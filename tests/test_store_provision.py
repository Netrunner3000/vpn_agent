"""
Persistence and peer lifecycle.

The site file holds the only copy of the server and CA private keys. Losing or
corrupting it cannot be recovered from, so the write path and its permissions
are worth pinning.
"""

import json
import stat

import pytest

from server import paths, provision, store


# ── Storage ──────────────────────────────────────


def test_site_round_trips_through_disk(site):
    loaded = store.load_site(site.name)
    assert loaded.server_wg_private_key == site.server_wg_private_key
    assert loaded.ca_key_pem == site.ca_key_pem
    assert [p.name for p in loaded.peers] == ["laptop"]


def test_site_file_is_owner_only(site):
    mode = stat.S_IMODE(paths.site_file(site.name).stat().st_mode)
    assert mode == 0o600


def test_state_directory_is_owner_only(site):
    mode = stat.S_IMODE(paths.sites_dir().stat().st_mode)
    assert mode == 0o700


def test_loading_a_world_readable_site_is_refused(site):
    """
    By the time anyone notices the permissions slipped, the keys may already
    have been copied. Fail loudly rather than loading and hoping.
    """
    path = paths.site_file(site.name)
    path.chmod(0o644)
    with pytest.raises(store.InsecurePermissions):
        store.load_site(site.name)


def test_permission_check_can_be_bypassed_deliberately(site):
    paths.site_file(site.name).chmod(0o644)
    assert store.load_site(site.name, strict_permissions=False).name == site.name


def test_save_is_atomic(site):
    """
    A half-written site file would mean losing every peer's keys, so the write
    goes to a temp file and is renamed into place.
    """
    provision.add_peer(site, "phone")
    leftovers = list(paths.sites_dir().glob("*.tmp"))
    assert leftovers == []
    assert json.loads(paths.site_file(site.name).read_text())["peers"]


def test_listing_and_deleting(site):
    assert site.name in store.list_sites()
    assert store.delete_site(site.name) is True
    assert store.list_sites() == []
    assert store.delete_site(site.name) is False


def test_missing_site_raises(site):
    with pytest.raises(FileNotFoundError):
        store.load_site("nope")


def test_unreadable_site_file_does_not_break_listing(site):
    (paths.sites_dir() / "broken.json").write_text("{not json")
    assert site.name in store.list_sites()


# ── Provisioning ─────────────────────────────────


def test_init_generates_a_complete_identity(site):
    assert site.server_wg_private_key
    assert site.server_wg_public_key
    assert site.ca_cert_pem and site.ca_key_pem
    assert site.tls_crypt_key


def test_creating_a_duplicate_site_is_refused(site):
    with pytest.raises(FileExistsError):
        provision.init_site(site.name, "remote")


def test_each_peer_gets_unique_material(site):
    provision.add_peer(site, "phone")
    laptop, phone = site.peers
    assert laptop.wg_private_key != phone.wg_private_key
    assert laptop.wg_preshared_key != phone.wg_preshared_key
    assert laptop.ip4 != phone.ip4


def test_duplicate_peer_name_is_refused(site):
    with pytest.raises(ValueError, match="already exists"):
        provision.add_peer(site, "laptop")


def test_empty_peer_name_is_refused(site):
    with pytest.raises(ValueError):
        provision.add_peer(site, "   ")


def test_peer_is_persisted_immediately(site):
    """
    A generated private key that is not saved can never be reproduced — the
    config just handed to someone would stop working.
    """
    provision.add_peer(site, "phone")
    assert "phone" in [p.name for p in store.load_site(site.name).peers]


def test_removing_a_peer_frees_its_address(site):
    provision.add_peer(site, "phone")          # .3
    provision.remove_peer(site, "laptop")      # frees .2
    new = provision.add_peer(site, "tablet")
    assert new.ip4 == "10.66.66.2"


def test_disabling_keeps_the_keys(site):
    before = site.peers[0].wg_private_key
    provision.set_peer_enabled(site, "laptop", False)
    peer = store.load_site(site.name).get_peer("laptop")
    assert peer.enabled is False
    assert peer.wg_private_key == before


def test_rotation_replaces_keys_but_keeps_the_address(site):
    peer = site.peers[0]
    old_private, old_address, old_cert = peer.wg_private_key, peer.address4, peer.ovpn_cert_pem

    rotated = provision.rotate_peer_keys(site, "laptop")

    assert rotated.wg_private_key != old_private
    assert rotated.ovpn_cert_pem != old_cert
    assert rotated.address4 == old_address


def test_rotating_an_unknown_peer_raises(site):
    with pytest.raises(ValueError):
        provision.rotate_peer_keys(site, "ghost")


def test_server_rotation_leaves_the_ca_alone(site):
    old_key, old_ca = site.server_wg_private_key, site.ca_cert_pem
    provision.rotate_server_keys(site)
    assert site.server_wg_private_key != old_key
    assert site.ca_cert_pem == old_ca


def test_changing_the_endpoint_reissues_the_server_certificate(site):
    """
    The certificate's subject names must still cover the endpoint, or clients
    verifying the server start failing.
    """
    before = site.server_cert_pem
    provision.set_endpoint(site, "198.51.100.5")
    assert site.server_cert_pem != before
    assert site.endpoint_host == "198.51.100.5"


def test_enabling_openvpn_later_issues_certs_for_existing_peers():
    site = provision.init_site("No VPN", "remote", endpoint_host="203.0.113.1",
                               enable_openvpn=False)
    provision.add_peer(site, "laptop")
    assert site.peers[0].has_openvpn is False

    provision.enable_openvpn(site)
    assert site.peers[0].has_openvpn is True
