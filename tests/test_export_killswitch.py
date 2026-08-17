"""
Config export and the kill switch.

Exported files carry private keys, so their permissions are part of the
contract. The kill switch assertions guard two bugs found while building it:
opening protocol/port combinations that serve nothing, and blocking the ICMP
the app's own latency test depends on.
"""

import shutil
import stat
import subprocess

import pytest

from server import export, paths
from services import killswitch as ks


# ── Export ───────────────────────────────────────


def test_export_writes_every_format(site):
    written = export.export_peer(site, site.peers[0])
    assert set(written) == {"wireguard", "qr", "openvpn"}
    for path in written.values():
        assert path.is_file() and path.stat().st_size > 0


def test_exported_files_are_owner_only(site):
    """These contain private keys — a password in a file."""
    for kind, path in export.export_peer(site, site.peers[0]).items():
        assert stat.S_IMODE(path.stat().st_mode) == 0o600, kind


def test_qr_is_a_png(site):
    written = export.export_peer(site, site.peers[0])
    assert written["qr"].read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_openvpn_export_skipped_when_peer_has_no_certificate(site):
    site.peers[0].ovpn_cert_pem = ""
    assert "openvpn" not in export.export_peer(site, site.peers[0])


def test_oversized_config_produces_no_qr(site, monkeypatch):
    """An unscannable QR code is worse than none — the .conf still works."""
    monkeypatch.setattr(export, "QR_MAX_BYTES", 10)
    assert "qr" not in export.export_peer(site, site.peers[0])


def test_register_profile_creates_then_updates(site, tmp_path):
    profiles = tmp_path / "vpn_profiles.json"
    assert export.register_profile(site, profiles) is True
    assert export.register_profile(site, profiles) is False   # unchanged

    site.wg_port = 51821
    assert export.register_profile(site, profiles) is True

    import json
    entries = json.loads(profiles.read_text())["profiles"]
    assert len([e for e in entries if e["name"] == site.name]) == 1
    assert entries[0]["port"] == 51821


def test_site_summary_mentions_the_essentials(site):
    text = export.site_summary(site)
    for expected in (site.name, site.endpoint_host, "laptop", "CA expires"):
        assert expected in text


# ── Kill switch ──────────────────────────────────


def test_placeholder_endpoint_is_rejected():
    """
    0.0.0.0 ships in the example profile. As a pf destination it means
    "unspecified", so a rule naming it protects nothing while looking like it
    does.
    """
    resolved, skipped = ks.resolve_endpoints(["0.0.0.0", "203.0.113.10"])
    assert resolved == ["203.0.113.10"]
    assert skipped == ["0.0.0.0"]


def test_unresolvable_host_is_reported_not_silently_dropped():
    resolved, skipped = ks.resolve_endpoints(["no-such-host.invalid"])
    assert resolved == []
    assert skipped == ["no-such-host.invalid"]


def test_literal_addresses_pass_through():
    resolved, _ = ks.resolve_endpoints(["203.0.113.10", "2001:db8::1"])
    assert resolved == ["203.0.113.10", "2001:db8::1"]


def test_rules_default_to_deny():
    rules = ks.build_rules(["203.0.113.10"], [("udp", 51820)], interfaces=["utun4"])
    assert rules.splitlines()[3].startswith("#")
    assert "block drop all" in rules


def test_rules_pass_loopback_and_the_tunnel():
    rules = ks.build_rules(["203.0.113.10"], [("udp", 51820)], interfaces=["utun4"])
    assert "pass quick on lo0 all" in rules
    assert "pass quick on utun4 all" in rules


def test_protocols_are_paired_with_their_own_ports():
    """
    Regression guard. Pairing every protocol with every port opened TCP/51820
    and UDP/443 — holes serving nothing.
    """
    rules = ks.build_rules(["203.0.113.10"], [("udp", 51820), ("tcp", 443)],
                           interfaces=["utun4"])
    assert "proto udp from any to 203.0.113.10 port 51820" in rules
    assert "proto tcp from any to 203.0.113.10 port 443" in rules
    assert "proto tcp from any to 203.0.113.10 port 51820" not in rules
    assert "proto udp from any to 203.0.113.10 port 443" not in rules


def test_icmp_to_the_endpoint_stays_open():
    """
    Regression guard. The Monitor tab pings this same endpoint; blocked, arming
    the switch would make the app report its own server as unreachable.
    """
    rules = ks.build_rules(["203.0.113.10"], [("udp", 51820)], interfaces=["utun4"])
    assert "proto icmp from any to 203.0.113.10" in rules


def test_dhcp_stays_open():
    """Otherwise the Mac loses its address when the lease expires."""
    rules = ks.build_rules([], [], interfaces=[])
    assert "port 68 to any port 67" in rules


def test_lan_can_be_excluded():
    rules = ks.build_rules([], [], interfaces=[], allow_lan=False)
    assert "192.168.0.0/16" not in rules


def test_armed_without_a_tunnel_says_so():
    rules = ks.build_rules(["203.0.113.10"], [("udp", 51820)], interfaces=[])
    assert "no tunnel" in rules.lower()


def test_recovery_command_is_embedded_in_the_rules():
    """Whoever finds this file while locked out needs the way back in it."""
    rules = ks.build_rules([], [], interfaces=[])
    assert ks.recovery_command() in rules
    assert "pfctl" in ks.recovery_command()


def test_arming_is_refused_when_no_endpoint_resolves():
    ok, message = ks.arm(["no-such-host.invalid"], [("udp", 51820)])
    assert ok is False
    assert "Could not resolve" in message


@pytest.mark.skipif(
    shutil.which("pfctl") is None, reason="pf is macOS-only"
)
def test_generated_rules_are_accepted_by_pf(tmp_path):
    """
    `pfctl -n` parses without loading and needs no privileges, so the real
    parser can vet the output. This is what stops a malformed ruleset ever
    reaching the point of being applied.
    """
    rules = ks.build_rules(
        ["203.0.113.10", "2001:db8::1"],
        [("udp", 51820), ("tcp", 443)],
        interfaces=["utun4"],
    )
    path = tmp_path / "test.pf"
    path.write_text(rules)
    proc = subprocess.run(["pfctl", "-n", "-f", str(path)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


@pytest.mark.skipif(shutil.which("pfctl") is None, reason="pf is macOS-only")
def test_validate_rejects_broken_rules(tmp_path):
    """Confirms the check is real and not passing everything."""
    path = tmp_path / "bad.pf"
    path.write_text("this is not valid pf syntax\n")
    ok, _ = ks.validate(path)
    assert ok is False
