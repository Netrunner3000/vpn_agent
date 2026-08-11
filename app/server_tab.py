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

from server import deploy as deploy_mod
from server import export, paths, provision, store
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

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(12)

        root.addWidget(self._build_site_row())

        columns = QHBoxLayout()
        columns.setSpacing(12)
        columns.addWidget(self._build_settings_panel(), stretch=1)
        columns.addWidget(self._build_peers_panel(), stretch=1)
        root.addLayout(columns)

        root.addWidget(self._build_deploy_panel())
        root.addWidget(self._build_output(), stretch=1)

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
        self.combo_sites.currentTextChanged.connect(self._on_site_selected)
        layout.addWidget(self.combo_sites)

        self.btn_new = QPushButton("New Server")
        self.btn_new.setObjectName("ConnectButton")
        self.btn_new.clicked.connect(self.on_new_site)
        layout.addWidget(self.btn_new)

        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setObjectName("DisconnectButton")
        self.btn_delete.clicked.connect(self.on_delete_site)
        layout.addWidget(self.btn_delete)

        layout.addStretch()

        self.lbl_state = QLabel("—")
        self.lbl_state.setObjectName("StatusNeutral")
        layout.addWidget(self.lbl_state)

        return container

    def _build_settings_panel(self) -> QGroupBox:
        box = QGroupBox("CONFIGURATION")
        box.setObjectName("StatusPanel")
        form = QFormLayout(box)
        form.setSpacing(7)

        self.lbl_mode = QLabel("—")
        self.lbl_mode.setObjectName("StatusValue")
        form.addRow("Mode", self.lbl_mode)

        self.edit_endpoint = QLineEdit()
        self.edit_endpoint.setPlaceholderText("public IP or DNS name")
        form.addRow("Endpoint", self.edit_endpoint)

        self.edit_ssh = QLineEdit()
        self.edit_ssh.setPlaceholderText("root@host")
        form.addRow("SSH", self.edit_ssh)

        self.spin_wg_port = QSpinBox()
        self.spin_wg_port.setRange(1, 65535)
        form.addRow("WireGuard port", self.spin_wg_port)

        self.spin_ovpn_port = QSpinBox()
        self.spin_ovpn_port.setRange(1, 65535)
        form.addRow("OpenVPN port", self.spin_ovpn_port)

        self.chk_openvpn = QCheckBox("OpenVPN TCP fallback")
        form.addRow("", self.chk_openvpn)

        self.chk_full_tunnel = QCheckBox("Route all client traffic through the server")
        form.addRow("", self.chk_full_tunnel)

        self.edit_dns = QLineEdit()
        self.edit_dns.setPlaceholderText("1.1.1.1, 1.0.0.1")
        form.addRow("Push DNS", self.edit_dns)

        self.edit_lan = QLineEdit()
        self.edit_lan.setPlaceholderText("192.168.1.0/24")
        form.addRow("LAN routes", self.edit_lan)

        self.lbl_pubkey = QLabel("—")
        self.lbl_pubkey.setObjectName("StatusValue")
        self.lbl_pubkey.setWordWrap(True)
        self.lbl_pubkey.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        form.addRow("Public key", self.lbl_pubkey)

        self.btn_save = QPushButton("Save Configuration")
        self.btn_save.setObjectName("ActionButton")
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
        self.list_peers.itemSelectionChanged.connect(self._update_peer_buttons)
        layout.addWidget(self.list_peers, stretch=1)

        row1 = QHBoxLayout()
        row1.setSpacing(6)
        self.btn_add_peer = QPushButton("Add Device")
        self.btn_add_peer.setObjectName("ConnectButton")
        self.btn_add_peer.clicked.connect(self.on_add_peer)
        row1.addWidget(self.btn_add_peer)

        self.btn_toggle_peer = QPushButton("Disable")
        self.btn_toggle_peer.setObjectName("ActionButton")
        self.btn_toggle_peer.clicked.connect(self.on_toggle_peer)
        row1.addWidget(self.btn_toggle_peer)

        self.btn_remove_peer = QPushButton("Remove")
        self.btn_remove_peer.setObjectName("DisconnectButton")
        self.btn_remove_peer.clicked.connect(self.on_remove_peer)
        row1.addWidget(self.btn_remove_peer)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(6)
        self.btn_qr = QPushButton("Show QR")
        self.btn_qr.setObjectName("ActionButton")
        self.btn_qr.clicked.connect(self.on_show_qr)
        row2.addWidget(self.btn_qr)

        self.btn_export = QPushButton("Export Configs")
        self.btn_export.setObjectName("ActionButton")
        self.btn_export.clicked.connect(self.on_export)
        row2.addWidget(self.btn_export)

        self.btn_rotate = QPushButton("Rotate Keys")
        self.btn_rotate.setObjectName("ActionButton")
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
        self.btn_check.clicked.connect(self.on_check)
        layout.addWidget(self.btn_check)

        self.btn_deploy = QPushButton("Deploy")
        self.btn_deploy.setObjectName("ConnectButton")
        self.btn_deploy.clicked.connect(self.on_deploy)
        layout.addWidget(self.btn_deploy)

        self.btn_script = QPushButton("Save Installer Script")
        self.btn_script.setObjectName("ActionButton")
        self.btn_script.clicked.connect(self.on_save_script)
        layout.addWidget(self.btn_script)

        self.btn_register = QPushButton("Add to Profiles")
        self.btn_register.setObjectName("ActionButton")
        self.btn_register.clicked.connect(self.on_register_profile)
        layout.addWidget(self.btn_register)

        self.btn_teardown = QPushButton("Tear Down")
        self.btn_teardown.setObjectName("DisconnectButton")
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

        self.btn_teardown.setEnabled(site.mode == MODE_REMOTE and bool(site.last_deployed_at))
        self.lbl_state.setText(
            f"Deployed {site.last_deployed_at}" if site.last_deployed_at
            else "Never deployed"
        )
        self._refresh_peers()

    def _refresh_peers(self) -> None:
        self.list_peers.clear()
        if self._site is None:
            self._update_peer_buttons()
            return

        for peer in self._site.peers:
            flags = [peer.ip4]
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
