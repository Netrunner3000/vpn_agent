"""
gui.py — Main window for VPN Agent.
Displays: public IP, DNS status, latency, VPN tunnel status, profile selector.
All network calls run in background QThread workers to keep the GUI responsive.
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QGroupBox,
    QSizePolicy, QFrame,
)
from PySide6.QtCore import Qt, QThread, Signal, QObject, QEvent
from PySide6.QtWidgets import QApplication

from app.styles import DARK_STYLESHEET
from app.doc_dialog import DocDialog
from services import public_ip, dns_check, latency, profile_store, wireguard_manager
from services.health_monitor import HealthMonitor


# ──────────────────────────────────────────────
# Tooltip filter — installed on QApplication to suppress all tooltips
# ──────────────────────────────────────────────

class TooltipFilter(QObject):
    """Event filter that swallows ToolTip events so no tooltips appear."""
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.ToolTip:
            return True  # consume — tooltip is suppressed
        return False


# ──────────────────────────────────────────────
# Background worker: runs a function, emits result
# ──────────────────────────────────────────────

class Worker(QObject):
    """Generic background worker that runs a callable and emits its result."""
    result = Signal(object)
    finished = Signal()

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            output = self._fn(*self._args, **self._kwargs)
        except Exception as e:
            output = {"error": str(e)}
        self.result.emit(output)
        self.finished.emit()


# ──────────────────────────────────────────────
# Main Window
# ──────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VPN Agent")
        self.setMinimumSize(760, 620)
        self.setStyleSheet(DARK_STYLESHEET)

        self._threads = []
        self._doc_dialog = None       # keep a reference so it stays open
        self._health_monitor = None   # set before UI build to guard against early signal
        self._tooltip_filter = TooltipFilter()
        self._tooltips_enabled = True

        # Build UI
        central = QWidget()
        central.setObjectName("CentralWidget")
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(24, 20, 24, 20)
        root_layout.setSpacing(14)

        root_layout.addWidget(self._build_title_bar())
        root_layout.addWidget(self._build_warning_banner())  # hidden by default
        root_layout.addWidget(self._build_profile_row())
        root_layout.addWidget(self._build_status_panels())
        root_layout.addWidget(self._build_action_buttons())
        root_layout.addWidget(self._build_log_area())

        self._init_health_monitor()  # must come before _refresh_profiles
        self._refresh_profiles()     # triggers currentTextChanged which needs _health_monitor

        self._log("VPN Agent started.")
        self.on_refresh()

    # ── UI builders ──────────────────────────────

    def _build_title_bar(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        title = QLabel("VPN AGENT")
        title.setObjectName("AppTitle")
        layout.addWidget(title)

        layout.addStretch()

        self.lbl_tunnel_indicator = QLabel("● TUNNEL: UNKNOWN")
        self.lbl_tunnel_indicator.setObjectName("StatusNeutral")
        self.lbl_tunnel_indicator.setToolTip(
            "Shows which WireGuard tunnels are currently active on your system.\n"
            "NONE = no tunnel — your traffic is going through your ISP directly.\n"
            "When connected, the interface name (e.g. WG2) should appear here."
        )
        layout.addWidget(self.lbl_tunnel_indicator)

        self.btn_tooltips = QPushButton("Tooltips: On")
        self.btn_tooltips.setObjectName("HelpButton")
        self.btn_tooltips.setToolTip("Toggle all tooltip hints on or off.")
        self.btn_tooltips.clicked.connect(self._toggle_tooltips)
        layout.addWidget(self.btn_tooltips)

        btn_help = QPushButton("? Docs")
        btn_help.setObjectName("HelpButton")
        btn_help.setToolTip("Open the full VPN Agent guide — setup, VPS configuration, tips, and troubleshooting.")
        btn_help.clicked.connect(self.on_open_docs)
        layout.addWidget(btn_help)

        return container

    def _build_warning_banner(self) -> QFrame:
        """Red warning banner shown when the health monitor detects a problem."""
        self.warning_banner = QFrame()
        self.warning_banner.setObjectName("WarningBanner")
        self.warning_banner.setVisible(False)

        layout = QHBoxLayout(self.warning_banner)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        icon = QLabel("⚠")
        icon.setObjectName("WarningIcon")
        icon.setFixedWidth(22)
        layout.addWidget(icon)

        self.lbl_warning_text = QLabel("")
        self.lbl_warning_text.setObjectName("WarningText")
        self.lbl_warning_text.setWordWrap(True)
        layout.addWidget(self.lbl_warning_text, stretch=1)

        btn_dismiss = QPushButton("Dismiss")
        btn_dismiss.setObjectName("DismissButton")
        btn_dismiss.setToolTip("Hide this warning. The event is still recorded in the activity log.")
        btn_dismiss.clicked.connect(self._dismiss_warning)
        layout.addWidget(btn_dismiss)

        return self.warning_banner

    def _build_profile_row(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        lbl = QLabel("ACTIVE PROFILE")
        lbl.setObjectName("SectionHeader")
        layout.addWidget(lbl)

        self.combo_profiles = QComboBox()
        self.combo_profiles.setObjectName("ProfileDropdown")
        self.combo_profiles.setToolTip(
            "Select which VPN profile to use.\n"
            "Connect / Disconnect / Restart and latency tests all use the selected profile.\n"
            "Profiles are defined in config/vpn_profiles.json."
        )
        self.combo_profiles.currentTextChanged.connect(self._on_profile_changed)
        layout.addWidget(self.combo_profiles)

        layout.addStretch()
        return container

    def _build_status_panels(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        layout.addWidget(self._make_status_panel_ip())
        layout.addWidget(self._make_status_panel_dns())
        layout.addWidget(self._make_status_panel_latency())

        return container

    def _make_status_panel_ip(self) -> QGroupBox:
        box = QGroupBox("PUBLIC IP")
        box.setObjectName("StatusPanel")
        box.setToolTip(
            "Your current outbound IP address as seen by the internet.\n\n"
            "When VPN is active:\n"
            "  - IP should show your VPS or server IP\n"
            "  - Country should show your server's location\n"
            "  - ISP should show your hosting provider\n\n"
            "If these still show your home details after connecting,\n"
            "your routing config is not working correctly."
        )
        layout_box = QVBoxLayout(box)
        layout_box.setSpacing(6)

        self.lbl_ip = QLabel("—")
        self.lbl_ip.setObjectName("StatusValue")
        layout_box.addWidget(self.lbl_ip)

        self.lbl_country = QLabel("Country: —")
        self.lbl_country.setObjectName("StatusValue")
        layout_box.addWidget(self.lbl_country)

        self.lbl_org = QLabel("ISP: —")
        self.lbl_org.setObjectName("StatusValue")
        layout_box.addWidget(self.lbl_org)

        layout_box.addStretch()
        return box

    def _make_status_panel_dns(self) -> QGroupBox:
        box = QGroupBox("DNS STATUS")
        box.setObjectName("StatusPanel")
        box.setToolTip(
            "Shows which DNS servers your system is currently sending queries to.\n\n"
            "DNS leaks happen when DNS queries bypass the VPN tunnel and\n"
            "go to your ISP's resolver — revealing your browsing even when\n"
            "your IP is hidden.\n\n"
            "Fix leaks by adding DNS = 1.1.1.1 to your WireGuard client config.\n\n"
            "Green = known public resolvers (Cloudflare, Google, Quad9)\n"
            "Orange = possible leak or unknown private resolver"
        )
        layout_box = QVBoxLayout(box)
        layout_box.setSpacing(6)

        self.lbl_dns_status = QLabel("—")
        self.lbl_dns_status.setObjectName("StatusValue")
        layout_box.addWidget(self.lbl_dns_status)

        self.lbl_dns_servers = QLabel("Resolvers: —")
        self.lbl_dns_servers.setObjectName("StatusValue")
        self.lbl_dns_servers.setWordWrap(True)
        layout_box.addWidget(self.lbl_dns_servers)

        layout_box.addStretch()
        return box

    def _make_status_panel_latency(self) -> QGroupBox:
        box = QGroupBox("LATENCY")
        box.setObjectName("StatusPanel")
        box.setToolTip(
            "Round-trip time to the selected profile's endpoint.\n\n"
            "Uses ICMP ping (wg server or endpoint IP).\n"
            "Falls back to TCP connect timing if ICMP is blocked.\n\n"
            "< 50 ms   — Excellent\n"
            "50–150 ms — Acceptable\n"
            "> 150 ms  — High — may impact real-time apps\n\n"
            "High packet loss (>1%) usually indicates a routing issue\n"
            "or an overloaded VPN server."
        )
        layout_box = QVBoxLayout(box)
        layout_box.setSpacing(6)

        self.lbl_latency = QLabel("—")
        self.lbl_latency.setObjectName("StatusValue")
        layout_box.addWidget(self.lbl_latency)

        self.lbl_latency_host = QLabel("Target: 1.1.1.1")
        self.lbl_latency_host.setObjectName("StatusValue")
        layout_box.addWidget(self.lbl_latency_host)

        self.lbl_packet_loss = QLabel("Packet loss: —")
        self.lbl_packet_loss.setObjectName("StatusValue")
        layout_box.addWidget(self.lbl_packet_loss)

        layout_box.addStretch()
        return box

    def _build_action_buttons(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        btn_refresh = QPushButton("Refresh Status")
        btn_refresh.setObjectName("ActionButton")
        btn_refresh.setToolTip(
            "Re-run all checks: public IP, DNS resolvers, latency, and tunnel state.\n"
            "Use this after connecting or disconnecting to confirm the changes took effect."
        )
        btn_refresh.clicked.connect(self.on_refresh)
        layout.addWidget(btn_refresh)

        btn_connect = QPushButton("Connect")
        btn_connect.setObjectName("ConnectButton")
        btn_connect.setToolTip(
            "Bring up the WireGuard tunnel for the selected profile.\n\n"
            "Requirements:\n"
            "  - wireguard-tools installed: brew install wireguard-tools\n"
            "  - A .conf file at /etc/wireguard/<interface>.conf\n"
            "  - sudo access (macOS will prompt for your password)\n\n"
            "After connecting, press Refresh Status to verify the IP changed."
        )
        btn_connect.clicked.connect(self.on_connect)
        layout.addWidget(btn_connect)

        btn_disconnect = QPushButton("Disconnect")
        btn_disconnect.setObjectName("DisconnectButton")
        btn_disconnect.setToolTip(
            "Bring down the active WireGuard tunnel.\n\n"
            "Your traffic will immediately revert to your ISP connection.\n"
            "No kill switch is active — traffic is unprotected after disconnecting."
        )
        btn_disconnect.clicked.connect(self.on_disconnect)
        layout.addWidget(btn_disconnect)

        btn_restart = QPushButton("Restart")
        btn_restart.setObjectName("ActionButton")
        btn_restart.setToolTip(
            "Disconnect then reconnect the tunnel.\n\n"
            "Use this after editing your WireGuard .conf file or\n"
            "when the tunnel is up but not passing traffic correctly."
        )
        btn_restart.clicked.connect(self.on_restart)
        layout.addWidget(btn_restart)

        btn_dns = QPushButton("Test DNS Leak")
        btn_dns.setObjectName("ActionButton")
        btn_dns.setToolTip(
            "Check which DNS servers your system is currently using.\n\n"
            "Run this after connecting to verify DNS queries are going\n"
            "through the VPN tunnel and not to your ISP's resolver.\n\n"
            "Fix leaks: add DNS = 1.1.1.1 to your WireGuard client config."
        )
        btn_dns.clicked.connect(self.on_dns_test)
        layout.addWidget(btn_dns)

        btn_latency = QPushButton("Test Latency")
        btn_latency.setObjectName("ActionButton")
        btn_latency.setToolTip(
            "Ping the selected profile's endpoint and measure round-trip time.\n\n"
            "Use this to:\n"
            "  - Verify the VPN server is reachable\n"
            "  - Compare latency before and after connecting\n"
            "  - Diagnose slow VPN performance"
        )
        btn_latency.clicked.connect(self.on_latency_test)
        layout.addWidget(btn_latency)

        layout.addStretch()
        return container

    def _build_log_area(self) -> QGroupBox:
        box = QGroupBox("ACTIVITY LOG")
        box.setObjectName("StatusPanel")
        box.setToolTip(
            "Running log of all events, status checks, and warnings.\n"
            "Most recent entries appear at the top.\n"
            "Health monitor warnings also appear here even after you dismiss the banner."
        )
        layout_box = QVBoxLayout(box)

        self.lbl_log = QLabel("Starting up…")
        self.lbl_log.setObjectName("LogArea")
        self.lbl_log.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.lbl_log.setWordWrap(True)
        self.lbl_log.setMinimumHeight(120)
        self.lbl_log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout_box.addWidget(self.lbl_log)

        return box

    # ── Health monitor ────────────────────────────

    def _init_health_monitor(self) -> None:
        self._health_monitor = HealthMonitor(interval_seconds=30, parent=self)
        self._health_monitor.warning.connect(self._on_health_warning)
        self._health_monitor.info.connect(self._log)
        self._health_monitor.tunnel_dropped.connect(self._on_tunnel_dropped)
        self._health_monitor.tunnel_up.connect(self._update_tunnel_indicator)
        self._health_monitor.start()

    def _update_watched_interfaces(self) -> None:
        """Tell the health monitor which interfaces to watch for the current profile."""
        if self._health_monitor is None:
            return
        interface = self._get_selected_interface()
        if interface:
            self._health_monitor.set_watched_interfaces([interface])

    def _on_health_warning(self, msg: str) -> None:
        self._log(f"WARNING: {msg}")
        self._show_warning(msg)

    def _on_tunnel_dropped(self, iface: str) -> None:
        self._update_tunnel_indicator()

    # ── Warning banner ────────────────────────────

    def _show_warning(self, msg: str) -> None:
        self.lbl_warning_text.setText(msg)
        self.warning_banner.setVisible(True)

    def _dismiss_warning(self) -> None:
        self.warning_banner.setVisible(False)

    # ── Helpers ──────────────────────────────────

    def _toggle_tooltips(self) -> None:
        """Enable or disable all tooltips application-wide."""
        self._tooltips_enabled = not self._tooltips_enabled
        app = QApplication.instance()
        if self._tooltips_enabled:
            app.removeEventFilter(self._tooltip_filter)
            self.btn_tooltips.setText("Tooltips: On")
        else:
            app.installEventFilter(self._tooltip_filter)
            self.btn_tooltips.setText("Tooltips: Off")

    def _log(self, message: str) -> None:
        current = self.lbl_log.text()
        if current == "Starting up…":
            current = ""
        lines = (message + "\n" + current).splitlines()
        self.lbl_log.setText("\n".join(lines[:30]))

    def _refresh_profiles(self) -> None:
        names = profile_store.get_profile_names()
        self.combo_profiles.clear()
        if names:
            self.combo_profiles.addItems(names)
            active = profile_store.get_active_profile_name()
            if active and active in names:
                self.combo_profiles.setCurrentText(active)
        else:
            self.combo_profiles.addItem("No profiles configured")

    def _get_selected_interface(self) -> str | None:
        name = self.combo_profiles.currentText()
        profile = profile_store.get_profile_by_name(name)
        if profile:
            return profile.get("interface")
        return None

    def _run_in_thread(self, fn, *args, on_result=None) -> None:
        thread = QThread()
        worker = Worker(fn, *args)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        if on_result:
            worker.result.connect(on_result)
        self._threads.append(thread)
        thread.finished.connect(
            lambda: self._threads.remove(thread) if thread in self._threads else None
        )
        thread.start()

    def _update_tunnel_indicator(self, _iface: str = "") -> None:
        active = wireguard_manager.list_active_tunnels()
        if active:
            self.lbl_tunnel_indicator.setText(f"● TUNNEL: {', '.join(active).upper()}")
            self.lbl_tunnel_indicator.setObjectName("StatusOk")
        else:
            self.lbl_tunnel_indicator.setText("● TUNNEL: NONE")
            self.lbl_tunnel_indicator.setObjectName("StatusNeutral")
        self.lbl_tunnel_indicator.style().unpolish(self.lbl_tunnel_indicator)
        self.lbl_tunnel_indicator.style().polish(self.lbl_tunnel_indicator)

    def _restyle(self, widget, object_name: str) -> None:
        """Change a widget's objectName and force stylesheet re-evaluation."""
        widget.setObjectName(object_name)
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    # ── Result handlers ──────────────────────────

    def _on_ip_result(self, details: dict) -> None:
        ip = details.get("ip", "Unknown")
        country = details.get("country", "Unknown")
        org = details.get("org", "Unknown")

        self.lbl_ip.setText(ip)
        self.lbl_country.setText(f"Country: {country}")
        self.lbl_org.setText(f"ISP: {org}")

        if "Error" in ip or "error" in str(details.get("error", "")):
            self._restyle(self.lbl_ip, "StatusError")
        else:
            self._restyle(self.lbl_ip, "StatusOk")

        self._log(f"Public IP: {ip} ({country})")

    def _on_dns_result(self, result: dict) -> None:
        status = result.get("status", "Unknown")
        labels = result.get("labels", [])
        leak = result.get("leak_risk", False)

        self.lbl_dns_status.setText(status)
        self.lbl_dns_servers.setText(
            "Resolvers:\n" + "\n".join(labels) if labels else "No resolvers found"
        )

        self._restyle(self.lbl_dns_status, "StatusWarn" if leak else "StatusOk")

        if leak:
            self._show_warning(
                "Possible DNS leak detected — your ISP may see your DNS queries. "
                "Add DNS = 1.1.1.1 to your WireGuard client config and reconnect."
            )
        self._log(f"DNS check: {status}")

    def _on_latency_result(self, result: dict) -> None:
        ms = result.get("latency_ms")
        loss = result.get("packet_loss_pct")
        status = result.get("status", "Unknown")
        method = result.get("method", "")

        if ms is not None:
            self.lbl_latency.setText(f"{ms} ms  ({method})")
            if ms < 50:
                self._restyle(self.lbl_latency, "StatusOk")
            elif ms < 150:
                self._restyle(self.lbl_latency, "StatusWarn")
            else:
                self._restyle(self.lbl_latency, "StatusError")
                self._show_warning(
                    f"High latency to {result.get('host', 'endpoint')}: {ms} ms. "
                    "VPN server may be overloaded or your route is poor."
                )
        else:
            self.lbl_latency.setText(status)
            self._restyle(self.lbl_latency, "StatusError")

        loss_str = f"{loss}%" if loss is not None else "—"
        self.lbl_packet_loss.setText(f"Packet loss: {loss_str}")

        if loss is not None and loss > 5:
            self._show_warning(
                f"Packet loss {loss}% to endpoint. "
                "This will degrade VPN performance. Check server health."
            )

        self._log(f"Latency: {ms} ms  Loss: {loss_str}  ({status})")

    # ── Button handlers ──────────────────────────

    def _on_profile_changed(self, name: str) -> None:
        profile_store.set_active_profile(name)
        profile = profile_store.get_profile_by_name(name)
        if profile:
            host = profile.get("endpoint", "1.1.1.1")
            self.lbl_latency_host.setText(f"Target: {host}")
            self._log(f"Profile selected: {name}")
        self._update_watched_interfaces()

    def on_refresh(self) -> None:
        self._log("Refreshing status…")
        self._update_tunnel_indicator()
        self._run_in_thread(public_ip.get_ip_details, on_result=self._on_ip_result)
        self._run_in_thread(dns_check.check_dns_leak, on_result=self._on_dns_result)

        profile = profile_store.get_profile_by_name(self.combo_profiles.currentText())
        host = profile.get("endpoint", "1.1.1.1") if profile else "1.1.1.1"
        self._run_in_thread(latency.measure_latency, host, on_result=self._on_latency_result)

    def on_connect(self) -> None:
        interface = self._get_selected_interface()
        if not interface:
            self._log("Connect: no interface found in selected profile.")
            return

        if not wireguard_manager.is_wg_quick_available():
            self._show_warning(
                "wg-quick not found. Install wireguard-tools first:\n"
                "  brew install wireguard-tools\n"
                "Then ensure your .conf file exists at /etc/wireguard/<interface>.conf"
            )
            self._log("Connect failed: wg-quick not installed.")
            return

        self._log(f"Connecting tunnel: {interface}…")

        def do_connect():
            return wireguard_manager.connect(interface)

        def on_result(r):
            if r.get("success"):
                self._log(f"Connected: {interface}. Press Refresh Status to verify IP changed.")
                self._dismiss_warning()
                self._update_watched_interfaces()
            else:
                err = r.get("error", "Unknown error")
                self._log(f"Connect failed: {err}")
                self._show_warning(
                    f"Connect failed for {interface}: {err}\n"
                    "Check: wg-quick installed, .conf file exists, sudo access granted."
                )
            self._update_tunnel_indicator()

        self._run_in_thread(do_connect, on_result=on_result)

    def on_disconnect(self) -> None:
        interface = self._get_selected_interface()
        if not interface:
            self._log("Disconnect: no interface found in selected profile.")
            return
        self._log(f"Disconnecting tunnel: {interface}…")

        def do_disconnect():
            return wireguard_manager.disconnect(interface)

        def on_result(r):
            if r.get("success"):
                self._log(f"Disconnected: {interface}. Traffic is now on your ISP connection.")
            else:
                self._log(f"Disconnect failed: {r.get('error', 'Unknown error')}")
            self._update_tunnel_indicator()

        self._run_in_thread(do_disconnect, on_result=on_result)

    def on_restart(self) -> None:
        interface = self._get_selected_interface()
        if not interface:
            self._log("Restart: no interface found in selected profile.")
            return
        self._log(f"Restarting tunnel: {interface}…")

        def do_restart():
            return wireguard_manager.restart(interface)

        def on_result(r):
            if r.get("success"):
                self._log(f"Restarted: {interface}.")
                self._dismiss_warning()
            else:
                self._log(f"Restart failed: {r.get('error', 'Unknown error')}")
            self._update_tunnel_indicator()

        self._run_in_thread(do_restart, on_result=on_result)

    def on_dns_test(self) -> None:
        self._log("Running DNS leak test…")
        self._run_in_thread(dns_check.check_dns_leak, on_result=self._on_dns_result)

    def on_latency_test(self) -> None:
        profile = profile_store.get_profile_by_name(self.combo_profiles.currentText())
        host = profile.get("endpoint", "1.1.1.1") if profile else "1.1.1.1"
        self._log(f"Testing latency to {host}…")
        self._run_in_thread(latency.measure_latency, host, on_result=self._on_latency_result)

    def on_open_docs(self) -> None:
        if self._doc_dialog is None or not self._doc_dialog.isVisible():
            self._doc_dialog = DocDialog(parent=self)
            self._doc_dialog.show()
        else:
            self._doc_dialog.raise_()
            self._doc_dialog.activateWindow()

    def closeEvent(self, event) -> None:
        """
        Hard-stop all background threads before Qt destroys any objects.

        Why this is non-trivial:
          - Worker threads don't run a Qt event loop, so thread.quit() is a no-op.
          - thread.wait(N) can time out while a network request is still blocking.
          - If a QThread object is garbage-collected while its thread is still
            running, Qt calls std::abort() → macOS shows 'Python quit unexpectedly'.

        Fix: disconnect all signals first (so no callback fires into a dying object),
        then quit+wait with a short timeout, then hard-terminate anything left alive.
        """
        # 1. Disconnect health monitor signals immediately — prevents any
        #    in-flight thread from firing a callback into this window
        if self._health_monitor is not None:
            self._health_monitor.stop()
            for sig in (
                self._health_monitor.warning,
                self._health_monitor.info,
                self._health_monitor.tunnel_dropped,
                self._health_monitor.tunnel_up,
            ):
                try:
                    sig.disconnect()
                except RuntimeError:
                    pass

        # 2. For every main-window thread: ask it to stop, wait briefly,
        #    then terminate() hard if it's still alive
        for thread in list(self._threads):
            if thread.isRunning():
                thread.quit()
                if not thread.wait(1500):       # wait up to 1.5 s
                    thread.terminate()          # force-kill the thread
                    thread.wait()               # wait for termination to complete
        self._threads.clear()

        event.accept()
