#!/bin/bash
# Builds "VPN Agent.app" with PyInstaller into dist.noindex/.
# Pass --install to also copy it into /Applications.
#
# The output folder is named ".noindex" deliberately. It lives under
# ~/Documents, which Spotlight indexes, and a built .app sitting there shows up
# as a second "VPN Agent" next to the installed one — re-registered on every
# build, because each rebuild re-signs the bundle with a new ad-hoc identity.
# Spotlight skips any directory whose name ends in .noindex.
set -euo pipefail
cd "$(dirname "$0")"

APP_NAME="VPN Agent"
BUNDLE_ID="com.netrunner3000.vpnagent"
DIST="dist.noindex"

source .venv/bin/activate
uv pip install -q pyinstaller

# Regenerate the icon so the bundle never ships a stale one.
python assets/make_icon.py

rm -rf build dist "$DIST"

# QtNetwork backs the single-instance guard, and cryptography's Rust bindings
# back every key this app generates. Neither is reachable from a plain import
# graph walk in all cases, and both fail only at runtime — the app starts, then
# dies the moment you create a server. --hidden-import is cheaper than finding
# that out later.
pyinstaller --noconfirm --clean --windowed \
  --name "$APP_NAME" \
  --icon assets/icon.icns \
  --osx-bundle-identifier "$BUNDLE_ID" \
  --distpath "$DIST" \
  --add-data "assets/icon.icns:assets" \
  --add-data "docs/GUIDE.md:docs" \
  --add-data "docs/SERVER_GUIDE.md:docs" \
  --add-data "config/vpn_profiles.json:config" \
  --add-data "config/settings.json:config" \
  --hidden-import PySide6.QtNetwork \
  --hidden-import cryptography.hazmat.bindings._rust \
  --hidden-import segno \
  --exclude-module PySide6.QtWebEngineCore \
  --exclude-module PySide6.QtWebEngineWidgets \
  --exclude-module PySide6.Qt3DCore \
  --exclude-module PySide6.QtCharts \
  --exclude-module PySide6.QtDataVisualization \
  --exclude-module PySide6.QtMultimedia \
  --exclude-module PySide6.QtQuick3D \
  --exclude-module tkinter \
  main.py

echo
echo "Built: $DIST/$APP_NAME.app ($(du -sh "$DIST/$APP_NAME.app" | cut -f1))"

# Run the packaged binary's own self-test. This is the whole reason --selftest
# exists: it checks the things that only break once frozen — a missing icon or
# guide, key generation that silently stopped working, and a state directory
# that would be written inside the bundle.
echo
echo "Running self-test against the built app…"
if "$DIST/$APP_NAME.app/Contents/MacOS/$APP_NAME" --selftest; then
  echo "Self-test passed."
else
  echo "Self-test FAILED — the bundle is broken, not shipping it." >&2
  exit 1
fi

if [[ "${1:-}" == "--install" ]]; then
  rm -rf "/Applications/$APP_NAME.app"
  cp -R "$DIST/$APP_NAME.app" /Applications/
  touch "/Applications/$APP_NAME.app"  # nudge Finder/Dock to refresh the cached icon
  echo "Installed: /Applications/$APP_NAME.app"

  # Nothing left behind to be indexed or backed up.
  rm -rf build "$DIST"
  echo "Cleaned: build/ and $DIST/"
else
  echo "Run '$0 --install' to copy it into /Applications."
  echo "$DIST/ is skipped by Spotlight; --install removes it entirely."
fi
