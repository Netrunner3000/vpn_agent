"""
Config rendering.

Several assertions here are regression guards for directives that break a
tunnel silently — the daemon starts, the handshake completes, and traffic goes
somewhere other than where you intended.
"""

from server import render
from server.model import Site


# ── WireGuard server ─────────────────────────────


def test_server_config_has_the_required_sections(site):
    text = render.wg_server_config(site)
    assert "[Interface]" in text
    assert f"ListenPort = {site.wg_port}" in text
    assert site.server_wg_private_key in text
    assert "[Peer]" in text


def test_server_config_lists_every_enabled_peer(site):
    from server import provision

    provision.add_peer(site, "phone")
    text = render.wg_server_config(site)
    assert text.count("[Peer]") == 2


def test_disabled_peers_are_left_out(site):
    from server import provision

    provision.add_peer(site, "phone")
    provision.set_peer_enabled(site, "phone", False)
    text = render.wg_server_config(site)
    assert text.count("[Peer]") == 1
    assert site.get_peer("phone").wg_public_key not in text


def test_server_config_never_contains_a_peer_private_key(site):
    """
    The server only ever needs peer *public* keys. Shipping a private key to
    the server would hand it the ability to impersonate that device.
    """
    text = render.wg_server_config(site)
    assert site.peers[0].wg_private_key not in text
    assert site.peers[0].wg_public_key in text


def test_empty_server_config_says_so(site):
    site.peers = []
    assert "No enabled peers" in render.wg_server_config(site)


# ── WireGuard client ─────────────────────────────


def test_client_config_pairs_its_own_key_with_the_server_public_key(site):
    peer = site.peers[0]
    text = render.wg_client_config(site, peer)
    assert peer.wg_private_key in text
    assert site.server_wg_public_key in text
    assert site.server_wg_private_key not in text


def test_client_config_sets_dns_to_prevent_leaks(site):
    """
    Without DNS the tunnel hides the traffic while lookups still announce
    every site visited to whatever resolver the local network handed out.
    """
    assert "DNS = 1.1.1.1, 1.0.0.1" in render.wg_client_config(site, site.peers[0])


def test_client_config_keeps_nat_open(site):
    assert "PersistentKeepalive = 25" in render.wg_client_config(site, site.peers[0])


def test_client_config_sets_mtu(site):
    """A too-large MTU black-holes big packets on any path that will not fragment."""
    assert f"MTU = {render.WG_MTU}" in render.wg_client_config(site, site.peers[0])


def test_ipv6_endpoint_is_bracketed(site):
    site.endpoint_host = "2001:db8::1"
    assert "Endpoint = [2001:db8::1]:51820" in render.wg_client_config(site, site.peers[0])


# ── OpenVPN server ───────────────────────────────


def test_openvpn_omits_explicit_exit_notify_on_tcp(site):
    """
    Regression guard. explicit-exit-notify is UDP-only; OpenVPN refuses to
    start with it under proto tcp-server, so the fallback would be dead
    exactly when it was needed.
    """
    assert "explicit-exit-notify" not in render.ovpn_server_config(site)


def test_openvpn_blocks_ipv6_on_a_v4_only_full_tunnel(site):
    """
    Regression guard. There is no server-ipv6 pool, so pushing
    `redirect-gateway ipv6` would send client IPv6 into a tunnel with no IPv6
    address and black-hole it. Blocking v6 instead also stops a dual-stack
    client reaching v6 destinations outside the tunnel.
    """
    text = render.ovpn_server_config(site)
    assert site.full_tunnel
    assert 'push "block-ipv6"' in text
    assert "redirect-gateway ipv6" not in text


def test_openvpn_full_tunnel_redirects_the_gateway(site):
    assert 'push "redirect-gateway def1 bypass-dhcp"' in render.ovpn_server_config(site)


def test_openvpn_split_tunnel_pushes_routes_not_a_gateway(site):
    site.full_tunnel = False
    site.lan_routes = ["192.168.1.0/24"]
    text = render.ovpn_server_config(site)
    assert "redirect-gateway" not in text
    assert 'push "route 192.168.1.0 255.255.255.0"' in text


def test_openvpn_requires_a_client_certificate(site):
    """Without remote-cert-tls, any certificate from the CA could connect."""
    assert "remote-cert-tls client" in render.ovpn_server_config(site)


def test_openvpn_uses_tls_crypt_and_no_dh_params(site):
    text = render.ovpn_server_config(site)
    assert "tls-crypt tls-crypt.key" in text
    # P-256 certificates mean no multi-minute DH generation at install time.
    assert "dh none" in text


def test_openvpn_drops_privileges(site):
    text = render.ovpn_server_config(site)
    assert "user nobody" in text


# ── OpenVPN client ───────────────────────────────


def test_ovpn_profile_is_self_contained(site):
    text = render.ovpn_client_config(site, site.peers[0])
    for tag in ("ca", "cert", "key", "tls-crypt"):
        assert f"<{tag}>" in text and f"</{tag}>" in text


def test_ovpn_profile_pins_the_server(site):
    """
    Stops a stolen client certificate from this same CA being used to
    impersonate the server to other devices.
    """
    assert "remote-cert-tls server" in render.ovpn_client_config(site, site.peers[0])


def test_ovpn_profile_never_carries_the_ca_private_key(site):
    """
    Compromising a device must not let its holder mint new certificates. The
    CA key stays on the machine that created the site.
    """
    text = render.ovpn_client_config(site, site.peers[0])
    assert site.ca_key_pem not in text
    assert site.ca_cert_pem in text


def test_ovpn_profile_uses_tcp(site):
    assert "proto tcp-client" in render.ovpn_client_config(site, site.peers[0])


def test_peer_without_a_certificate_is_refused(site):
    import pytest

    peer = site.peers[0]
    peer.ovpn_cert_pem = ""
    with pytest.raises(ValueError, match="no OpenVPN certificate"):
        render.ovpn_client_config(site, peer)
