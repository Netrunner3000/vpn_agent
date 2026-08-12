#!/usr/bin/env python3
"""
VPN Agent — entry point.

    python main.py              launch the app
    python main.py --selftest   check a build's wiring and exit

The self-test exists because a packaged .app fails in ways the source tree
cannot. This app leans on `cryptography`, which ships compiled cffi modules
PyInstaller's static analysis can miss, and on QtNetwork, which the
single-instance guard needs. Both fail silently-ish once packaged: the app
starts, and then generating a key or guarding the socket blows up. Running the
self-test against the built binary catches that before the app is trusted with
a certificate authority.
"""

import os
import sys

# Ensure the project root is in the Python path so all imports resolve correctly
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def selftest() -> int:
    """Verify a build can do everything it claims. Returns a shell exit code."""
    import base64

    from app.resources import APP_NAME, asset_path, guide_path, is_frozen
    from server import keys, paths, pki, render
    from server.model import Site, Peer

    problems: list[str] = []

    icon = asset_path("icon.icns")
    guide = guide_path()
    state = paths.state_dir()

    print(f"{APP_NAME} self-test")
    print(f"  frozen bundle:   {is_frozen()}")
    print(f"  icon asset:      {icon} ({'found' if icon.exists() else 'MISSING'})")
    print(f"  user guide:      {guide} ({'found' if guide.exists() else 'MISSING'})")
    print(f"  state dir:       {state}")

    if not icon.exists():
        problems.append("icon asset missing from the bundle")
    if not guide.exists():
        problems.append("user guide missing from the bundle")

    # Writing inside the bundle breaks the code signature, and a reinstall
    # would silently destroy every server key the user has.
    if is_frozen() and ".app/" in str(state):
        problems.append("state directory would be written inside the .app bundle")

    # QtNetwork backs the single-instance guard. Missing, two copies could run
    # and the second to save would discard the first's peers.
    try:
        from PySide6.QtNetwork import QLocalServer  # noqa: F401
        print("  QtNetwork:       ok")
    except ImportError as exc:
        print("  QtNetwork:       MISSING")
        problems.append(f"PySide6.QtNetwork not bundled ({exc})")

    # cryptography: the RFC 7748 vector proves our X25519 matches what
    # `wg pubkey` produces. A wrong answer here means every key this app has
    # ever generated is garbage.
    try:
        priv = base64.b64encode(
            bytes.fromhex(
                "77076d0a7318a57d3c16c17251b26645df4c2f87ebc0992ab177fba51db92c2a"
            )
        ).decode()
        want = base64.b64encode(
            bytes.fromhex(
                "8520f0098930a754748b7ddcb43ef75a0dbf3a0d26381af4eba4a98eaa9b4e6a"
            )
        ).decode()
        if keys.derive_wg_public(priv) == want:
            print("  wireguard keys:  ok (matches RFC 7748 vector)")
        else:
            print("  wireguard keys:  WRONG OUTPUT")
            problems.append("X25519 derivation does not match the RFC 7748 test vector")
    except Exception as exc:
        print("  wireguard keys:  FAILED")
        problems.append(f"WireGuard key generation failed ({type(exc).__name__}: {exc})")

    # The OpenVPN half needs certificate issuance to work end to end.
    try:
        ca_cert, ca_key = pki.create_ca("selftest")
        cert, _ = pki.issue_client_cert(ca_cert, ca_key, "probe")
        info = pki.describe_cert(cert)
        print(f"  openvpn pki:     ok (issued {info['common_name']})")
    except Exception as exc:
        print("  openvpn pki:     FAILED")
        problems.append(f"certificate issuance failed ({type(exc).__name__}: {exc})")

    # segno backs the QR export.
    try:
        import segno
        segno.make("probe", error="m")
        print("  qr codes:        ok")
    except Exception as exc:
        print("  qr codes:        FAILED")
        problems.append(f"QR generation failed ({type(exc).__name__}: {exc})")

    # Config rendering, end to end, with throwaway material.
    try:
        private_key, public_key = keys.generate_wg_keypair()
        peer_private, peer_public = keys.generate_wg_keypair()
        site = Site(name="selftest", endpoint_host="198.51.100.1")
        site.server_wg_private_key, site.server_wg_public_key = private_key, public_key
        site.peers = [
            Peer(
                name="probe",
                wg_private_key=peer_private,
                wg_public_key=peer_public,
                wg_preshared_key=keys.generate_preshared_key(),
                address4="10.66.66.2/32",
                address6="fd42:66:66::2/128",
            )
        ]
        server_conf = render.wg_server_config(site)
        client_conf = render.wg_client_config(site, site.peers[0])
        assert "[Interface]" in server_conf and "AllowedIPs" in client_conf
        print("  config render:   ok")
    except Exception as exc:
        print("  config render:   FAILED")
        problems.append(f"config rendering failed ({type(exc).__name__}: {exc})")

    if problems:
        print("\nFAILED:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print("\nOK")
    return 0


def run() -> int:
    """Create the application, guard against a second copy, and show the window."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from app.resources import APP_NAME, asset_path
    from app.gui import MainWindow
    from app.single_instance import SingleInstance

    # High-DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("PersonalTools")

    guard = SingleInstance()
    if not guard.acquire():
        # Another copy already holds the site files and has been told to come
        # forward. Two copies would each keep their own view of the same peers,
        # and whichever saved last would silently discard the other's work.
        print(f"{APP_NAME} is already running — bringing it to the front.")
        return 0

    # A packaged .app takes its Dock icon from the bundle; this covers running
    # from source, where there is no bundle to read.
    icon_file = asset_path("icon.icns")
    if icon_file.exists():
        app.setWindowIcon(QIcon(str(icon_file)))

    window = MainWindow()
    guard.activated.connect(window.present)
    app.aboutToQuit.connect(guard.release)

    window.show()
    return app.exec()


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    sys.exit(run())
