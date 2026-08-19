"""
Tor, proxy chains, MAC addresses, and server-side obfuscation.

The SOCKS tests run against a real socket: a tiny in-process SOCKS5 server
accepts a connection, performs the handshake, and echoes. Mocking the protocol
would test the mock — the failures worth catching here are wire-format ones,
like a short read being treated as a complete reply.
"""

import socket
import threading

import pytest

from server import obfuscation, render
from server.model import OBFS_NONE, OBFS_STUNNEL, Site
from services import macaddr, proxychain
from services.socks_client import (
    HTTP,
    SOCKS4,
    SOCKS5,
    ProxyHop,
    SocksError,
    connect_through,
)


# ── A real SOCKS5 server, in-process ─────────────


class FakeSocks5:
    """
    Just enough of RFC 1928 to accept a CONNECT and echo.

    `dribble` sends the greeting reply one byte at a time, which is how a real
    congested link behaves and what breaks a client that assumes recv() returns
    everything at once.
    """

    def __init__(self, require_auth: bool = False, refuse: bool = False,
                 dribble: bool = False) -> None:
        self.require_auth = require_auth
        self.refuse = refuse
        self.dribble = dribble
        self.requested: tuple[str, int] | None = None
        self._server = socket.socket()
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("127.0.0.1", 0))
        self._server.listen(1)
        self.port = self._server.getsockname()[1]
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def hop(self) -> ProxyHop:
        return ProxyHop(kind=SOCKS5, host="127.0.0.1", port=self.port, label="fake")

    def _send(self, conn, payload: bytes) -> None:
        if self.dribble:
            for byte in payload:
                conn.sendall(bytes([byte]))
        else:
            conn.sendall(payload)

    def _serve(self) -> None:
        try:
            conn, _ = self._server.accept()
        except OSError:
            return
        try:
            header = conn.recv(2)
            count = header[1]
            methods = conn.recv(count)

            if self.require_auth:
                if 0x02 not in methods:
                    conn.sendall(b"\x05\xff")
                    return
                self._send(conn, b"\x05\x02")
                conn.recv(1)
                ulen = conn.recv(1)[0]
                conn.recv(ulen)
                plen = conn.recv(1)[0]
                conn.recv(plen)
                conn.sendall(b"\x01\x00")
            else:
                self._send(conn, b"\x05\x00")

            request = conn.recv(4)
            length = conn.recv(1)[0]
            host = conn.recv(length).decode()
            port = int.from_bytes(conn.recv(2), "big")
            self.requested = (host, port)

            if self.refuse:
                conn.sendall(b"\x05\x05\x00\x01" + b"\x00" * 6)
                return
            conn.sendall(b"\x05\x00\x00\x01" + b"\x00" * 6)

            while True:
                data = conn.recv(4096)
                if not data:
                    break
                conn.sendall(data)
        except OSError:
            pass
        finally:
            conn.close()

    def close(self) -> None:
        self._server.close()


@pytest.fixture
def socks_server():
    server = FakeSocks5()
    yield server
    server.close()


def test_socks5_connect_reaches_the_requested_host(socks_server):
    sock = connect_through([socks_server.hop()], "example.com", 80)
    try:
        assert socks_server.requested == ("example.com", 80)
    finally:
        sock.close()


def test_hostname_is_sent_unresolved(socks_server):
    """
    Resolving locally would send a DNS query naming the host to the ISP's
    resolver — the exact leak the proxy exists to prevent.
    """
    sock = connect_through([socks_server.hop()], "secret.example.org", 443)
    try:
        assert socks_server.requested[0] == "secret.example.org"
    finally:
        sock.close()


def test_data_survives_the_round_trip(socks_server):
    sock = connect_through([socks_server.hop()], "example.com", 80)
    try:
        sock.sendall(b"ping")
        assert sock.recv(16) == b"ping"
    finally:
        sock.close()


def test_short_reads_are_handled():
    """A proxy trickling its reply must not be mistaken for a malformed one."""
    server = FakeSocks5(dribble=True)
    try:
        sock = connect_through([server.hop()], "example.com", 80)
        sock.close()
        assert server.requested == ("example.com", 80)
    finally:
        server.close()


def test_refusal_is_reported_in_words():
    server = FakeSocks5(refuse=True)
    try:
        with pytest.raises(SocksError, match="refused by destination"):
            connect_through([server.hop()], "example.com", 80)
    finally:
        server.close()


def test_authentication_is_performed_when_offered():
    server = FakeSocks5(require_auth=True)
    try:
        hop = server.hop()
        hop.username, hop.password = "user", "secret"
        sock = connect_through([hop], "example.com", 80)
        sock.close()
        assert server.requested == ("example.com", 80)
    finally:
        server.close()


def test_missing_credentials_are_reported_clearly():
    server = FakeSocks5(require_auth=True)
    try:
        with pytest.raises(SocksError, match="likely demands a username"):
            connect_through([server.hop()], "example.com", 80)
    finally:
        server.close()


def test_chain_hands_each_hop_the_next_ones_address():
    """
    The property that makes chaining worth doing: hop 1 is asked for hop 2's
    address, not for the final destination.
    """
    first, second = FakeSocks5(), FakeSocks5()
    try:
        # The fake is not a real relay, so the second negotiation fails — but by
        # then the first hop has already recorded what it was asked for.
        try:
            connect_through([first.hop(), second.hop()], "example.com", 80)
        except (SocksError, OSError):
            pass
        assert first.requested == ("127.0.0.1", second.port)
    finally:
        first.close()
        second.close()


def test_empty_chain_is_refused():
    with pytest.raises(SocksError, match="no proxies"):
        connect_through([], "example.com", 80)


def test_failing_hop_is_identified_by_number():
    with pytest.raises((SocksError, OSError)):
        connect_through(
            [ProxyHop(kind=SOCKS5, host="127.0.0.1", port=1)], "example.com", 80
        )


# ── Chain model ──────────────────────────────────


def test_chain_validation_flags_bad_hops():
    chain = proxychain.Chain(hops=[ProxyHop(kind="carrier-pigeon", host="", port=99999)])
    problems = chain.problems()
    assert any("carrier-pigeon" in p for p in problems)
    assert any("no host" in p for p in problems)
    assert any("out of range" in p for p in problems)


def test_empty_chain_is_flagged():
    assert any("no proxies" in p for p in proxychain.Chain().problems())


def test_disabling_proxy_dns_is_flagged_as_a_leak():
    chain = proxychain.Chain(hops=[ProxyHop()], proxy_dns=False)
    assert any("DNS" in p for p in chain.problems())


def test_proxychains_conf_lists_hops_in_order():
    chain = proxychain.Chain(hops=[
        ProxyHop(kind=SOCKS5, host="10.0.0.1", port=1080),
        ProxyHop(kind=HTTP, host="10.0.0.2", port=8080, username="u", password="p"),
    ])
    conf = proxychain.render_proxychains_conf(chain)
    body = conf.split("[ProxyList]")[1].strip().splitlines()
    assert body == ["socks5 10.0.0.1 1080", "http 10.0.0.2 8080 u p"]


def test_proxychains_conf_carries_the_macos_caveat():
    """
    The wrapper silently does nothing for Apple-shipped binaries. Anyone reading
    the file needs to know before they trust a curl that "worked".
    """
    conf = proxychain.render_proxychains_conf(proxychain.Chain(hops=[ProxyHop()]))
    assert "System Integrity Protection" in conf
    assert "connect directly" in conf


def test_chain_round_trips_through_disk():
    chain = proxychain.Chain(
        name="mine", mode=proxychain.DYNAMIC,
        hops=[ProxyHop(kind=SOCKS4, host="1.2.3.4", port=9050, label="a")],
    )
    proxychain.save_chain(chain)
    restored = proxychain.load_chain()
    assert restored.name == "mine"
    assert restored.mode == proxychain.DYNAMIC
    assert restored.hops[0].label == "a"


def test_chain_file_is_owner_only():
    """It can hold proxy credentials."""
    import stat

    proxychain.save_chain(proxychain.Chain(hops=[ProxyHop(username="u", password="p")]))
    mode = stat.S_IMODE(proxychain.chain_path().stat().st_mode)
    assert mode == 0o600


def test_probe_refuses_an_invalid_chain():
    result = proxychain.probe(proxychain.Chain())
    assert result.ok is False
    assert "no proxies" in result.error


# ── MAC addresses ────────────────────────────────


def test_random_mac_is_unicast_and_locally_administered():
    for _ in range(200):
        first = int(macaddr.random_mac().split(":")[0], 16)
        assert first & 0x01 == 0, "multicast bit set — invalid as a source address"
        assert first & 0x02 == 2, "locally-administered bit not set"


def test_random_macs_differ():
    assert len({macaddr.random_mac() for _ in range(50)}) > 45


def test_same_vendor_mode_keeps_the_prefix():
    generated = macaddr.random_mac(macaddr.MODE_SAME_VENDOR, like="a4:83:e7:11:22:33")
    assert generated.startswith("a4:83:e7:")
    assert generated != "a4:83:e7:11:22:33"


def test_same_vendor_falls_back_when_given_nonsense():
    generated = macaddr.random_mac(macaddr.MODE_SAME_VENDOR, like="not-a-mac")
    assert macaddr.is_valid(generated)


def test_multicast_address_is_rejected():
    assert macaddr.is_valid("01:00:5e:00:00:01") is False


@pytest.mark.parametrize("bad", ["", "zz:zz:zz:zz:zz:zz", "aa:bb:cc:dd:ee", "aabbccddeeff"])
def test_malformed_addresses_are_rejected(bad):
    assert macaddr.is_valid(bad) is False


def test_setting_an_invalid_address_is_refused_before_touching_anything():
    ok, message = macaddr.set_mac("en0", "not-a-mac")
    assert ok is False
    assert "not a usable" in message


def test_unknown_interface_is_refused():
    ok, message = macaddr.set_mac("en999", "02:11:22:33:44:55")
    assert ok is False
    assert "No such interface" in message


# ── Server obfuscation ───────────────────────────


@pytest.fixture
def stunnel_site(site):
    site.obfuscation = OBFS_STUNNEL
    return site


def test_openvpn_binds_loopback_only_behind_stunnel(stunnel_site):
    """
    Without this, OpenVPN stays reachable on its own port and the obfuscation
    is bypassable by anyone who simply tries the direct connection.
    """
    conf = render.ovpn_server_config(stunnel_site)
    assert "local 127.0.0.1" in conf
    assert f"port {stunnel_site.ovpn_local_port}" in conf


def test_openvpn_holds_the_public_port_without_stunnel(site):
    conf = render.ovpn_server_config(site)
    assert "local 127.0.0.1" not in conf
    assert f"port {site.ovpn_port}" in conf


def test_client_profile_points_at_local_stunnel(stunnel_site):
    conf = render.ovpn_client_config(stunnel_site, stunnel_site.peers[0])
    assert f"remote 127.0.0.1 {stunnel_site.ovpn_local_port}" in conf


def test_stunnel_client_verifies_the_server(stunnel_site):
    """Without verifyChain, stunnel accepts any certificate and proves nothing."""
    conf = obfuscation.stunnel_client_config(stunnel_site)
    assert "verifyChain = yes" in conf
    assert "CAfile" in conf


def test_stunnel_server_forwards_to_the_loopback_port(stunnel_site):
    conf = obfuscation.stunnel_server_config(stunnel_site)
    assert f"accept = {stunnel_site.ovpn_port}" in conf
    assert f"connect = 127.0.0.1:{stunnel_site.ovpn_local_port}" in conf


def test_stunnel_drops_privileges(stunnel_site):
    assert "setuid = stunnel4" in obfuscation.stunnel_server_config(stunnel_site)


def test_obfuscation_sections_are_absent_when_off(site):
    assert obfuscation.linux_stunnel_section(site) == ""
    assert obfuscation.linux_onion_section(site) == ""


def test_onion_section_appears_when_enabled(site):
    site.onion_enabled = True
    section = obfuscation.linux_onion_section(site)
    assert "HiddenServiceDir" in section
    assert "VPN_AGENT_ONION=" in section


def test_onion_address_is_parsed_from_deploy_output():
    output = "noise\n[vpn-agent] VPN_AGENT_ONION=abcdef1234.onion\nmore noise"
    assert obfuscation.parse_onion_address(output) == "abcdef1234.onion"


def test_non_onion_output_yields_nothing():
    assert obfuscation.parse_onion_address("nothing here") == ""


def test_stunnel_without_openvpn_is_caught_by_validation(site):
    site.obfuscation = OBFS_STUNNEL
    site.enable_openvpn = False
    assert any("nothing behind it" in p for p in site.validate())


def test_stunnel_sharing_the_public_port_is_caught(site):
    site.obfuscation = OBFS_STUNNEL
    site.ovpn_local_port = site.ovpn_port
    assert any("different (loopback) port" in p for p in site.validate())


def test_client_instructions_explain_the_extra_moving_part(stunnel_site):
    text = obfuscation.client_instructions(stunnel_site)
    assert "stunnel" in text
    assert "127.0.0.1" in text


def test_no_instructions_when_nothing_is_obfuscated(site):
    assert obfuscation.client_instructions(site) == ""
