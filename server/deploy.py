"""
deploy.py — Applying a rendered configuration to a server.

The installer script is streamed to the target over stdin and never written to
the target's disk. That is not incidental: the script embeds the server's
WireGuard private key and the OpenVPN server key, and a file in /tmp survives
long enough for anything else on the box to read it.

Both paths run the same script. Remote wraps it in ssh; native pipes it to a
local shell. Everything that differs between a VPS and a Raspberry Pi is
already resolved by the time the script is built.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Callable

from . import bootstrap, provision
from .model import MODE_NATIVE, MODE_REMOTE, Site

OutputCallback = Callable[[str], None]

DEPLOY_TIMEOUT = 600      # apt-get on a cold VPS is genuinely slow
PREFLIGHT_TIMEOUT = 20

SSH_BASE_OPTIONS = [
    "-o", "BatchMode=yes",           # never hang waiting for a password prompt
    "-o", "StrictHostKeyChecking=accept-new",
    "-o", "ConnectTimeout=10",
]


@dataclass
class DeployResult:
    success: bool
    output: str = ""
    error: str = ""
    command: str = ""
    problems: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if self.success:
            return "Deploy succeeded."
        if self.problems:
            return "Deploy blocked: " + "; ".join(self.problems)
        return self.error or "Deploy failed."


# ── Preflight ────────────────────────────────────


def preflight(site: Site) -> list[str]:
    """Return blocking problems, or an empty list if the site is deployable."""
    problems = site.validate()

    if site.mode == MODE_REMOTE:
        if not shutil.which("ssh"):
            problems.append("ssh not found on this machine.")
    elif site.mode == MODE_NATIVE:
        system = platform.system().lower()
        if system not in ("linux", "darwin"):
            problems.append(f"Native deploys are not supported on {platform.system()}.")

    if not any(p.enabled for p in site.peers):
        problems.append(
            "No enabled peers — the server would start with nothing able to connect. "
            "Add a peer first."
        )
    return problems


def check_ssh(site: Site) -> DeployResult:
    """Verify the remote host is reachable and we can act as root there."""
    if not site.ssh.is_configured():
        return DeployResult(False, error="No SSH host configured.")

    probe = "id -u; uname -s; command -v apt-get >/dev/null && echo has-apt || echo no-apt"
    command = _ssh_command(site) + [probe]
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=PREFLIGHT_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return DeployResult(
            False,
            error=f"Timed out connecting to {site.ssh.destination()}.",
            command=" ".join(command),
        )
    except OSError as exc:
        return DeployResult(False, error=str(exc), command=" ".join(command))

    if proc.returncode != 0:
        return DeployResult(
            False,
            output=proc.stdout,
            error=(proc.stderr.strip() or f"ssh exited {proc.returncode}"),
            command=" ".join(command),
        )

    lines = proc.stdout.split()
    problems: list[str] = []
    if lines and lines[0] != "0" and site.ssh.user != "root":
        problems.append(
            f"Connected as a non-root user ({site.ssh.user}). The installer will "
            "use `sudo -n`, which needs passwordless sudo configured for that user."
        )
    if "no-apt" in proc.stdout:
        problems.append("Remote host has no apt-get — the installer targets Debian/Ubuntu.")

    return DeployResult(
        success=not problems,
        output=proc.stdout.strip(),
        command=" ".join(command),
        problems=problems,
    )


# ── Deploy ───────────────────────────────────────


def deploy(
    site: Site,
    *,
    dry_run: bool = False,
    on_output: OutputCallback | None = None,
) -> DeployResult:
    """
    Push the current site configuration to its server.

    Safe to call repeatedly — the installer is idempotent, and adding a peer is
    just a redeploy. With dry_run the script is rendered and returned without
    touching anything.
    """
    problems = preflight(site)
    if problems:
        return DeployResult(False, problems=problems)

    script = build_script(site)

    if dry_run:
        return DeployResult(True, output=script, command="(dry run — nothing executed)")

    if site.mode == MODE_REMOTE:
        result = _run_remote(site, script, on_output)
    else:
        result = _run_local(site, script, on_output)

    if result.success:
        provision.mark_deployed(site)
    return result


def build_script(site: Site) -> str:
    """Render the installer that would be run for this site."""
    if site.mode == MODE_REMOTE:
        target_platform = "linux"
    else:
        target_platform = "darwin" if platform.system() == "Darwin" else "linux"
    return bootstrap.bootstrap_for(site, target_platform)


def _ssh_command(site: Site) -> list[str]:
    command = ["ssh", *SSH_BASE_OPTIONS]
    if site.ssh.port and site.ssh.port != 22:
        command += ["-p", str(site.ssh.port)]
    if site.ssh.identity_file:
        command += ["-i", site.ssh.identity_file, "-o", "IdentitiesOnly=yes"]
    command.append(site.ssh.destination())
    return command


def _run_remote(site: Site, script: str, on_output: OutputCallback | None) -> DeployResult:
    shell = "bash -s" if site.ssh.user == "root" else "sudo -n bash -s"
    command = _ssh_command(site) + [shell]
    return _stream(command, script, on_output)


def _run_local(site: Site, script: str, on_output: OutputCallback | None) -> DeployResult:
    """
    Run the installer on this machine.

    Requires root. We use `sudo -n` rather than prompting: a GUI has nowhere to
    show a terminal password prompt, and silently blocking on one looks like a
    hang. If credentials are not cached the caller is told exactly what to run.
    """
    import os

    if os.geteuid() == 0:
        command = ["bash", "-s"]
    else:
        command = ["sudo", "-n", "bash", "-s"]

    result = _stream(command, script, on_output)
    if not result.success and "sudo" in result.error.lower() and "password" in result.error.lower():
        result.problems.append(
            "sudo needs a password and none is cached. Run `sudo -v` in a terminal "
            "first, then deploy again — or use 'Save installer script' and run it "
            "yourself with sudo."
        )
    return result


def _stream(
    command: list[str],
    script: str,
    on_output: OutputCallback | None,
) -> DeployResult:
    """
    Run a command, feed it the script on stdin, and collect its output live.

    stdin is written from a helper thread. Writing it inline would deadlock as
    soon as the script outgrew the pipe buffer, because nothing would be
    draining stdout while we blocked on the write.
    """
    printable = " ".join(command)
    try:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except OSError as exc:
        return DeployResult(False, error=str(exc), command=printable)

    def feed() -> None:
        try:
            proc.stdin.write(script)
            proc.stdin.close()
        except (BrokenPipeError, ValueError):
            # The remote end rejected us before reading the script — the real
            # error will be on stdout, so let the reader report it.
            pass

    writer = threading.Thread(target=feed, daemon=True)
    writer.start()

    collected: list[str] = []
    try:
        for line in proc.stdout:
            collected.append(line)
            if on_output:
                on_output(line.rstrip("\n"))
        proc.wait(timeout=DEPLOY_TIMEOUT)
    except subprocess.TimeoutExpired:
        proc.kill()
        return DeployResult(
            False,
            output="".join(collected),
            error=f"Deploy timed out after {DEPLOY_TIMEOUT}s.",
            command=printable,
        )
    finally:
        writer.join(timeout=5)

    output = "".join(collected)
    if proc.returncode == 0:
        return DeployResult(True, output=output, command=printable)

    return DeployResult(
        False,
        output=output,
        error=_explain_failure(proc.returncode, output),
        command=printable,
    )


def _explain_failure(returncode: int, output: str) -> str:
    """Translate the common failure modes into something actionable."""
    lowered = output.lower()

    if "permission denied (publickey" in lowered:
        return (
            "SSH rejected the key. Add your public key to the server's "
            "~/.ssh/authorized_keys, or set an identity file on the site."
        )
    if "could not resolve hostname" in lowered:
        return "Could not resolve the host name. Check the SSH host on the site."
    if "connection refused" in lowered:
        return "Connection refused — is sshd running, and is the port right?"
    if "sudo: a password is required" in lowered or "sudo: a terminal is required" in lowered:
        return (
            "sudo needs a password. Connect as root, or configure passwordless "
            "sudo for this user on the target."
        )
    if "host key verification failed" in lowered:
        return (
            "Host key verification failed — the server's key changed since last "
            "time. Verify why, then remove the stale entry from ~/.ssh/known_hosts."
        )
    if "unable to locate package" in lowered:
        return "A package was not found. Run `apt-get update` on the target and retry."
    if returncode == 255:
        return "SSH failed to connect. Check host, port, user and network."
    return f"Installer exited with status {returncode}. See the output above."


# ── Teardown ─────────────────────────────────────


def build_teardown_script(site: Site) -> str:
    """
    Render a script that removes everything this tool installed.

    Stops and disables both services, removes the NAT unit and its rules, and
    deletes the configs. Packages are left installed — removing them could take
    out something else on the box that depends on them.
    """
    ovpn = ""
    if site.enable_openvpn:
        ovpn = """
systemctl disable --now openvpn-server@server.service 2>/dev/null || true
rm -rf /etc/openvpn/server/ca.crt /etc/openvpn/server/server.crt \\
       /etc/openvpn/server/server.key /etc/openvpn/server/tls-crypt.key \\
       /etc/openvpn/server/server.conf
echo "[vpn-agent] OpenVPN removed."
"""

    return f"""#!/usr/bin/env bash
# Remove the {site.name} VPN server. Generated by VPN Agent.
set -uo pipefail

[ "$(id -u)" -eq 0 ] || {{ echo "Must run as root." >&2; exit 1; }}

systemctl disable --now wg-quick@{site.wg_interface}.service 2>/dev/null || true
rm -f /etc/wireguard/{site.wg_interface}.conf
echo "[vpn-agent] WireGuard removed."
{ovpn}
systemctl disable --now vpn-agent-nat.service 2>/dev/null || true
[ -x {bootstrap.NAT_HELPER_PATH} ] && {bootstrap.NAT_HELPER_PATH} down 2>/dev/null || true
rm -f {bootstrap.NAT_UNIT_PATH} {bootstrap.NAT_HELPER_PATH} {bootstrap.SYSCTL_PATH}
systemctl daemon-reload
echo "[vpn-agent] NAT rules and forwarding removed."

echo "[vpn-agent] Teardown complete. Packages were left installed."
"""


def teardown(site: Site, *, on_output: OutputCallback | None = None) -> DeployResult:
    """Remove the VPN server from its host. Does not delete local site state."""
    if site.mode != MODE_REMOTE:
        return DeployResult(
            False,
            problems=[
                "Teardown is implemented for remote (Linux) hosts only. For a native "
                "macOS install, remove the pf anchor block from /etc/pf.conf and run "
                "`sudo wg-quick down` manually."
            ],
        )
    script = build_teardown_script(site)
    command = _ssh_command(site) + (
        ["bash -s"] if site.ssh.user == "root" else ["sudo -n bash -s"]
    )
    return _stream(command, script, on_output)
