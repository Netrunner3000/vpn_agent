"""
server_tab.py — The half of VPN Agent that builds servers.

The other tab watches a tunnel; this one creates the thing at the far end of
it. Layout follows the order the work actually happens in: pick or create a
site, set where it lives, add the devices that may connect, then deploy.

Anything that touches the network or a server runs on a worker thread. A deploy
runs apt-get on a cold VPS and can take a minute; doing that on the GUI thread
would freeze the window in a way macOS reports as "application not responding".
"""

from __future__ import annotations

import io
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.doc_dialog import DocDialog
from app.server_doc_content import SERVER_DOC_HTML
from server import deploy as deploy_mod
from server import backup, bootstrap, export, paths, provision, store
from server.model import MODE_NATIVE, MODE_REMOTE, Site


# ── Workers ──────────────────────────────────────


class StreamWorker(QObject):
    """Runs a long server operation, forwarding its output line by line."""

    line = Signal(str)
    done = Signal(object)

    def __init__(self, fn, *args, **kwargs) -> None:
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self) -> None:
        try:
            result = self._fn(*self._args, on_output=self.line.emit, **self._kwargs)
        except Exception as exc:  # a crash here must not take the window with it
            result = deploy_mod.DeployResult(False, error=f"{type(exc).__name__}: {exc}")
        self.done.emit(result)


# ── Dialogs ──────────────────────────────────────


class NewSiteDialog(QDialog):
    """Collects the few things that cannot be defaulted."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New VPN Server")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)

        blurb = QLabel(
            "<b>Remote</b> deploys to a rented host over SSH — your traffic exits "
            "there, so your apparent location changes.<br><br>"
            "<b>Native</b> runs on hardware you own at home — traffic exits through "
            "your own ISP, giving you an encrypted way into your network rather "
            "than a new exit point."
        )
        blurb.setWordWrap(True)
        blurb.setObjectName("StatusValue")
        layout.addWidget(blurb)

        form = QFormLayout()
        form.setSpacing(8)

        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText("Berlin VPS")
        form.addRow("Name", self.edit_name)

        self.combo_mode = QComboBox()
        self.combo_mode.addItem("Remote — deploy to a VPS over SSH", MODE_REMOTE)
        self.combo_mode.addItem("Native — run on hardware I own", MODE_NATIVE)
        self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)
        form.addRow("Mode", self.combo_mode)

        self.edit_host = QLineEdit()
        self.edit_host.setPlaceholderText("public IP, or a dynamic-DNS name for home")
        form.addRow("Endpoint", self.edit_host)

        self.edit_ssh = QLineEdit("root@")
        self.edit_ssh.setPlaceholderText("root@203.0.113.10")
        form.addRow("SSH", self.edit_ssh)

        self.chk_openvpn = QCheckBox("Also set up the OpenVPN TCP/443 fallback")
        self.chk_openvpn.setChecked(True)
        form.addRow("", self.chk_openvpn)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_mode_changed(self) -> None:
        remote = self.combo_mode.currentData() == MODE_REMOTE
        self.edit_ssh.setEnabled(remote)
        self.edit_ssh.setPlaceholderText(
            "root@203.0.113.10" if remote else "not needed — installs on this machine"
        )

    def values(self) -> dict:
        return {
            "name": self.edit_name.text().strip(),
            "mode": self.combo_mode.currentData(),
            "host": self.edit_host.text().strip(),
            "ssh": self.edit_ssh.text().strip(),
            "openvpn": self.chk_openvpn.isChecked(),
        }


class QRDialog(QDialog):
    """Shows a peer's WireGuard config as a scannable code."""

    def __init__(self, site: Site, peer, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{peer.name} — scan to import")

        layout = QVBoxLayout(self)

        import segno

        from server import render

        buffer = io.BytesIO()
        segno.make(render.wg_client_config(site, peer), error="m").save(
            buffer, kind="png", scale=7, border=3, dark="#000000", light="#ffffff"
        )
        pixmap = QPixmap()
        pixmap.loadFromData(buffer.getvalue(), "PNG")

        image = QLabel()
        image.setPixmap(pixmap)
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(image)

        caption = QLabel(
            "Open the WireGuard app on the device → Add tunnel → Create from QR code.<br>"
            "<b>This encodes a private key.</b> Anyone who photographs it has your tunnel."
        )
        caption.setWordWrap(True)
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        caption.setObjectName("StatusValue")
        layout.addWidget(caption)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


# ── The tab ──────────────────────────────────────


class ServerTab(QWidget):
    """Create, configure, and deploy VPN servers."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._site: Site | None = None
        self._threads: list[QThread] = []
        self._busy = False
        self._guide_dialog = None
        self._live_status: dict = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(12)

        root.addWidget(self._build_site_row())

        columns = QHBoxLayout()
        columns.setSpacing(12)
        columns.addWidget(self._build_settings_panel(), stretch=1)
        columns.addWidget(self._build_peers_panel(), stretch=1)

        # The configuration form has a fixed number of rows and a real minimum
        # height; the output pane can shrink to nothing without harm. Giving the
        # columns the larger share stops the form being squeezed until its last
        # row — the Save button — is cut in half.
        root.addLayout(columns, stretch=3)

        root.addWidget(self._build_deploy_panel())
        root.addWidget(self._build_output(), stretch=2)

        self._refresh_sites()

    # ── UI builders ──────────────────────────────

    def _build_site_row(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        label = QLabel("SERVER")
        label.setObjectName("SectionHeader")
        layout.addWidget(label)

        self.combo_sites = QComboBox()
        self.combo_sites.setObjectName("ProfileDropdown")
        self.combo_sites.setMinimumWidth(220)
        self.combo_sites.setToolTip(
            "The VPN servers you have built.\n\n"
            "Each one keeps its own keys, certificate authority and device list in\n"
            "~/Library/Application Support/VPN Agent/sites/ — never inside this app\n"
            "and never inside the git repo."
        )
        self.combo_sites.currentTextChanged.connect(self._on_site_selected)
        layout.addWidget(self.combo_sites)

        self.btn_new = QPushButton("New Server")
        self.btn_new.setObjectName("ConnectButton")
        self.btn_new.setToolTip(
            "Create a new VPN server and generate its identity.\n\n"
            "Generates the WireGuard server keypair and, if enabled, an OpenVPN\n"
            "certificate authority. This happens on your machine — the server never\n"
            "creates its own keys and never sees the CA key.\n\n"
            "Nothing is installed anywhere until you press Deploy."
        )
        self.btn_new.clicked.connect(self.on_new_site)
        layout.addWidget(self.btn_new)

        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setObjectName("DisconnectButton")
        self.btn_delete.setToolTip(
            "Delete this server's local state.\n\n"
            "DESTRUCTIVE. This is the only copy of the server and CA private keys.\n"
            "Every config you have handed out stops working and none can be reissued.\n\n"
            "The server itself keeps running — use Tear Down first if you want it gone."
        )
        self.btn_delete.clicked.connect(self.on_delete_site)
        layout.addWidget(self.btn_delete)

        layout.addStretch()

        self.lbl_state = QLabel("—")
        self.lbl_state.setObjectName("StatusNeutral")
        layout.addWidget(self.lbl_state)

        self.btn_guide = QPushButton("? Server Guide")
        self.btn_guide.setObjectName("HelpButton")
        self.btn_guide.setToolTip(
            "Open the server-building guide.\n\n"
            "Covers choosing between remote and native, picking a VPS, what the\n"
            "installer does to the machine, getting configs onto phones, where your\n"
            "keys are stored, and what this setup does not protect you from."
        )
        self.btn_guide.clicked.connect(self.on_open_guide)
        layout.addWidget(self.btn_guide)

        return container

    def _build_settings_panel(self) -> QGroupBox:
        box = QGroupBox("CONFIGURATION")
        box.setObjectName("StatusPanel")
        form = QFormLayout(box)
        form.setSpacing(7)

        self.lbl_mode = QLabel("—")
        self.lbl_mode.setObjectName("StatusValue")
        self.lbl_mode.setToolTip(
            "Where this server runs. Fixed when you create it.\n\n"
            "Remote — a rented host reached over SSH. Traffic exits there, so your\n"
            "  apparent IP and country become the server's. This is the mode that\n"
            "  hides your home connection.\n\n"
            "Native — hardware you own on your own LAN. Traffic exits through your\n"
            "  own ISP, so it does NOT change your apparent location. What it gives\n"
            "  you is an encrypted way back into your home network from outside."
        )
        form.addRow("Mode", self.lbl_mode)

        self.edit_endpoint = QLineEdit()
        self.edit_endpoint.setPlaceholderText("public IP or DNS name")
        self.edit_endpoint.setToolTip(
            "The address clients dial to reach this server.\n\n"
            "For a VPS: its public IP.\n"
            "For a home server: a dynamic-DNS name. A home IP changes whenever your\n"
            "ISP feels like it, and every config you handed out points at the old one.\n\n"
            "Changing this reissues the OpenVPN server certificate so its subject\n"
            "names still match — otherwise clients start failing verification."
        )
        form.addRow("Endpoint", self.edit_endpoint)

        self.edit_ssh = QLineEdit()
        self.edit_ssh.setPlaceholderText("root@host")
        self.edit_ssh.setToolTip(
            "Where to deploy, as user@host. Remote mode only.\n\n"
            "Key-based authentication only — this never asks for or stores a password.\n"
            "As a non-root user the installer runs under `sudo -n`, which needs\n"
            "passwordless sudo configured on the target."
        )
        form.addRow("SSH", self.edit_ssh)

        self.spin_wg_port = QSpinBox()
        self.spin_wg_port.setRange(1, 65535)
        self.spin_wg_port.setToolTip(
            "UDP port WireGuard listens on. 51820 is the convention.\n\n"
            "Worth changing if you are on a network that throttles the default.\n"
            "Remember to open it on the host's firewall and, for a home server,\n"
            "to forward it on your router."
        )
        form.addRow("WireGuard port", self.spin_wg_port)

        self.spin_ovpn_port = QSpinBox()
        self.spin_ovpn_port.setRange(1, 65535)
        self.spin_ovpn_port.setToolTip(
            "TCP port for the OpenVPN fallback. 443 by default, deliberately.\n\n"
            "443 is the HTTPS port, so the traffic passes on networks that allow\n"
            "only web browsing. Combined with tls-crypt, a scanner probing the port\n"
            "gets no OpenVPN handshake to fingerprint.\n\n"
            "If the host also serves real HTTPS on 443, pick another port."
        )
        form.addRow("OpenVPN port", self.spin_ovpn_port)

        self.chk_openvpn = QCheckBox("OpenVPN TCP fallback")
        self.chk_openvpn.setToolTip(
            "Run an OpenVPN endpoint alongside WireGuard.\n\n"
            "WireGuard is UDP, and some networks — hotels, corporate guest wifi,\n"
            "airports — pass only TCP 80 and 443. There WireGuard simply cannot\n"
            "connect, and the fallback is the only thing that works.\n\n"
            "It is slower. Use WireGuard by default and reach for the .ovpn profile\n"
            "only when the tunnel will not come up.\n\n"
            "Enabling this later issues certificates for every existing device."
        )
        form.addRow("", self.chk_openvpn)

        self.chk_full_tunnel = QCheckBox("Route all client traffic through the server")
        self.chk_full_tunnel.setToolTip(
            "On  — every packet goes through the tunnel. Your apparent IP becomes\n"
            "     the server's. This is what you want on a VPS.\n\n"
            "Off — only the VPN subnet and the LAN routes below go through the\n"
            "     tunnel; everything else uses the normal connection. This is the\n"
            "     sane default for a home server, whose exit IP is your own ISP\n"
            "     anyway, so routing all traffic through it buys nothing and costs\n"
            "     you a round trip."
        )
        form.addRow("", self.chk_full_tunnel)

        self.edit_dns = QLineEdit()
        self.edit_dns.setPlaceholderText("1.1.1.1, 1.0.0.1")
        self.edit_dns.setToolTip(
            "Resolvers pushed to clients, comma separated.\n\n"
            "Without this a client keeps using whatever resolver the local network\n"
            "handed it — so the tunnel hides the traffic while the DNS lookups still\n"
            "announce every site visited. That is a DNS leak, and it is exactly what\n"
            "the Monitor tab checks for.\n\n"
            "For a home server you may prefer your router's address, so names on\n"
            "your own LAN still resolve."
        )
        form.addRow("Push DNS", self.edit_dns)

        self.edit_lan = QLineEdit()
        self.edit_lan.setPlaceholderText("192.168.1.0/24")
        self.edit_lan.setToolTip(
            "Extra networks clients should reach through the tunnel, comma separated.\n"
            "Only used in split-tunnel mode.\n\n"
            "This is what lets you reach your home NAS, printer or router from a\n"
            "hotel. Set it to the subnet your home devices actually live on — check\n"
            "your router if you are not sure whether it is 192.168.1.0/24 or\n"
            "192.168.8.0/24."
        )
        form.addRow("LAN routes", self.edit_lan)

        # A read-only field rather than a label: a 44-character base64 key is
        # wider than the column, and a label would either wrap into a row the
        # form has already squeezed flat or silently truncate. A field scrolls,
        # and the value is meant to be selected and copied anyway.
        self.lbl_pubkey = QLineEdit("—")
        self.lbl_pubkey.setReadOnly(True)
        self.lbl_pubkey.setCursorPosition(0)
        self.lbl_pubkey.setToolTip(
            "This server's WireGuard public key. Safe to share — it is in every\n"
            "client config already.\n\n"
            "The matching private key stays in the site file on this machine and is\n"
            "written to the server only during a deploy, over the SSH channel."
        )
        form.addRow("Public key", self.lbl_pubkey)

        self.btn_save = QPushButton("Save Configuration")
        self.btn_save.setObjectName("ActionButton")
        # Last row of a crowded form: without a floor the layout shrinks it
        # until the label is cut through the middle.
        self.btn_save.setMinimumHeight(30)
        self.btn_save.setToolTip(
            "Save these settings to the site file.\n\n"
            "Saving only records the change locally. The server keeps running its\n"
            "old configuration until you press Deploy."
        )
        self.btn_save.clicked.connect(self.on_save_settings)
        form.addRow("", self.btn_save)

        return box

    def _build_peers_panel(self) -> QGroupBox:
        box = QGroupBox("DEVICES")
        box.setObjectName("StatusPanel")
        layout = QVBoxLayout(box)
        layout.setSpacing(8)

        self.list_peers = QListWidget()
        self.list_peers.setObjectName("PeerList")
        self.list_peers.setMinimumHeight(150)
        self.list_peers.setToolTip(
            "Devices allowed to connect to this server.\n\n"
            "Each gets its own keypair, its own pre-shared key and its own address,\n"
            "so one device being lost never exposes the others.\n\n"
            "Greyed out means disabled — it keeps its keys but is left out of the\n"
            "server config on the next deploy."
        )
        self.list_peers.itemSelectionChanged.connect(self._update_peer_buttons)
        layout.addWidget(self.list_peers, stretch=1)

        row1 = QHBoxLayout()
        row1.setSpacing(6)
        self.btn_add_peer = QPushButton("Add Device")
        self.btn_add_peer.setObjectName("ConnectButton")
        self.btn_add_peer.setToolTip(
            "Generate credentials for one more device.\n\n"
            "Creates a WireGuard keypair, a pre-shared key, the next free address\n"
            "and — if the fallback is on — an OpenVPN client certificate.\n\n"
            "Give each device its own entry rather than sharing one config. Sharing\n"
            "means you cannot revoke a single lost phone without cutting off\n"
            "everything else."
        )
        self.btn_add_peer.clicked.connect(self.on_add_peer)
        row1.addWidget(self.btn_add_peer)

        self.btn_toggle_peer = QPushButton("Disable")
        self.btn_toggle_peer.setObjectName("ActionButton")
        self.btn_toggle_peer.setToolTip(
            "Switch a device off without discarding its keys.\n\n"
            "It keeps its address and certificate, so you can switch it back on\n"
            "later without reissuing anything to the device.\n\n"
            "Takes effect on the next deploy."
        )
        self.btn_toggle_peer.clicked.connect(self.on_toggle_peer)
        row1.addWidget(self.btn_toggle_peer)

        self.btn_remove_peer = QPushButton("Remove")
        self.btn_remove_peer.setObjectName("DisconnectButton")
        self.btn_remove_peer.setToolTip(
            "Delete this device and discard its keys. Its address is freed for reuse.\n\n"
            "Removing here does not revoke anything by itself — the device keeps\n"
            "working until you Deploy, which is what actually rewrites the server."
        )
        self.btn_remove_peer.clicked.connect(self.on_remove_peer)
        row1.addWidget(self.btn_remove_peer)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(6)
        self.btn_qr = QPushButton("Show QR")
        self.btn_qr.setObjectName("ActionButton")
        self.btn_qr.setToolTip(
            "Show this device's WireGuard config as a scannable code.\n\n"
            "On the phone: WireGuard app → Add tunnel → Create from QR code.\n"
            "Far easier than moving a file onto a phone.\n\n"
            "The code encodes a private key. Anyone who photographs your screen\n"
            "has your tunnel — do not project it or screenshot it into a chat.\n\n"
            "WireGuard only: an .ovpn carries a whole certificate chain and will\n"
            "not fit in a QR code."
        )
        self.btn_qr.clicked.connect(self.on_show_qr)
        row2.addWidget(self.btn_qr)

        self.btn_export = QPushButton("Export Configs")
        self.btn_export.setObjectName("ActionButton")
        self.btn_export.setToolTip(
            "Write this device's config files to a folder you choose.\n\n"
            "Produces a .conf for WireGuard and, if the fallback is on, a\n"
            "self-contained .ovpn with its keys inlined.\n\n"
            "Both contain private keys and are written owner-readable only.\n"
            "Delete them once the device has imported them, and do not send them\n"
            "through email or a cloud drive."
        )
        self.btn_export.clicked.connect(self.on_export)
        row2.addWidget(self.btn_export)

        self.btn_rotate = QPushButton("Rotate Keys")
        self.btn_rotate.setObjectName("ActionButton")
        self.btn_rotate.setToolTip(
            "Issue fresh keys for this device, keeping its name and address.\n\n"
            "This is what you do when a phone or laptop is lost or stolen. The old\n"
            "config stops working as soon as you deploy; the new one has to be\n"
            "delivered to the replacement device."
        )
        self.btn_rotate.clicked.connect(self.on_rotate_peer)
        row2.addWidget(self.btn_rotate)
        layout.addLayout(row2)

        return box

    def _build_deploy_panel(self) -> QGroupBox:
        box = QGroupBox("DEPLOY")
        box.setObjectName("StatusPanel")
        layout = QHBoxLayout(box)
        layout.setSpacing(8)

        self.btn_check = QPushButton("Check")
        self.btn_check.setObjectName("ActionButton")
        self.btn_check.setToolTip(
            "Validate the configuration and test the connection, without changing\n"
            "anything.\n\n"
            "Catches the things that would otherwise fail halfway through an\n"
            "install: overlapping subnets, a missing endpoint, an unreachable host,\n"
            "a key SSH will not accept, a target that is not Debian or Ubuntu.\n\n"
            "Always safe to run."
        )
        self.btn_check.clicked.connect(self.on_check)
        layout.addWidget(self.btn_check)

        self.btn_deploy = QPushButton("Deploy")
        self.btn_deploy.setObjectName("ConnectButton")
        self.btn_deploy.setToolTip(
            "Install and start the VPN on the target host.\n\n"
            "Installs the packages, writes the configs, enables IP forwarding, sets\n"
            "up NAT and starts both services. Idempotent — running it twice changes\n"
            "nothing the second time, which is why adding a device is just another\n"
            "deploy.\n\n"
            "Adding a peer reloads WireGuard in place, so tunnels that are already\n"
            "up stay up.\n\n"
            "This is also the step that applies removals: a device you deleted keeps\n"
            "working until you deploy."
        )
        self.btn_deploy.clicked.connect(self.on_deploy)
        layout.addWidget(self.btn_deploy)

        self.btn_script = QPushButton("Save Installer Script")
        self.btn_script.setObjectName("ActionButton")
        self.btn_script.setToolTip(
            "Write the installer to a file instead of running it.\n\n"
            "Use this to read exactly what would be done before letting it touch a\n"
            "server, or to install on a host this app cannot reach over SSH — copy\n"
            "the script across and run it with sudo.\n\n"
            "It embeds the server's private keys. Run it, then delete it."
        )
        self.btn_script.clicked.connect(self.on_save_script)
        layout.addWidget(self.btn_script)

        self.btn_register = QPushButton("Add to Profiles")
        self.btn_register.setObjectName("ActionButton")
        self.btn_register.setToolTip(
            "Add this server to the Monitor tab's profile list.\n\n"
            "That is what connects the two halves of the app: once registered, the\n"
            "server you just built appears in the dropdown, and the latency test,\n"
            "tunnel indicator and health monitor all start watching it."
        )
        self.btn_register.clicked.connect(self.on_register_profile)
        layout.addWidget(self.btn_register)

        self.btn_status = QPushButton("Status")
        self.btn_status.setObjectName("ActionButton")
        self.btn_status.setToolTip(
            "Ask the server which devices are actually connected.\n\n"
            "Deploying tells you the configuration was written; this tells you what\n"
            "has happened since — when each device last handshaked, how much it has\n"
            "transferred, and which address it is connecting from.\n\n"
            "WireGuard is connectionless, so 'connected' means 'handshaked in the\n"
            "last few minutes'. An active device rekeys every two minutes.\n\n"
            "Remote servers only."
        )
        self.btn_status.clicked.connect(self.on_status)
        layout.addWidget(self.btn_status)

        self.btn_backup = QPushButton("Backup…")
        self.btn_backup.setObjectName("ActionButton")
        self.btn_backup.setToolTip(
            "Write an encrypted backup of this server's keys.\n\n"
            "The site file is the ONLY copy of the server key and the certificate\n"
            "authority. Lose it and every config you have issued is permanently\n"
            "dead, with no way to reissue one.\n\n"
            "Encrypted with a passphrase you choose (scrypt + AES-256-GCM). The\n"
            "passphrase is never stored — lose it and the backup is gone too.\n\n"
            "Use this before reinstalling, or to carry a server to another machine."
        )
        self.btn_backup.clicked.connect(self.on_backup)
        layout.addWidget(self.btn_backup)

        self.btn_restore = QPushButton("Restore…")
        self.btn_restore.setObjectName("ActionButton")
        self.btn_restore.setToolTip(
            "Restore a server from an encrypted backup.\n\n"
            "Brings back the keys, the certificate authority and every device, so\n"
            "the configs already on your phones keep working.\n\n"
            "Refuses to overwrite an existing server of the same name unless you\n"
            "confirm — replacing its keys would invalidate every config issued\n"
            "from it."
        )
        self.btn_restore.clicked.connect(self.on_restore)
        layout.addWidget(self.btn_restore)

        self.btn_teardown = QPushButton("Tear Down")
        self.btn_teardown.setObjectName("DisconnectButton")
        self.btn_teardown.setToolTip(
            "Remove the VPN from the server.\n\n"
            "Stops and disables both services, drops the NAT rules and deletes the\n"
            "configs. Installed packages are left alone, since removing them could\n"
            "take out something else on the box.\n\n"
            "Every connected device loses the tunnel immediately. Your local keys\n"
            "are kept, so you can redeploy later.\n\n"
            "Remote servers only."
        )
        self.btn_teardown.clicked.connect(self.on_teardown)
        layout.addWidget(self.btn_teardown)

        layout.addStretch()
        return box

    def _build_output(self) -> QGroupBox:
        box = QGroupBox("OUTPUT")
        box.setObjectName("StatusPanel")
        layout = QVBoxLayout(box)

        self.output = QPlainTextEdit()
        self.output.setObjectName("DeployOutput")
        self.output.setReadOnly(True)
        self.output.setMinimumHeight(110)
        self.output.setToolTip(
            "Live output from the server as it is configured.\n\n"
            "Lines prefixed [vpn-agent] come from the installer running on the host.\n"
            "A deploy ends with a verification pass — WireGuard active, OpenVPN\n"
            "active, forwarding on, NAT rules present. If any of those fail, the\n"
            "reason is in this pane."
        )
        layout.addWidget(self.output)

        return box

    # ── State ────────────────────────────────────

    def _refresh_sites(self, select: str | None = None) -> None:
        names = store.list_sites()
        self.combo_sites.blockSignals(True)
        self.combo_sites.clear()
        self.combo_sites.addItems(names)
        if select and select in names:
            self.combo_sites.setCurrentText(select)
        self.combo_sites.blockSignals(False)

        if names:
            self._load_site(self.combo_sites.currentText())
        else:
            self._site = None
            self._apply_site_to_form()

    def _on_site_selected(self, name: str) -> None:
        if name:
            self._load_site(name)

    def _load_site(self, name: str) -> None:
        # Handshake ages belong to the site they were read from.
        self._live_status = {}
        try:
            self._site = store.load_site(name)
        except store.InsecurePermissions as exc:
            self._site = None
            self._warn("Insecure permissions", str(exc))
        except (FileNotFoundError, ValueError) as exc:
            self._site = None
            self._append(f"Could not load {name!r}: {exc}")
        self._apply_site_to_form()

    def _apply_site_to_form(self) -> None:
        site = self._site
        enabled = site is not None

        for widget in (
            self.edit_endpoint, self.edit_ssh, self.spin_wg_port, self.spin_ovpn_port,
            self.chk_openvpn, self.chk_full_tunnel, self.edit_dns, self.edit_lan,
            self.btn_save, self.btn_add_peer, self.btn_check, self.btn_deploy,
            self.btn_script, self.btn_delete, self.btn_register, self.btn_teardown,
        ):
            widget.setEnabled(enabled)

        if site is None:
            self.lbl_mode.setText("—")
            self.lbl_pubkey.setText("—")
            self.lbl_state.setText("No servers yet — press New Server")
            self.list_peers.clear()
            self._update_peer_buttons()
            return

        self.lbl_mode.setText(
            "Remote (deploys over SSH)" if site.mode == MODE_REMOTE
            else "Native (installs on this machine)"
        )
        self.edit_endpoint.setText(site.endpoint_host)
        self.edit_ssh.setText(site.ssh.destination() if site.ssh.is_configured() else "")
        self.edit_ssh.setEnabled(site.mode == MODE_REMOTE)
        self.spin_wg_port.setValue(site.wg_port)
        self.spin_ovpn_port.setValue(site.ovpn_port)
        self.spin_ovpn_port.setEnabled(site.enable_openvpn)
        self.chk_openvpn.setChecked(site.enable_openvpn)
        self.chk_full_tunnel.setChecked(site.full_tunnel)
        self.edit_dns.setText(", ".join(site.dns))
        self.edit_lan.setText(", ".join(site.lan_routes))
        self.edit_lan.setEnabled(not site.full_tunnel)
        self.lbl_pubkey.setText(site.server_wg_public_key or "—")
        self.lbl_pubkey.setCursorPosition(0)  # show the start, not the tail

        self.btn_teardown.setEnabled(bool(site.last_deployed_at))
        self.btn_status.setEnabled(site.mode == MODE_REMOTE)
        self._warn_if_pf_registration_lost(site)
        self.lbl_state.setText(
            f"Deployed {site.last_deployed_at}" if site.last_deployed_at
            else "Never deployed"
        )
        self._refresh_peers()

    def _warn_if_pf_registration_lost(self, site) -> None:
        """
        A macOS update rewrites /etc/pf.conf and drops our anchor with it.

        The failure is quiet and confusing: WireGuard still starts, the
        handshake still completes, and nothing routes, because NAT is gone. The
        tunnel looks healthy right up until you try to use it. Say so instead.
        """
        import platform as _platform

        if site.mode != MODE_NATIVE or not site.last_deployed_at:
            return
        if _platform.system() != "Darwin":
            return
        if bootstrap.pf_conf_has_marker():
            return

        self._append(
            "WARNING: this Mac's /etc/pf.conf no longer contains the VPN Agent "
            "block. A macOS update almost certainly rewrote it.\n"
            "   NAT is gone, so the tunnel will connect and carry nothing. "
            "Deploy again to restore it."
        )

    def _refresh_peers(self) -> None:
        self.list_peers.clear()
        if self._site is None:
            self._update_peer_buttons()
            return

        for peer in self._site.peers:
            flags = [peer.ip4]
            live = self._live_status.get(peer.name)
            if live is not None:
                flags.append(
                    f"● {live.describe_handshake()}" if live.connected
                    else f"○ {live.describe_handshake()}"
                )
            if peer.has_openvpn:
                flags.append("ovpn")
            if not peer.enabled:
                flags.append("disabled")
            item = QListWidgetItem(f"{peer.name}  ·  {'  ·  '.join(flags)}")
            item.setData(Qt.ItemDataRole.UserRole, peer.name)
            if not peer.enabled:
                item.setForeground(Qt.GlobalColor.gray)
            self.list_peers.addItem(item)

        self._update_peer_buttons()

    def _update_peer_buttons(self) -> None:
        peer = self._selected_peer()
        has = peer is not None
        for widget in (
            self.btn_remove_peer, self.btn_qr, self.btn_export,
            self.btn_rotate, self.btn_toggle_peer,
        ):
            widget.setEnabled(has and not self._busy)
        if has:
            self.btn_toggle_peer.setText("Enable" if not peer.enabled else "Disable")

    def _selected_peer(self):
        item = self.list_peers.currentItem()
        if item is None or self._site is None:
            return None
        return self._site.get_peer(item.data(Qt.ItemDataRole.UserRole))

    # ── Actions ──────────────────────────────────

    def on_new_site(self) -> None:
        dialog = NewSiteDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()

        if not values["name"]:
            self._warn("Name required", "Give the server a name.")
            return

        try:
            site = provision.init_site(
                values["name"],
                values["mode"],
                endpoint_host=values["host"],
                enable_openvpn=values["openvpn"],
            )
        except FileExistsError as exc:
            self._warn("Already exists", str(exc))
            return

        ssh = values["ssh"]
        if values["mode"] == MODE_REMOTE and ssh and ssh != "root@":
            user, _, host = ssh.partition("@")
            site.ssh.user, site.ssh.host = (user or "root"), host
            store.save_site(site)

        self._append(f"Created {site.name!r}. Keys generated at {paths.site_file(site.name)}")
        self._append("Add at least one device, then Deploy.")
        self._refresh_sites(select=site.name)

    def on_delete_site(self) -> None:
        if self._site is None:
            return
        name = self._site.name
        if not self._confirm(
            "Delete this server?",
            f"Deletes all local state for {name!r}, including the only copy of the "
            "server and CA private keys.\n\nEvery config already handed out stops "
            "working, and none of them can ever be reissued. The server itself is "
            "left running — tear it down first if you want it gone.",
        ):
            return
        store.delete_site(name)
        self._append(f"Deleted {name!r}.")
        self._refresh_sites()

    def on_save_settings(self) -> None:
        site = self._site
        if site is None:
            return

        host = self.edit_endpoint.text().strip()
        if host != site.endpoint_host:
            provision.set_endpoint(site, host)

        ssh = self.edit_ssh.text().strip()
        if ssh:
            user, _, remote_host = ssh.partition("@")
            if remote_host:
                site.ssh.user, site.ssh.host = user, remote_host
            else:
                site.ssh.host = user

        site.wg_port = self.spin_wg_port.value()
        site.ovpn_port = self.spin_ovpn_port.value()
        site.full_tunnel = self.chk_full_tunnel.isChecked()
        site.dns = [d.strip() for d in self.edit_dns.text().split(",") if d.strip()]
        site.lan_routes = [r.strip() for r in self.edit_lan.text().split(",") if r.strip()]

        if self.chk_openvpn.isChecked() and not site.enable_openvpn:
            provision.enable_openvpn(site)
            self._append("OpenVPN fallback enabled — certificates issued for all devices.")
        elif not self.chk_openvpn.isChecked():
            site.enable_openvpn = False

        problems = site.validate()
        store.save_site(site)
        self._append("Configuration saved.")
        for problem in problems:
            self._append(f"  warning: {problem}")
        self._apply_site_to_form()

    def on_add_peer(self) -> None:
        if self._site is None:
            return
        name, ok = QInputDialog.getText(
            self, "Add Device", "Device name (e.g. iphone, work-laptop):"
        )
        if not ok or not name.strip():
            return
        try:
            peer = provision.add_peer(self._site, name.strip())
        except ValueError as exc:
            self._warn("Could not add device", str(exc))
            return
        self._append(f"Added {peer.name!r} at {peer.ip4}. Deploy to activate it.")
        self._refresh_peers()

    def on_remove_peer(self) -> None:
        peer = self._selected_peer()
        if peer is None or self._site is None:
            return
        if not self._confirm(
            "Remove this device?",
            f"Removes {peer.name!r} and discards its keys.\n\nIt keeps working until "
            "you deploy again — deploying is what actually revokes it on the server.",
        ):
            return
        provision.remove_peer(self._site, peer.name)
        self._append(f"Removed {peer.name!r}. Deploy to revoke it on the server.")
        self._refresh_peers()

    def on_toggle_peer(self) -> None:
        peer = self._selected_peer()
        if peer is None or self._site is None:
            return
        provision.set_peer_enabled(self._site, peer.name, not peer.enabled)
        state = "enabled" if not peer.enabled else "disabled"
        self._append(f"{peer.name!r} {state}. Deploy to apply.")
        self._refresh_peers()

    def on_rotate_peer(self) -> None:
        peer = self._selected_peer()
        if peer is None or self._site is None:
            return
        if not self._confirm(
            "Rotate this device's keys?",
            f"Issues fresh keys for {peer.name!r}, keeping its name and address.\n\n"
            "Use this if the device was lost. Its current config stops working after "
            "the next deploy, and the new one has to be delivered to the device.",
        ):
            return
        provision.rotate_peer_keys(self._site, peer.name)
        self._append(f"Rotated keys for {peer.name!r}. Re-export and deploy.")
        self._refresh_peers()

    def on_open_guide(self) -> None:
        # Kept on the instance so it is not garbage-collected the moment this
        # method returns, which is what makes a non-modal dialog flash and vanish.
        if self._guide_dialog is None or not self._guide_dialog.isVisible():
            self._guide_dialog = DocDialog(
                SERVER_DOC_HTML, "BUILDING YOUR OWN VPN", parent=self
            )
            self._guide_dialog.show()
        else:
            self._guide_dialog.raise_()
            self._guide_dialog.activateWindow()

    def on_show_qr(self) -> None:
        peer = self._selected_peer()
        if peer is None or self._site is None:
            return
        QRDialog(self._site, peer, self).exec()

    def on_export(self) -> None:
        peer = self._selected_peer()
        if peer is None or self._site is None:
            return

        directory = QFileDialog.getExistingDirectory(
            self, "Export configs to…", str(paths.exports_dir(self._site.name))
        )
        if not directory:
            return

        written = export.export_peer(self._site, peer, directory=Path(directory))
        self._append(f"Exported {peer.name!r}:")
        for kind, path in written.items():
            self._append(f"   {kind}: {path}")
        self._append("   These hold private keys — delete them once imported.")
        QDesktopServices.openUrl(QUrl.fromLocalFile(directory))

    def on_register_profile(self) -> None:
        if self._site is None:
            return
        if export.register_profile(self._site):
            self._append(
                f"Added {self._site.name!r} to the profile list — it now appears in "
                "the Monitor tab's dropdown."
            )
        else:
            self._append("Profile already up to date.")

    def on_check(self) -> None:
        site = self._site
        if site is None:
            return
        self.output.clear()
        self._append(f"Checking {site.name!r}…")

        problems = deploy_mod.preflight(site)
        if problems:
            for problem in problems:
                self._append(f"  blocked: {problem}")
        else:
            self._append("  configuration is valid.")

        if site.mode == MODE_REMOTE and site.ssh.is_configured():
            self._append(f"  testing SSH to {site.ssh.destination()}…")
            self._start(deploy_mod.check_ssh, site, label="check")

    def on_deploy(self) -> None:
        site = self._site
        if site is None:
            return

        problems = deploy_mod.preflight(site)
        if problems:
            self.output.clear()
            for problem in problems:
                self._append(f"blocked: {problem}")
            self._warn("Cannot deploy", "\n".join(problems))
            return

        where = site.ssh.destination() if site.mode == MODE_REMOTE else "this machine"
        if not self._confirm(
            "Deploy now?",
            f"Installs and starts WireGuard"
            + (" and OpenVPN" if site.enable_openvpn else "")
            + f" on {where}, and replaces any config this tool wrote there before.\n\n"
            f"{len([p for p in site.peers if p.enabled])} device(s) will be able to connect.",
        ):
            return

        self.output.clear()
        self._append(f"Deploying {site.name!r} to {where}…")
        self._start(deploy_mod.deploy, site, label="deploy")

    def on_teardown(self) -> None:
        site = self._site
        if site is None:
            return
        if not self._confirm(
            "Tear down the server?",
            f"Stops and removes WireGuard, OpenVPN and the NAT rules on "
            f"{site.ssh.destination()}.\n\nEvery connected device loses the tunnel "
            "immediately. Local keys are kept, so you can redeploy later.",
        ):
            return
        self.output.clear()
        self._append("Tearing down…")
        self._start(deploy_mod.teardown, site, label="teardown")

    def on_status(self) -> None:
        site = self._site
        if site is None:
            return
        if site.mode != MODE_REMOTE:
            self._warn("Not available", "Live status works for remote servers only.")
            return
        self.output.clear()
        self._append(f"Asking {site.ssh.destination()} what it is doing…")
        self._start(self._fetch_status, site, label="status")

    @staticmethod
    def _fetch_status(site, on_output=None):
        """Runs on a worker thread; _start passes on_output to every callable."""
        return deploy_mod.server_status(site)

    def _show_status(self, status) -> None:
        self._live_status = {p.name: p for p in status.peers}
        self._append(status.summary())

        if status.peers:
            self._append("")
            for peer in status.peers:
                mark = "●" if peer.connected else "○"
                self._append(
                    f"  {mark} {peer.name:<18} {peer.describe_handshake():<12}"
                    f"{peer.describe_transfer():<26}{peer.endpoint or '-'}"
                )
            self._append("\n  ● connected (handshaked within ~3 minutes)   ○ idle")

        known = {p.name for p in self._site.peers} if self._site else set()
        strangers = [p.name for p in status.peers if p.name not in known]
        if strangers:
            self._append(
                f"\n  WARNING: the server has peer(s) this app does not know about: "
                f"{', '.join(strangers)}. Redeploy to bring it back in line."
            )
        self._refresh_peers()

    def on_backup(self) -> None:
        site = self._site
        if site is None:
            return

        passphrase = self._ask_passphrase("Choose a passphrase for this backup:")
        if passphrase is None:
            return
        problems = backup.passphrase_problems(passphrase)
        if problems and not self._confirm(
            "Weak passphrase", "\n".join(problems) + "\n\nUse it anyway?"
        ):
            return
        again = self._ask_passphrase("Repeat the passphrase:")
        if again is None:
            return
        if again != passphrase:
            self._warn("Passphrases differ", "The two entries did not match.")
            return

        default = str(Path.home() / f"{paths.slugify(site.name)}{backup.SUFFIX}")
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save encrypted backup", default, f"VPN Agent backup (*{backup.SUFFIX})"
        )
        if not filename:
            return

        try:
            written = backup.write_backup(site, passphrase, Path(filename))
        except backup.BackupError as exc:
            self._warn("Backup failed", str(exc))
            return

        self._append(f"Encrypted backup written to {written}")
        self._append("   Holds the server key and the certificate authority.")
        self._append("   Without the passphrase it cannot be opened — including by you.")

    def on_restore(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Restore from backup", str(Path.home()),
            f"VPN Agent backup (*{backup.SUFFIX})"
        )
        if not filename:
            return
        path = Path(filename)

        try:
            info = backup.describe(path.read_bytes())
        except (backup.BackupError, OSError) as exc:
            self._warn("Not a backup file", str(exc))
            return

        name = info["site"]
        overwrite = store.site_exists(name)
        if overwrite and not self._confirm(
            "Replace the existing server?",
            f"A server named {name!r} already exists.\n\nRestoring replaces its keys, "
            "which invalidates every config already issued from it. Continue?",
        ):
            return

        passphrase = self._ask_passphrase(f"Passphrase for {name!r}:")
        if passphrase is None:
            return

        try:
            site = backup.restore(path, passphrase, overwrite=overwrite)
        except backup.BackupError as exc:
            self._warn("Restore failed", str(exc))
            return

        self._append(f"Restored {site.name!r} with {len(site.peers)} device(s).")
        self._append("   Deploy it to make the server match this state again.")
        self._refresh_sites(select=site.name)

    def _ask_passphrase(self, prompt: str) -> str | None:
        text, ok = QInputDialog.getText(
            self, "Passphrase", prompt, QLineEdit.EchoMode.Password
        )
        if not ok:
            return None
        if not text:
            self._warn("Empty passphrase", "An unencrypted backup of a CA key is not offered.")
            return None
        return text

    def on_save_script(self) -> None:
        site = self._site
        if site is None:
            return
        default = str(Path.home() / f"install-{paths.slugify(site.name)}.sh")
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save installer script", default, "Shell scripts (*.sh)"
        )
        if not filename:
            return
        path = Path(filename)
        paths.write_private(path, deploy_mod.build_script(site))
        path.chmod(0o700)
        self._append(f"Wrote {path}")
        self._append("   It embeds private keys. Run it with sudo, then delete it.")

    # ── Threading ────────────────────────────────

    def _start(self, fn, *args, label: str) -> None:
        self._set_busy(True)

        thread = QThread()
        worker = StreamWorker(fn, *args)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.line.connect(self._append)
        worker.done.connect(lambda result: self._on_done(result, label))
        worker.done.connect(thread.quit)
        worker.done.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(
            lambda: self._threads.remove(thread) if thread in self._threads else None
        )
        self._threads.append(thread)
        thread.start()

    def _on_done(self, result, label: str) -> None:
        self._set_busy(False)

        if label == "status":
            if getattr(result, "reachable", False):
                self._show_status(result)
            else:
                self._append(f"\nstatus FAILED: {result.summary()}")
            return

        if getattr(result, "success", False):
            self._append(f"\n{label}: {result.summary()}")
            if label == "deploy" and self._site is not None:
                self._load_site(self._site.name)
                self._append(
                    "Export a device config and import it on the device to connect."
                )
        else:
            self._append(f"\n{label} FAILED: {getattr(result, 'summary', lambda: result)()}")
            for problem in getattr(result, "problems", []):
                self._append(f"  - {problem}")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        for widget in (
            self.btn_deploy, self.btn_check, self.btn_teardown, self.btn_new,
            self.btn_delete, self.btn_save, self.btn_add_peer, self.combo_sites,
        ):
            widget.setEnabled(not busy and (self._site is not None or widget is self.btn_new))
        self._update_peer_buttons()
        if busy:
            self.lbl_state.setText("Working…")

    def shutdown(self) -> None:
        """
        Stop every worker before Qt tears the widgets down.

        A QThread garbage-collected while still running makes Qt call abort(),
        which macOS reports as 'VPN Agent quit unexpectedly' — a crash dialog
        for what was actually a clean quit.
        """
        for thread in list(self._threads):
            if thread.isRunning():
                thread.quit()
                if not thread.wait(2000):
                    thread.terminate()
                    thread.wait()
        self._threads.clear()

    # ── Helpers ──────────────────────────────────

    def _append(self, text: str) -> None:
        self.output.appendPlainText(text)
        self.output.verticalScrollBar().setValue(
            self.output.verticalScrollBar().maximum()
        )

    def _warn(self, title: str, text: str) -> None:
        QMessageBox.warning(self, title, text)

    def _confirm(self, title: str, text: str) -> bool:
        answer = QMessageBox.question(
            self,
            title,
            text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes
