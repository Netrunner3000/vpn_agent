"""
Shared fixtures.

Every test runs against a throwaway state directory. Without this the suite
would read and write the real ~/Library/Application Support/VPN Agent/, whose
site files hold the only copy of the user's server and CA private keys — a
test that deletes a site would destroy a working VPN.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server import paths, provision  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Point every path lookup at a per-test directory."""
    state = tmp_path / "state"
    monkeypatch.setenv(paths.ENV_STATE_DIR, str(state))
    return state


@pytest.fixture
def site():
    """A remote site with a CA and one peer — the common starting point."""
    s = provision.init_site("Test Site", "remote", endpoint_host="203.0.113.10")
    s.ssh.host = "203.0.113.10"
    provision.add_peer(s, "laptop")
    return s
