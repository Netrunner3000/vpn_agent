"""
privacy_tab.py — Tor, proxy chains, and the hardware address.

Three tools that are often assembled in the belief that stacking them adds up
to anonymity. They do not, and the tab says so rather than implying otherwise:
each one narrows a specific, different exposure, and the panels are labelled
with which.

Everything that touches the network runs on a worker thread. Starting Tor waits
for a full bootstrap and can take the better part of a minute on a slow link;
testing a chain of three proxies can take longer still.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
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
from app.privacy_doc_content import PRIVACY_DOC_HTML
from server import paths
from services import macaddr, proxychain, tor
from services.socks_client import HTTP, KINDS, SOCKS4, SOCKS5, ProxyHop


class Worker(QObject):
    """Runs one callable off the GUI thread and hands back whatever it returns."""

    done = Signal(object)

    def __init__(self, fn, *args, **kwargs) -> None:
        super().__init__()
        self._fn, self._args, self._kwargs = fn, args, kwargs

    def run(self) -> None:
        try:
            result = self._fn(*self._args, **self._kwargs)
        except Exception as exc:
            result = (False, f"{type(exc).__name__}: {exc}")
        self.done.emit(result)


class HopDialog(QDialog):
    """Add or edit one proxy in the chain."""

    def __init__(self, hop: ProxyHop | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Proxy hop")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self.combo_kind = QComboBox()
        for kind in KINDS:
            self.combo_kind.addItem(kind, kind)
        form.addRow("Type", self.combo_kind)

        self.edit_host = QLineEdit()
        self.edit_host.setPlaceholderText("127.0.0.1")
        form.addRow("Host", self.edit_host)

        self.spin_port = QSpinBox()
        self.spin_port.setRange(1, 65535)
        self.spin_port.setValue(1080)
        form.addRow("Port", self.spin_port)

        self.edit_user = QLineEdit()
        self.edit_user.setPlaceholderText("leave empty if the proxy is open")
        form.addRow("Username", self.edit_user)

        self.edit_password = QLineEdit()
        self.edit_password.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Password", self.edit_password)

        self.edit_label = QLineEdit()
        self.edit_label.setPlaceholderText("optional, e.g. 'Tor' or 'work'")
        form.addRow("Label", self.edit_label)

        layout.addLayout(form)

        note = QLabel(
            "Credentials are stored in a file only you can read, alongside your "
            "server keys — not in the repository."
        )
        note.setWordWrap(True)
        note.setObjectName("StatusValue")
        layout.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if hop is not None:
            self.combo_kind.setCurrentText(hop.kind)
            self.edit_host.setText(hop.host)
            self.spin_port.setValue(hop.port)
            self.edit_user.setText(hop.username)
            self.edit_password.setText(hop.password)
            self.edit_label.setText(hop.label)

    def hop(self) -> ProxyHop:
        return ProxyHop(
            kind=self.combo_kind.currentData(),
            host=self.edit_host.text().strip(),
            port=self.spin_port.value(),
            username=self.edit_user.text().strip(),
            password=self.edit_password.text(),
            label=self.edit_label.text().strip(),
        )


class PrivacyTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._threads: list[QThread] = []
        self._chain = proxychain.load_chain()
        self._guide_dialog = None

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(10)
        header.addWidget(self._build_preamble(), stretch=1)

        self.btn_guide = QPushButton("? Privacy Guide")
        self.btn_guide.setObjectName("HelpButton")
        self.btn_guide.setToolTip(
            "Open the privacy guide.\n\n"
            "Covers what each of these four tools actually hides you from, what it\n"
            "does not, and the two limits that catch people out: chains carry TCP\n"
            "only, and a MAC address travels exactly one hop."
        )
        self.btn_guide.clicked.connect(self.on_open_guide)
        header.addWidget(self.btn_guide, alignment=Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)

        columns = QHBoxLayout()
        columns.setSpacing(12)
        columns.addWidget(self._build_tor_panel(), stretch=1)
        columns.addWidget(self._build_mac_panel(), stretch=1)
        root.addLayout(columns)

        root.addWidget(self._build_chain_panel(), stretch=1)
        root.addWidget(self._build_output(), stretch=1)

        self._refresh_tor()
        self._refresh_interfaces()
        self._refresh_chain()

    # ── Builders ─────────────────────────────────

    def _build_preamble(self) -> QWidget:
        label = QLabel(
            "These narrow three <i>different</i> exposures. Stacking them does not "
            "add up to anonymity — for that the tool is Tor Browser, whose "
            "fingerprinting defences are the hard part and are absent everywhere else."
        )
        label.setWordWrap(True)
        label.setObjectName("StatusValue")
        return label

    def _build_tor_panel(self) -> QGroupBox:
        box = QGroupBox("TOR")
        box.setObjectName("StatusPanel")
        box.setToolTip(
            "Runs a Tor client on this Mac, listening on 127.0.0.1:9250.\n\n"
            "Ports 9250/9251 rather than the usual 9050/9051, so it never fights a\n"
            "system Tor or Tor Browser.\n\n"
            "With the VPN also up, traffic enters the tunnel, leaves at your server,\n"
            "and only then enters Tor — so Tor's guard sees your server rather than\n"
            "your home connection.\n\n"
            "It does NOT make you anonymous: the server is rented in your name, and\n"
            "the exit node still sees anything not end-to-end encrypted."
        )
        layout = QVBoxLayout(box)
        layout.setSpacing(7)

        self.lbl_tor_state = QLabel("—")
        self.lbl_tor_state.setObjectName("StatusValue")
        self.lbl_tor_state.setWordWrap(True)
        layout.addWidget(self.lbl_tor_state)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.btn_tor_toggle = QPushButton("Start Tor")
        self.btn_tor_toggle.setObjectName("ConnectButton")
        self.btn_tor_toggle.setToolTip(
            "Start or stop the Tor client.\n\n"
            "Starting waits for a full bootstrap rather than returning as soon as the\n"
            "port opens — Tor listens well before it has built a circuit, and a request\n"
            "made in that window fails with a confusing SOCKS error."
        )
        self.btn_tor_toggle.clicked.connect(self.on_tor_toggle)
        row.addWidget(self.btn_tor_toggle)

        self.btn_tor_check = QPushButton("Verify")
        self.btn_tor_check.setObjectName("ActionButton")
        self.btn_tor_check.setToolTip(
            "Ask the Tor Project whether this traffic really is exiting through Tor.\n\n"
            "A reachable SOCKS port is not proof it is Tor, and 'I configured it' is\n"
            "not the same as 'it works'."
        )
        self.btn_tor_check.clicked.connect(self.on_tor_check)
        row.addWidget(self.btn_tor_check)

        self.btn_tor_newnym = QPushButton("New Circuit")
        self.btn_tor_newnym.setObjectName("ActionButton")
        self.btn_tor_newnym.setToolTip(
            "Ask Tor for fresh circuits, changing the exit you appear to come from.\n\n"
            "It does not clear what a site already knows about you — cookies, a login,\n"
            "a browser fingerprint all survive. This is not a way to become someone\n"
            "else mid-session."
        )
        self.btn_tor_newnym.clicked.connect(self.on_tor_newnym)
        row.addWidget(self.btn_tor_newnym)
        layout.addLayout(row)

        self.btn_tor_add_hop = QPushButton("Add Tor to the chain")
        self.btn_tor_add_hop.setObjectName("ActionButton")
        self.btn_tor_add_hop.setToolTip(
            "Append this Tor instance to the proxy chain below, so anything routed\n"
            "through the chain goes out via Tor."
        )
        self.btn_tor_add_hop.clicked.connect(self.on_tor_add_hop)
        layout.addWidget(self.btn_tor_add_hop)

        layout.addStretch()
        return box

    def _build_mac_panel(self) -> QGroupBox:
        box = QGroupBox("HARDWARE ADDRESS")
        box.setObjectName("StatusPanel")
        box.setToolTip(
            "Changes the MAC address of a network interface.\n\n"
            "Scope, because this is the most over-estimated measure in common use:\n"
            "a MAC travels exactly ONE hop. The café's access point sees it; nothing\n"
            "beyond the first router ever does. It has no bearing on what a website\n"
            "sees or on what your ISP sees.\n\n"
            "What it is good for: not being recognised by the network you are joining,\n"
            "across visits.\n\n"
            "Does not survive a reboot."
        )
        layout = QVBoxLayout(box)
        layout.setSpacing(7)

        self.combo_iface = QComboBox()
        self.combo_iface.setObjectName("ProfileDropdown")
        self.combo_iface.currentIndexChanged.connect(self._on_iface_changed)
        layout.addWidget(self.combo_iface)

        self.lbl_mac_detail = QLabel("—")
        self.lbl_mac_detail.setObjectName("StatusValue")
        self.lbl_mac_detail.setWordWrap(True)
        layout.addWidget(self.lbl_mac_detail)

        self.combo_mac_mode = QComboBox()
        self.combo_mac_mode.addItem("Locally administered (correct, but visibly random)",
                                    macaddr.MODE_LOCAL)
        self.combo_mac_mode.addItem("Keep vendor prefix (less conspicuous)",
                                    macaddr.MODE_SAME_VENDOR)
        self.combo_mac_mode.setToolTip(
            "Locally administered sets the bit that marks an address as not belonging\n"
            "to any manufacturer. It is the correct thing to do and cannot collide with\n"
            "real hardware — but that same bit tells anyone looking that the address\n"
            "was made up.\n\n"
            "Keeping the vendor prefix reuses the first three octets of your real\n"
            "address, so the interface still looks like the same make of hardware."
        )
        layout.addWidget(self.combo_mac_mode)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.btn_mac_random = QPushButton("Randomise")
        self.btn_mac_random.setObjectName("ConnectButton")
        self.btn_mac_random.clicked.connect(self.on_mac_randomise)
        row.addWidget(self.btn_mac_random)

        self.btn_mac_restore = QPushButton("Restore")
        self.btn_mac_restore.setObjectName("ActionButton")
        self.btn_mac_restore.setToolTip("Put back the address the hardware shipped with.")
        self.btn_mac_restore.clicked.connect(self.on_mac_restore)
        row.addWidget(self.btn_mac_restore)
        layout.addLayout(row)

        layout.addStretch()
        return box

    def _build_chain_panel(self) -> QGroupBox:
        box = QGroupBox("PROXY CHAIN")
        box.setObjectName("StatusPanel")
        box.setToolTip(
            "Routes through several proxies in sequence, so no single one sees both\n"
            "who you are and where you are going.\n\n"
            "Two limits worth knowing:\n"
            "  • Chains carry TCP only. UDP, and so ordinary DNS and QUIC, does not\n"
            "    traverse SOCKS — it either fails or bypasses the chain.\n"
            "  • On macOS, proxychains-ng is largely defeated by System Integrity\n"
            "    Protection. Test uses this app's own SOCKS implementation instead,\n"
            "    so it works regardless."
        )
        layout = QVBoxLayout(box)
        layout.setSpacing(8)

        self.list_hops = QListWidget()
        self.list_hops.setObjectName("PeerList")
        self.list_hops.setMinimumHeight(90)
        self.list_hops.itemSelectionChanged.connect(self._update_chain_buttons)
        layout.addWidget(self.list_hops, stretch=1)

        row = QHBoxLayout()
        row.setSpacing(6)
        for text, slot, style in (
            ("Add Hop", self.on_hop_add, "ConnectButton"),
            ("Edit", self.on_hop_edit, "ActionButton"),
            ("Remove", self.on_hop_remove, "DisconnectButton"),
            ("Move Up", lambda: self.on_hop_move(-1), "ActionButton"),
            ("Move Down", lambda: self.on_hop_move(1), "ActionButton"),
        ):
            button = QPushButton(text)
            button.setObjectName(style)
            button.clicked.connect(slot)
            row.addWidget(button)
            setattr(self, f"_btn_{text.lower().replace(' ', '_')}", button)
        layout.addLayout(row)

        row2 = QHBoxLayout()
        row2.setSpacing(6)

        self.combo_chain_mode = QComboBox()
        for mode in proxychain.MODES:
            self.combo_chain_mode.addItem(mode, mode)
        self.combo_chain_mode.setToolTip(
            "strict  — every proxy, in the order listed. Fails if any is down.\n"
            "dynamic — same order, skipping any that are unreachable.\n"
            "random  — a random subset each time.\n\n"
            "Only affects the generated proxychains.conf. Test always walks the\n"
            "full chain in order."
        )
        self.combo_chain_mode.currentIndexChanged.connect(self._on_chain_mode_changed)
        row2.addWidget(self.combo_chain_mode)

        self.btn_chain_test = QPushButton("Test Chain")
        self.btn_chain_test.setObjectName("ConnectButton")
        self.btn_chain_test.setToolTip(
            "Send real traffic through every hop and report the address it comes out\n"
            "of. Speaks SOCKS directly, so this is a genuine end-to-end test even where\n"
            "proxychains itself would be defeated by SIP."
        )
        self.btn_chain_test.clicked.connect(self.on_chain_test)
        row2.addWidget(self.btn_chain_test)

        self.btn_chain_export = QPushButton("Save proxychains.conf")
        self.btn_chain_export.setObjectName("ActionButton")
        self.btn_chain_export.setToolTip(
            "Write a proxychains-ng config for wrapping other programs.\n\n"
            "On macOS this only works for binaries you installed yourself — SIP strips\n"
            "the injection from anything Apple ships, and /usr/bin/curl will connect\n"
            "directly while looking like it worked."
        )
        self.btn_chain_export.clicked.connect(self.on_chain_export)
        row2.addWidget(self.btn_chain_export)

        row2.addStretch()
        layout.addLayout(row2)

        return box

    def _build_output(self) -> QGroupBox:
        box = QGroupBox("OUTPUT")
        box.setObjectName("StatusPanel")
        layout = QVBoxLayout(box)
        self.output = QPlainTextEdit()
        self.output.setObjectName("DeployOutput")
        self.output.setReadOnly(True)
        self.output.setMinimumHeight(90)
        layout.addWidget(self.output)
        return box

    def on_open_guide(self) -> None:
        # Held on the instance so a non-modal dialog is not collected the moment
        # this method returns.
        if self._guide_dialog is None or not self._guide_dialog.isVisible():
            self._guide_dialog = DocDialog(
                PRIVACY_DOC_HTML, "PRIVACY TOOLS", parent=self
            )
            self._guide_dialog.show()
        else:
            self._guide_dialog.raise_()
            self._guide_dialog.activateWindow()

    # ── Tor ──────────────────────────────────────

    def _refresh_tor(self) -> None:
        if not tor.is_installed():
            self.lbl_tor_state.setText(
                f"Tor is not installed.  Install it with:  {tor.install_hint()}"
            )
            self.btn_tor_toggle.setEnabled(False)
            for button in (self.btn_tor_check, self.btn_tor_newnym, self.btn_tor_add_hop):
                button.setEnabled(False)
            return

        running = tor.is_running()
        self.btn_tor_toggle.setEnabled(True)
        self.btn_tor_toggle.setText("Stop Tor" if running else "Start Tor")
        for button in (self.btn_tor_check, self.btn_tor_newnym, self.btn_tor_add_hop):
            button.setEnabled(running)
        self.lbl_tor_state.setText(
            f"Running — SOCKS5 on 127.0.0.1:{tor.SOCKS_PORT}"
            if running
            else "Installed, not running."
        )

    def on_tor_toggle(self) -> None:
        if tor.is_running():
            self._append("Stopping Tor…")
            self._start(tor.stop, label="tor")
        else:
            self._append("Starting Tor — this waits for a full bootstrap…")
            self._start(tor.start, label="tor")

    def on_tor_check(self) -> None:
        self._append("Asking the Tor Project where this traffic appears to come from…")
        self._start(tor.check, label="tor")

    def on_tor_newnym(self) -> None:
        self._start(tor.new_identity, label="tor")

    def on_tor_add_hop(self) -> None:
        hop = tor.hop()
        if any(h.host == hop.host and h.port == hop.port for h in self._chain.hops):
            self._append("Tor is already in the chain.")
            return
        self._chain.hops.append(hop)
        proxychain.save_chain(self._chain)
        self._append(f"Added {hop.describe()} to the chain.")
        self._refresh_chain()

    # ── MAC ──────────────────────────────────────

    def _refresh_interfaces(self) -> None:
        current = self.combo_iface.currentData()
        self.combo_iface.blockSignals(True)
        self.combo_iface.clear()
        for interface in macaddr.list_interfaces():
            self.combo_iface.addItem(interface.describe(), interface.device)
        if current:
            index = self.combo_iface.findData(current)
            if index >= 0:
                self.combo_iface.setCurrentIndex(index)
        self.combo_iface.blockSignals(False)
        self._on_iface_changed()

    def _on_iface_changed(self) -> None:
        device = self.combo_iface.currentData()
        interface = macaddr.get_interface(device) if device else None
        if interface is None:
            self.lbl_mac_detail.setText("—")
            return

        detail = [f"In use: {interface.current or 'none'}",
                  f"Hardware: {interface.hardware or 'unknown'}"]
        if interface.spoofed and interface.is_wifi:
            # Almost always macOS's own feature rather than anything the user did.
            detail.append(
                "Already differs from the hardware address — on Wi-Fi this is normally "
                "macOS's own Private Wi-Fi Address, not something you set."
            )
        elif interface.spoofed:
            detail.append("Currently using a changed address.")
        if interface.is_wifi:
            detail.append(macaddr.wifi_private_address_note())

        self.lbl_mac_detail.setText("\n".join(detail))

    def on_mac_randomise(self) -> None:
        device = self.combo_iface.currentData()
        if not device:
            return
        interface = macaddr.get_interface(device)
        warning = ""
        if interface is not None and interface.is_wifi:
            warning = (
                "\n\nWi-Fi will be switched off and on to apply this, so you will drop "
                "off the network and may need to rejoin."
            )
        if not self._confirm(
            "Randomise the hardware address?",
            f"Changes the MAC of {device}.\n\nThis is visible only to the network you "
            f"are joined to — it changes nothing about what websites or your ISP see, "
            f"and it does not survive a reboot.{warning}",
        ):
            return
        mode = self.combo_mac_mode.currentData()
        self._append(f"Changing {device}…")
        self._start(macaddr.randomize, device, mode, label="mac")

    def on_mac_restore(self) -> None:
        device = self.combo_iface.currentData()
        if not device:
            return
        self._append(f"Restoring {device} to its hardware address…")
        self._start(macaddr.restore, device, label="mac")

    # ── Chain ────────────────────────────────────

    def _refresh_chain(self) -> None:
        self.list_hops.clear()
        for index, hop in enumerate(self._chain.hops, start=1):
            item = QListWidgetItem(f"{index}.  {hop.describe()}")
            item.setData(Qt.ItemDataRole.UserRole, index - 1)
            self.list_hops.addItem(item)

        mode_index = self.combo_chain_mode.findData(self._chain.mode)
        if mode_index >= 0:
            self.combo_chain_mode.blockSignals(True)
            self.combo_chain_mode.setCurrentIndex(mode_index)
            self.combo_chain_mode.blockSignals(False)
        self._update_chain_buttons()

    def _update_chain_buttons(self) -> None:
        selected = self.list_hops.currentRow() >= 0
        for name in ("edit", "remove", "move_up", "move_down"):
            button = getattr(self, f"_btn_{name}", None)
            if button is not None:
                button.setEnabled(selected)
        self.btn_chain_test.setEnabled(bool(self._chain.hops))
        self.btn_chain_export.setEnabled(bool(self._chain.hops))

    def _on_chain_mode_changed(self) -> None:
        self._chain.mode = self.combo_chain_mode.currentData()
        proxychain.save_chain(self._chain)

    def on_hop_add(self) -> None:
        dialog = HopDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        hop = dialog.hop()
        problems = hop.problems()
        if problems:
            self._warn("Not a usable proxy", "\n".join(problems))
            return
        self._chain.hops.append(hop)
        proxychain.save_chain(self._chain)
        self._append(f"Added {hop.describe()}.")
        self._refresh_chain()

    def on_hop_edit(self) -> None:
        row = self.list_hops.currentRow()
        if row < 0:
            return
        dialog = HopDialog(self._chain.hops[row], parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        hop = dialog.hop()
        problems = hop.problems()
        if problems:
            self._warn("Not a usable proxy", "\n".join(problems))
            return
        self._chain.hops[row] = hop
        proxychain.save_chain(self._chain)
        self._refresh_chain()

    def on_hop_remove(self) -> None:
        row = self.list_hops.currentRow()
        if row < 0:
            return
        removed = self._chain.hops.pop(row)
        proxychain.save_chain(self._chain)
        self._append(f"Removed {removed.describe()}.")
        self._refresh_chain()

    def on_hop_move(self, delta: int) -> None:
        row = self.list_hops.currentRow()
        target = row + delta
        if row < 0 or not (0 <= target < len(self._chain.hops)):
            return
        hops = self._chain.hops
        hops[row], hops[target] = hops[target], hops[row]
        proxychain.save_chain(self._chain)
        self._refresh_chain()
        self.list_hops.setCurrentRow(target)

    def on_chain_test(self) -> None:
        self._append(f"Testing:  {self._chain.describe()}")
        for problem in self._chain.problems():
            self._append(f"   note: {problem}")
        self._start(proxychain.probe, self._chain, label="chain")

    def on_chain_export(self) -> None:
        default = str(Path.home() / "proxychains.conf")
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save proxychains config", default, "Config files (*.conf)"
        )
        if not filename:
            return
        written = proxychain.write_proxychains_conf(self._chain, Path(filename))
        self._append(f"Wrote {written}")
        self._append(
            "   On macOS this only affects binaries you installed yourself; SIP strips "
            "the injection from anything Apple ships. Always check the exit address."
        )

    # ── Threading ────────────────────────────────

    def _start(self, fn, *args, label: str) -> None:
        thread = QThread()
        worker = Worker(fn, *args)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(lambda result: self._on_done(result, label))
        worker.done.connect(thread.quit)
        worker.done.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(
            lambda: self._threads.remove(thread) if thread in self._threads else None
        )
        self._threads.append(thread)
        self._set_busy(True)
        thread.start()

    def _on_done(self, result, label: str) -> None:
        self._set_busy(False)

        if label == "chain":
            self._append(result.summary())
            return

        ok, message = result if isinstance(result, tuple) else (False, str(result))
        self._append(message)
        if label == "tor":
            self._refresh_tor()
        elif label == "mac":
            self._refresh_interfaces()
        if not ok and label == "mac":
            self._warn("Could not change the address", message)

    def _set_busy(self, busy: bool) -> None:
        for button in (self.btn_tor_toggle, self.btn_tor_check, self.btn_tor_newnym,
                       self.btn_mac_random, self.btn_mac_restore, self.btn_chain_test):
            button.setEnabled(not busy)
        if not busy:
            self._refresh_tor()
            self._update_chain_buttons()

    def shutdown(self) -> None:
        """Stop workers before Qt destroys the widgets they would report into."""
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
        return QMessageBox.question(
            self, title, text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes
