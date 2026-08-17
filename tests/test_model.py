"""
Addressing and validation.

Address allocation and validate() are what stand between a typo and a server
that deploys cleanly but routes nothing.
"""

import pytest

from server.model import (
    MODE_NATIVE,
    MODE_REMOTE,
    Peer,
    Site,
    default_site,
)


def _peer(name: str, address4: str) -> Peer:
    return Peer(
        name=name,
        wg_private_key="k",
        wg_public_key="p",
        wg_preshared_key="s",
        address4=address4,
        address6="",
    )


# ── Addressing ───────────────────────────────────


def test_server_takes_the_first_address():
    assert Site(name="s").server_ip4 == "10.66.66.1"


def test_peers_start_after_the_server():
    site = Site(name="s")
    assert site.allocate_addresses()[0] == "10.66.66.2/32"


def test_addresses_are_handed_out_in_order():
    site = Site(name="s")
    for i in range(3):
        address4, _ = site.allocate_addresses()
        site.peers.append(_peer(f"p{i}", address4))
    assert [p.ip4 for p in site.peers] == ["10.66.66.2", "10.66.66.3", "10.66.66.4"]


def test_removed_addresses_are_reused():
    """
    A site that churns devices must not march off the end of its /24. The gap
    left by a removed peer is the next address handed out.
    """
    site = Site(name="s")
    site.peers = [_peer("a", "10.66.66.2/32"), _peer("c", "10.66.66.4/32")]
    assert site.allocate_addresses()[0] == "10.66.66.3/32"


def test_exhausted_subnet_raises_rather_than_colliding():
    site = Site(name="s", wg_subnet4="10.66.66.0/30")
    site.peers = [_peer("a", "10.66.66.2/32")]
    with pytest.raises(ValueError, match="No free addresses"):
        site.allocate_addresses()


def test_ipv6_address_tracks_the_ipv4_host_number():
    site = Site(name="s")
    site.peers = [_peer("a", "10.66.66.2/32")]
    address4, address6 = site.allocate_addresses()
    assert address4 == "10.66.66.3/32"
    assert address6 == "fd42:66:66::3/128"


def test_no_ipv6_when_disabled():
    site = Site(name="s", enable_ipv6=False)
    assert site.allocate_addresses()[1] == ""


# ── Routing policy ───────────────────────────────


def test_full_tunnel_routes_everything():
    site = Site(name="s", full_tunnel=True)
    assert site.client_allowed_ips() == "0.0.0.0/0, ::/0"


def test_split_tunnel_routes_only_named_networks():
    site = Site(name="s", full_tunnel=False, lan_routes=["192.168.1.0/24"])
    routes = site.client_allowed_ips()
    assert "0.0.0.0/0" not in routes
    assert "192.168.1.0/24" in routes
    assert site.wg_subnet4 in routes


def test_server_confines_each_peer_to_its_own_address():
    """
    AllowedIPs on the server side is an access-control rule: a peer may only
    send from the addresses listed. A wildcard here would let any peer spoof
    any other.
    """
    site = Site(name="s")
    peer = _peer("a", "10.66.66.2/32")
    peer.address6 = "fd42:66:66::2/128"
    allowed = site.server_allowed_ips(peer)
    assert allowed == "10.66.66.2/32, fd42:66:66::2/128"
    assert "0.0.0.0/0" not in allowed


def test_native_mode_defaults_to_split_tunnel():
    """
    A home server exits through the same ISP, so a full tunnel buys nothing
    and costs a round trip.
    """
    assert default_site("Home", MODE_NATIVE).full_tunnel is False


def test_remote_mode_defaults_to_full_tunnel():
    assert default_site("VPS", MODE_REMOTE).full_tunnel is True


# ── Validation ───────────────────────────────────


def _valid_site() -> Site:
    site = Site(name="s", endpoint_host="203.0.113.10", enable_openvpn=False)
    site.server_wg_private_key = "key"
    site.ssh.host = "203.0.113.10"
    return site


def test_a_complete_site_validates():
    assert _valid_site().validate() == []


def test_missing_endpoint_is_caught():
    site = _valid_site()
    site.endpoint_host = ""
    assert any("endpoint" in p for p in site.validate())


def test_overlapping_subnets_are_caught():
    site = _valid_site()
    site.enable_openvpn = True
    site.ca_cert_pem = "x"
    site.ovpn_subnet4 = site.wg_subnet4
    assert any("overlap" in p for p in site.validate())


def test_public_subnet_is_caught():
    """10.66.66.0/24 is private; 8.8.8.0/24 would hijack real internet routes."""
    site = _valid_site()
    site.wg_subnet4 = "8.8.8.0/24"
    assert any("not a private range" in p for p in site.validate())


def test_openvpn_without_a_ca_is_caught():
    site = _valid_site()
    site.enable_openvpn = True
    assert any("certificate authority" in p for p in site.validate())


def test_remote_without_ssh_is_caught():
    site = _valid_site()
    site.ssh.host = ""
    assert any("SSH" in p for p in site.validate())


def test_duplicate_peer_names_are_caught():
    site = _valid_site()
    site.peers = [_peer("a", "10.66.66.2/32"), _peer("a", "10.66.66.3/32")]
    assert any("Duplicate" in p for p in site.validate())


def test_out_of_range_port_is_caught():
    site = _valid_site()
    site.wg_port = 70000
    assert any("out of range" in p for p in site.validate())


# ── Serialisation ────────────────────────────────


def test_site_survives_a_round_trip(site):
    restored = Site.from_dict(site.to_dict())
    assert restored.name == site.name
    assert restored.server_wg_private_key == site.server_wg_private_key
    assert restored.ca_cert_pem == site.ca_cert_pem
    assert [p.name for p in restored.peers] == [p.name for p in site.peers]
    assert restored.peers[0].wg_private_key == site.peers[0].wg_private_key
    assert restored.ssh.host == site.ssh.host


def test_unknown_fields_are_ignored_on_load():
    """A site file written by a newer version must not crash an older one."""
    data = Site(name="s").to_dict()
    data["some_future_field"] = True
    assert Site.from_dict(data).name == "s"
