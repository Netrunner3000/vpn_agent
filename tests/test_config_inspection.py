from pathlib import Path

import pytest

from services.config_inspection import inspect_wireguard_config


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "travel.conf"
    path.write_text(text, encoding="utf-8")
    return path


def test_summary_discards_private_and_preshared_keys(tmp_path):
    private = "PRIVATE-MUST-NEVER-LEAK"
    preshared = "PRESHARED-MUST-NEVER-LEAK"
    summary = inspect_wireguard_config(_write(tmp_path, f"""
[Interface]
PrivateKey = {private}
Address = 10.7.0.2/32
DNS = 10.7.0.1, 1.1.1.1

[Peer]
PresharedKey = {preshared}
Endpoint = vpn.example.test:51820
AllowedIPs = 0.0.0.0/0, ::/0
"""))

    assert summary.route_mode == "Full tunnel"
    assert summary.peer_count == 1
    assert summary.secrets_discarded == 2
    assert private not in repr(summary)
    assert preshared not in repr(summary)


def test_split_tunnel_and_multiple_peers_are_summarised(tmp_path):
    summary = inspect_wireguard_config(_write(tmp_path, """
[Interface]
Address = 10.7.0.2/32

[Peer]
Endpoint = 198.51.100.8:51820
AllowedIPs = 10.10.0.0/16

[Peer]
Endpoint = [2001:db8::1]:51821
AllowedIPs = 192.168.50.0/24
"""))

    assert summary.route_mode == "Split tunnel"
    assert summary.peer_count == 2
    assert summary.invalid_endpoint_count == 0
    assert summary.allowed_ips == ("10.10.0.0/16", "192.168.50.0/24")


def test_invalid_public_fields_warn_without_echoing_secret_values(tmp_path):
    summary = inspect_wireguard_config(_write(tmp_path, """
[Interface]
PrivateKey = secret-material
Address = not-an-address
[Peer]
Endpoint = bad endpoint
AllowedIPs = not-a-network
"""))

    assert summary.invalid_endpoint_count == 1
    assert len(summary.warnings) == 3
    assert "secret-material" not in " ".join(summary.warnings)


def test_missing_and_oversized_files_are_refused(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="not a readable file"):
        inspect_wireguard_config(tmp_path / "missing.conf")

    path = _write(tmp_path, "[Interface]\n")
    monkeypatch.setattr(Path, "stat", lambda _self: type("S", (), {"st_size": 2 ** 20 + 1})())
    with pytest.raises(ValueError, match="larger than 1 MiB"):
        inspect_wireguard_config(path)
