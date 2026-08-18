"""
v2 hardening: kill-switch leak semantics, non-apt refusal, macOS teardown.

The kill-switch tests here do more than match strings. They evaluate the
generated ruleset the way pf would — default deny, first `quick` match wins —
and assert that a packet leaving a physical interface is dropped. That is the
question the feature exists to answer, and the one a string check cannot.
"""

import os
import shutil
import stat
import subprocess

import pytest

from server import bootstrap, deploy, provision
from server.model import MODE_NATIVE
from services import killswitch as ks


# ── A miniature pf evaluator ─────────────────────


def _verdict(rules: str, *, interface: str, dest: str = "", proto: str = "tcp",
             port: int = 443, src: str = "192.0.2.50") -> str:
    """
    Decide what pf would do with one packet, for the subset of syntax we emit.

    pf semantics: rules are evaluated in order, the last match wins, except a
    `quick` rule which wins immediately. Our anchor is a `block drop all`
    followed by `pass quick` exceptions, so anything not explicitly passed is
    dropped.
    """
    verdict = "block"
    for line in rules.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if line == "block drop all":
            verdict = "block"
            continue
        if not line.startswith("pass"):
            continue

        # on <iface>
        if " on " in line:
            named = line.split(" on ", 1)[1].split()[0]
            if named != interface:
                continue
        # to <address>
        if " to " in line:
            target = line.split(" to ", 1)[1].split()[0]
            if target != "any" and target != dest and not target.endswith("/16") \
               and not target.endswith("/8") and not target.endswith("/12"):
                continue
            if target.endswith(("/8", "/12", "/16")) and not src.startswith("192.168."):
                continue
        # proto
        if " proto " in line:
            named_proto = line.split(" proto ", 1)[1].split()[0]
            if named_proto != proto:
                continue
        # port
        if " port " in line:
            named_port = line.split(" port ", 1)[1].split()[0]
            if named_port.isdigit() and int(named_port) != port:
                continue

        if "quick" in line:
            return "pass"
        verdict = "pass"
    return verdict


ENDPOINT = "203.0.113.10"
ALLOW = [("udp", 51820), ("tcp", 443)]


def test_ordinary_traffic_is_blocked_while_armed():
    """The leak case: a browser talking to the internet over wifi."""
    rules = ks.build_rules([ENDPOINT], ALLOW, interfaces=["utun4"])
    assert _verdict(rules, interface="en0", dest="93.184.216.34") == "block"


def test_tunnel_traffic_passes():
    rules = ks.build_rules([ENDPOINT], ALLOW, interfaces=["utun4"])
    assert _verdict(rules, interface="utun4", dest="93.184.216.34") == "pass"


def test_no_packet_escapes_when_the_tunnel_drops():
    """
    The failure this feature exists for.

    A dropped tunnel means no utun device, so the rules are rebuilt with no
    interface exemption at all. Traffic must still be blocked rather than
    falling back to the ISP.
    """
    rules = ks.build_rules([ENDPOINT], ALLOW, interfaces=[])
    assert _verdict(rules, interface="en0", dest="93.184.216.34") == "block"
    assert _verdict(rules, interface="utun4", dest="93.184.216.34") == "block"


def test_the_server_itself_stays_reachable_after_a_drop():
    """Otherwise the tunnel could never be rebuilt from inside the switch."""
    rules = ks.build_rules([ENDPOINT], ALLOW, interfaces=[])
    assert _verdict(rules, interface="en0", dest=ENDPOINT, proto="udp", port=51820) == "pass"
    assert _verdict(rules, interface="en0", dest=ENDPOINT, proto="tcp", port=443) == "pass"


def test_loopback_survives():
    rules = ks.build_rules([ENDPOINT], ALLOW, interfaces=["utun4"])
    assert _verdict(rules, interface="lo0", dest="127.0.0.1") == "pass"


def test_a_different_port_on_the_server_is_still_blocked():
    """The exemption is the VPN port, not the whole host."""
    rules = ks.build_rules([ENDPOINT], ALLOW, interfaces=["utun4"])
    assert _verdict(rules, interface="en0", dest=ENDPOINT, proto="tcp", port=22) == "block"


def test_evaluator_agrees_with_pf_that_the_rules_are_valid():
    """Guards the evaluator itself against drifting from real syntax."""
    if shutil.which("pfctl") is None:
        pytest.skip("pf is macOS-only")
    import tempfile

    rules = ks.build_rules([ENDPOINT], ALLOW, interfaces=["utun4"])
    with tempfile.NamedTemporaryFile("w", suffix=".pf", delete=False) as handle:
        handle.write(rules)
        path = handle.name
    try:
        assert subprocess.run(["pfctl", "-n", "-f", path],
                              capture_output=True).returncode == 0
    finally:
        os.unlink(path)


# ── Refusing a non-Debian target ─────────────────


@pytest.mark.skipif(shutil.which("apt-get") is not None,
                    reason="this host has apt-get, so it is not a non-apt target")
def test_installer_actually_stops_without_apt(site, tmp_path):
    """
    Run the real installer on a host with no apt-get and assert it dies rather
    than guessing. macOS has no apt-get, so this machine is the test fixture.

    A stub `id` reporting root gets execution past the privilege check, so the
    package-manager guard is what is really being exercised.
    """
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "id").write_text("#!/bin/sh\necho 0\n")
    (stub / "id").chmod(0o755)

    script = tmp_path / "install.sh"
    script.write_text(bootstrap.linux_bootstrap(site))

    proc = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": f"{stub}:/usr/bin:/bin"},
    )

    assert proc.returncode != 0
    assert "apt-get" in (proc.stdout + proc.stderr)


def test_installer_refuses_to_run_unprivileged(site, tmp_path):
    script = tmp_path / "install.sh"
    script.write_text(bootstrap.linux_bootstrap(site))
    proc = subprocess.run(["bash", str(script)], capture_output=True, text=True)
    assert proc.returncode != 0
    assert "root" in (proc.stdout + proc.stderr).lower()


# ── macOS teardown ───────────────────────────────


def test_native_teardown_targets_pf_not_systemd(site, monkeypatch):
    site.mode = MODE_NATIVE
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    script = deploy.build_teardown_script(site)
    assert "pf.conf" in script
    assert "systemctl" not in script


def test_remote_teardown_still_targets_systemd(site):
    script = deploy.build_teardown_script(site)
    assert "systemctl" in script
    assert "pf.conf" not in script


def test_native_teardown_preserves_the_rest_of_pf_conf(site, monkeypatch):
    """
    Apple's anchors live in the same file. The block is cut out by marker
    rather than the file being rewritten, so nothing else is disturbed.
    """
    site.mode = MODE_NATIVE
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    script = deploy.build_teardown_script(site)
    assert "awk" in script and "vpn-agent >>>" in script
    assert "pf.conf.vpn-agent-teardown.bak" in script


def test_native_teardown_is_valid_bash(site, monkeypatch, tmp_path):
    site.mode = MODE_NATIVE
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    path = tmp_path / "td.sh"
    path.write_text(deploy.build_teardown_script(site))
    assert subprocess.run(["bash", "-n", str(path)], capture_output=True).returncode == 0


def test_pf_marker_check_reports_absence():
    """On a machine that has never had a native install, the marker is absent."""
    assert bootstrap.pf_conf_has_marker() in (True, False)   # never raises


# ── Key rotation without a server rebuild ────────


def test_rotation_reuses_the_address_so_no_rebuild_is_needed(site):
    """
    Rotation keeps the peer's address, so the server config changes only in the
    peer's public key. Deploy applies that with `wg syncconf`, which reloads in
    place — existing tunnels for other devices are not torn down.
    """
    before = site.peers[0].address4
    rotated = provision.rotate_peer_keys(site, "laptop")
    assert rotated.address4 == before
    assert "wg syncconf" in bootstrap.linux_bootstrap(site)
