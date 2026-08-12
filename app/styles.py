"""
styles.py — Dark theme stylesheet for VPN Agent.
All selectors use object-name or class scoping to avoid style bleed.
"""

DARK_STYLESHEET = """
QMainWindow {
    background-color: #0f0f0f;
}

QWidget#CentralWidget {
    background-color: #0f0f0f;
}

QLabel#AppTitle {
    color: #00e5ff;
    font-size: 20px;
    font-weight: bold;
    letter-spacing: 2px;
}

QLabel#SectionHeader {
    color: #888888;
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 1px;
    text-transform: uppercase;
}

QLabel#StatusValue {
    color: #e0e0e0;
    font-size: 13px;
}

QLabel#StatusOk {
    color: #00e676;
    font-size: 13px;
    font-weight: bold;
}

QLabel#StatusWarn {
    color: #ff9800;
    font-size: 13px;
    font-weight: bold;
}

QLabel#StatusError {
    color: #f44336;
    font-size: 13px;
    font-weight: bold;
}

QLabel#StatusNeutral {
    color: #90caf9;
    font-size: 13px;
}

QGroupBox#StatusPanel {
    color: #888888;
    font-size: 11px;
    font-weight: bold;
    border: 1px solid #222222;
    border-radius: 8px;
    margin-top: 10px;
    padding: 12px;
    background-color: #141414;
}

QGroupBox#StatusPanel::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: #555555;
    font-size: 10px;
    letter-spacing: 1px;
}

QComboBox#ProfileDropdown {
    background-color: #1a1a1a;
    color: #e0e0e0;
    border: 1px solid #333333;
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 13px;
    min-width: 200px;
}

QComboBox#ProfileDropdown:hover {
    border: 1px solid #00e5ff;
}

QComboBox#ProfileDropdown QAbstractItemView {
    background-color: #1a1a1a;
    color: #e0e0e0;
    selection-background-color: #003344;
}

QPushButton#ActionButton {
    background-color: #1a1a1a;
    color: #e0e0e0;
    border: 1px solid #333333;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 13px;
    min-width: 110px;
}

QPushButton#ActionButton:hover {
    background-color: #222222;
    border: 1px solid #00e5ff;
    color: #00e5ff;
}

QPushButton#ActionButton:pressed {
    background-color: #003344;
}

QPushButton#ConnectButton {
    background-color: #003300;
    color: #00e676;
    border: 1px solid #00e676;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: bold;
    min-width: 110px;
}

QPushButton#ConnectButton:hover {
    background-color: #004400;
}

QPushButton#DisconnectButton {
    background-color: #330000;
    color: #f44336;
    border: 1px solid #f44336;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: bold;
    min-width: 110px;
}

QPushButton#DisconnectButton:hover {
    background-color: #440000;
}

QLabel#LogArea {
    background-color: #0a0a0a;
    color: #44cc44;
    font-family: "Menlo", "Monaco", "Courier New", monospace;
    font-size: 11px;
    border: 1px solid #1a1a1a;
    border-radius: 6px;
    padding: 8px;
}

QScrollArea {
    border: none;
    background-color: transparent;
}

QScrollBar:vertical {
    background: #111111;
    width: 8px;
    border-radius: 4px;
}

QScrollBar::handle:vertical {
    background: #333333;
    border-radius: 4px;
}

QFrame#WarningBanner {
    background-color: #1a0800;
    border: 1px solid #7f3b00;
    border-left: 4px solid #ff6f00;
    border-radius: 6px;
}

QLabel#WarningText {
    color: #ffab40;
    font-size: 12px;
    font-weight: bold;
    padding: 2px 0;
}

QLabel#WarningIcon {
    color: #ff6f00;
    font-size: 16px;
    font-weight: bold;
}

QPushButton#DismissButton {
    background-color: transparent;
    color: #888888;
    border: 1px solid #444444;
    border-radius: 4px;
    padding: 3px 10px;
    font-size: 11px;
    min-width: 60px;
}

QPushButton#DismissButton:hover {
    color: #ffffff;
    border-color: #666666;
}

QPushButton#HelpButton {
    background-color: #111111;
    color: #555555;
    border: 1px solid #2a2a2a;
    border-radius: 5px;
    padding: 5px 12px;
    font-size: 12px;
    font-weight: bold;
}

QPushButton#HelpButton:hover {
    background-color: #1a1a1a;
    color: #90caf9;
    border: 1px solid #334455;
}

/* ── Server tab ───────────────────────────────── */

QTabWidget#MainTabs::pane {
    border: 1px solid #222222;
    border-radius: 8px;
    background-color: #0f0f0f;
    top: -1px;
}

QTabWidget#MainTabs QTabBar::tab {
    background-color: #141414;
    color: #666666;
    border: 1px solid #222222;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 8px 20px;
    margin-right: 3px;
    font-size: 12px;
    font-weight: bold;
    letter-spacing: 1px;
}

QTabWidget#MainTabs QTabBar::tab:selected {
    background-color: #0f0f0f;
    color: #00e5ff;
    border-color: #2a3a3f;
}

QTabWidget#MainTabs QTabBar::tab:hover:!selected {
    color: #90caf9;
}

QListWidget#PeerList {
    background-color: #0d0d0d;
    color: #e0e0e0;
    border: 1px solid #222222;
    border-radius: 6px;
    padding: 4px;
    font-size: 12px;
}

QListWidget#PeerList::item {
    padding: 5px 6px;
    border-radius: 4px;
}

QListWidget#PeerList::item:selected {
    background-color: #10323a;
    color: #00e5ff;
}

QPlainTextEdit#DeployOutput {
    background-color: #0a0a0a;
    color: #b8b8b8;
    border: 1px solid #222222;
    border-radius: 6px;
    padding: 8px;
    font-family: "SF Mono", Menlo, monospace;
    font-size: 11px;
}

/* min-height is load-bearing, not cosmetic: a QFormLayout with this many rows
   will happily squeeze each one down to ~18px, and the padding below then
   leaves less room than the font needs — so the text renders clipped through
   the middle. The minimum stops the row collapsing under the font height. */
QLineEdit, QSpinBox {
    background-color: #141414;
    color: #e0e0e0;
    border: 1px solid #2a2a2a;
    border-radius: 5px;
    padding: 3px 8px;
    min-height: 19px;
    font-size: 12px;
}

QLineEdit:focus, QSpinBox:focus {
    border-color: #00e5ff;
}

QLineEdit:disabled, QSpinBox:disabled {
    color: #555555;
    background-color: #101010;
}

QCheckBox {
    color: #b0b0b0;
    font-size: 12px;
    spacing: 7px;
}

QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #333333;
    border-radius: 3px;
    background-color: #141414;
}

QCheckBox::indicator:checked {
    background-color: #00e5ff;
    border-color: #00e5ff;
}

QDialog {
    background-color: #0f0f0f;
}

QDialog QLabel {
    color: #c0c0c0;
    font-size: 12px;
}
"""
