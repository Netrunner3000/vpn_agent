"""
resources.py — Finding bundled files, whether running from source or frozen.

PyInstaller unpacks data files into a temporary directory and points
sys._MEIPASS at it. Nothing else in the app should have to know that, so every
lookup for an icon or a document goes through here.

The counterpart rule — never write to these locations — lives in server.paths:
anything the app creates goes to Application Support, because writing inside a
.app bundle breaks its signature and a reinstall wipes it.
"""

from __future__ import annotations

import sys
from pathlib import Path

APP_NAME = "VPN Agent"
BUNDLE_ID = "com.netrunner3000.vpnagent"


def bundle_root() -> Path:
    """Directory holding the app's read-only files."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parents[1]


def asset_path(name: str) -> Path:
    return bundle_root() / "assets" / name


def guide_path() -> Path:
    return bundle_root() / "docs" / "GUIDE.md"


# Every document the build is supposed to ship. The self-test walks this, so a
# guide added to docs/ but forgotten in build_app.sh fails the build rather than
# going missing quietly in the packaged app.
BUNDLED_DOCS = ("GUIDE.md", "SERVER_GUIDE.md", "PRIVACY_GUIDE.md")


def doc_paths() -> list[Path]:
    return [bundle_root() / "docs" / name for name in BUNDLED_DOCS]


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))
