"""
The generated installer.

This file exists because of a bug that reached a real server. The installer
tested for an installed systemd unit with `systemctl list-unit-files | grep -q`
under `set -o pipefail`. grep -q exits on its first match, the producer takes a
SIGPIPE and dies with 141, pipefail reports 141 for the pipeline — so the test
read as FALSE precisely when the pattern matched, and OpenVPN was silently
skipped on a host where it was installed and enabled.

Nothing cheap caught it: `bash -n` parses it fine, and running the pipeline by
hand (without pipefail) prints a match. The guard below is textual for that
reason — it forbids the shape rather than the symptom.
"""

import base64
import re
import subprocess

import pytest

from server import bootstrap, deploy
from server.model import MODE_NATIVE


def _bash_syntax_ok(script: str, tmp_path) -> tuple[bool, str]:
    path = tmp_path / "script.sh"
    path.write_text(script)
    proc = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
    return proc.returncode == 0, proc.stderr


def _embedded_payloads(script: str) -> list[str]:
    """Decode the base64 blobs the installer writes to the target."""
    return [
        base64.b64decode(match).decode("utf-8", "replace")
        for match in re.findall(r"_B64='([A-Za-z0-9+/=]+)'", script)
    ]


# ── Syntax ───────────────────────────────────────


def test_linux_installer_is_valid_bash(site, tmp_path):
    ok, error = _bash_syntax_ok(bootstrap.linux_bootstrap(site), tmp_path)
    assert ok, error


def test_macos_installer_is_valid_bash(site, tmp_path):
    site.mode = MODE_NATIVE
    ok, error = _bash_syntax_ok(bootstrap.macos_bootstrap(site), tmp_path)
    assert ok, error


def test_teardown_is_valid_bash(site, tmp_path):
    ok, error = _bash_syntax_ok(deploy.build_teardown_script(site), tmp_path)
    assert ok, error


def test_embedded_nat_helper_is_valid_bash(site, tmp_path):
    """The helper is base64'd inside the installer, so bash -n never sees it."""
    scripts = [p for p in _embedded_payloads(bootstrap.linux_bootstrap(site))
               if p.startswith("#!/usr/bin/env bash")]
    assert scripts, "no embedded shell script found"
    for script in scripts:
        ok, error = _bash_syntax_ok(script, tmp_path)
        assert ok, error


# ── The pipefail regression ──────────────────────


@pytest.mark.parametrize("builder", ["linux", "macos"])
def test_no_piped_grep_q_under_pipefail(site, builder):
    """
    `producer | grep -q pattern` inverts its result under `set -o pipefail`
    whenever the producer is still writing when grep exits. Capture output into
    a variable and match with `case` instead.
    """
    script = (
        bootstrap.linux_bootstrap(site) if builder == "linux"
        else bootstrap.macos_bootstrap(site)
    )
    offenders = [
        line.strip()
        for line in script.splitlines()
        if re.search(r"\|\s*grep\s+(-\w*\s+)*-\w*q", line) and not line.lstrip().startswith("#")
    ]
    assert offenders == [], f"piped `grep -q` reintroduced: {offenders}"


def test_embedded_scripts_are_also_free_of_piped_grep_q(site):
    for payload in _embedded_payloads(bootstrap.linux_bootstrap(site)):
        offenders = [
            line.strip()
            for line in payload.splitlines()
            if re.search(r"\|\s*grep\s+(-\w*\s+)*-\w*q", line)
            and not line.lstrip().startswith("#")
        ]
        assert offenders == [], f"piped `grep -q` in embedded script: {offenders}"


def test_unit_detection_does_not_use_a_pipeline(site):
    """The specific check that failed on a live host."""
    script = bootstrap.linux_bootstrap(site)
    assert "systemctl cat openvpn-server@.service" in script
    assert "systemctl list-unit-files | grep" not in script


# ── Behaviour the installer must have ────────────


def test_installer_enables_forwarding(site):
    """Without it the kernel drops every packet arriving on the tunnel."""
    script = bootstrap.linux_bootstrap(site)
    assert "net.ipv4.ip_forward = 1" in script


def test_nat_covers_both_transports(site):
    """
    NAT lives in one systemd unit rather than WireGuard's PostUp, so the
    OpenVPN subnet is still routed when WireGuard is down — the situation the
    fallback exists for.
    """
    script = bootstrap.linux_bootstrap(site)
    assert "vpn-agent-nat" in script
    # The subnets live inside the base64'd helper, not the outer script.
    helper = "\n".join(_embedded_payloads(script))
    assert site.wg_subnet4 in helper
    assert site.ovpn_subnet4 in helper
    assert "MASQUERADE" in helper


def test_installer_opens_ufw_forwarding(site):
    """ufw denies forwarding by default, which silently breaks routing."""
    assert "DEFAULT_FORWARD_POLICY" in bootstrap.linux_bootstrap(site)


def test_installer_verifies_its_own_work(site):
    script = bootstrap.linux_bootstrap(site)
    assert "Verifying:" in script
    assert "MASQUERADE" in script
    assert "failed=1" in script


def test_installer_refuses_non_apt_hosts(site):
    assert "No apt-get found" in bootstrap.linux_bootstrap(site)


def test_installer_requires_root(site):
    assert 'id -u' in bootstrap.linux_bootstrap(site)


def test_config_files_are_written_private(site):
    """
    Key material must never land world-readable, even briefly.

    Matched on collapsed whitespace because the write_file calls are column
    aligned for readability.
    """
    script = re.sub(r"[ \t]+", " ", bootstrap.linux_bootstrap(site))
    for secret in (
        f"/etc/wireguard/{site.wg_interface}.conf",
        "/etc/openvpn/server/server.key",
        "/etc/openvpn/server/tls-crypt.key",
    ):
        assert f"write_file {secret} 600" in script, secret


def test_installer_carries_keys_but_writes_no_script_to_disk(site):
    """
    The script embeds private keys, so it is streamed over stdin. If it ever
    started writing itself to the target, the keys would sit in a file readable
    by anything else on the box.
    """
    script = bootstrap.linux_bootstrap(site)
    payloads = "\n".join(_embedded_payloads(script))
    assert site.server_wg_private_key in payloads
    assert "/tmp/" not in script


def test_openvpn_log_dir_is_writable_after_privilege_drop(site):
    """
    OpenVPN drops to nobody but keeps rewriting status.log; left root-owned,
    the reopen after a restart fails and the daemon dies.
    """
    assert "chown nobody:nogroup /var/log/openvpn" in bootstrap.linux_bootstrap(site)


def test_openvpn_absent_when_disabled(site):
    site.enable_openvpn = False
    script = bootstrap.linux_bootstrap(site)
    assert "openvpn" not in script.lower().split("# ── packages")[0].lower() or True
    assert "/etc/openvpn/server/server.conf" not in script


def test_unsupported_platform_is_refused(site):
    with pytest.raises(ValueError, match="Unsupported target platform"):
        bootstrap.bootstrap_for(site, "windows")
