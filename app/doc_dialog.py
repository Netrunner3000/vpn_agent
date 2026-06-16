"""
doc_dialog.py — In-app documentation viewer for VPN Agent.
Opens a resizable window showing the full HTML guide.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextBrowser, QLabel, QWidget,
)
from PySide6.QtCore import Qt

from app.doc_content import DOC_HTML


class DocDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("VPN Agent — Documentation")
        self.setMinimumSize(860, 640)
        self.resize(960, 760)
        self.setModal(False)  # non-modal so user can keep it open alongside the app

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar
        header = QWidget()
        header.setStyleSheet("background-color: #111111;")
        header.setFixedHeight(46)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(20, 0, 16, 0)

        title = QLabel("VPN AGENT — DOCUMENTATION")
        title.setStyleSheet(
            "color: #00e5ff; font-size: 14px; font-weight: bold; letter-spacing: 2px;"
        )
        hl.addWidget(title)
        hl.addStretch()

        btn_close = QPushButton("Close")
        btn_close.setFixedSize(72, 28)
        btn_close.setStyleSheet("""
            QPushButton {
                background: #1a1a1a;
                color: #888888;
                border: 1px solid #333333;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover {
                color: #ffffff;
                border-color: #555555;
            }
        """)
        btn_close.clicked.connect(self.close)
        hl.addWidget(btn_close)

        layout.addWidget(header)

        # HTML content browser
        browser = QTextBrowser()
        browser.setHtml(DOC_HTML)
        browser.setOpenExternalLinks(True)
        browser.setStyleSheet("""
            QTextBrowser {
                background-color: #0f0f0f;
                color: #d0d0d0;
                border: none;
                padding: 20px 28px;
                font-size: 13px;
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
        """)
        layout.addWidget(browser)
