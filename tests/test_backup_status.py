"""
Encrypted backup, and parsing live server status.

The backup format guards the only copy of a certificate authority, so the
failure cases matter more than the happy path: a wrong passphrase and a
tampered file must both be refused, and the ciphertext must not leak what it
is protecting.
"""

import stat
import time

import pytest

from server import backup, deploy, provision, store

PASSPHRASE = "correct horse battery staple"


# ── Backup round trip ────────────────────────────


def test_round_trip_preserves_every_secret(site, tmp_path):
    path = backup.write_backup(site, PASSPHRASE, tmp_path / "b")
    restored = backup.read_backup(path, PASSPHRASE)

    assert restored.server_wg_private_key == site.server_wg_private_key
    assert restored.ca_key_pem == site.ca_key_pem
    assert restored.ca_cert_pem == site.ca_cert_pem
    assert restored.tls_crypt_key == site.tls_crypt_key
    assert restored.peers[0].wg_private_key == site.peers[0].wg_private_key
    assert restored.peers[0].wg_preshared_key == site.peers[0].wg_preshared_key
    assert restored.peers[0].ovpn_key_pem == site.peers[0].ovpn_key_pem


def test_ciphertext_does_not_leak_key_material(site, tmp_path):
    """The point of the exercise, stated as a test."""
    blob = backup.write_backup(site, PASSPHRASE, tmp_path / "b").read_bytes()
    assert site.ca_key_pem.encode() not in blob
    assert site.server_wg_private_key.encode() not in blob
    assert site.peers[0].wg_private_key.encode() not in blob


def test_backup_file_is_owner_only(site, tmp_path):
    path = backup.write_backup(site, PASSPHRASE, tmp_path / "b")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_suffix_is_applied(site, tmp_path):
    assert backup.write_backup(site, PASSPHRASE, tmp_path / "b").suffix == backup.SUFFIX


def test_each_backup_uses_fresh_salt_and_nonce(site, tmp_path):
    """
    Reusing a nonce with the same key breaks AES-GCM badly. Fresh randomness
    each time also means two backups of an unchanged site are not identical.
    """
    a = backup.write_backup(site, PASSPHRASE, tmp_path / "a").read_bytes()
    b = backup.write_backup(site, PASSPHRASE, tmp_path / "b").read_bytes()
    assert a != b


# ── Failure cases ────────────────────────────────


def test_wrong_passphrase_is_refused(site, tmp_path):
    path = backup.write_backup(site, PASSPHRASE, tmp_path / "b")
    with pytest.raises(backup.BackupError, match="Could not decrypt"):
        backup.read_backup(path, "not the passphrase")


def test_tampered_ciphertext_is_detected(site, tmp_path):
    """AES-GCM authenticates, so an altered file fails rather than decrypting wrongly."""
    path = backup.write_backup(site, PASSPHRASE, tmp_path / "b")
    raw = bytearray(path.read_bytes())
    index = raw.find(b'"ciphertext"') + 40
    raw[index] ^= 0x01
    path.write_bytes(bytes(raw))

    with pytest.raises(backup.BackupError):
        backup.read_backup(path, PASSPHRASE)


def test_tampered_header_is_detected(site, tmp_path):
    """
    The header is authenticated as additional data, so editing the recorded
    site name invalidates the file rather than silently mislabelling it.
    """
    path = backup.write_backup(site, PASSPHRASE, tmp_path / "b")
    path.write_bytes(path.read_bytes().replace(b'"Test Site"', b'"Other Site"'))
    with pytest.raises(backup.BackupError):
        backup.read_backup(path, PASSPHRASE)


def test_empty_passphrase_is_refused(site):
    with pytest.raises(backup.BackupError, match="passphrase is required"):
        backup.export_site(site, "")


def test_foreign_file_is_refused(tmp_path):
    path = tmp_path / "random.vpnbackup"
    path.write_bytes(b"just some bytes")
    with pytest.raises(backup.BackupError, match="Not a VPN Agent backup"):
        backup.read_backup(path, PASSPHRASE)


def test_future_format_version_is_refused(site, tmp_path):
    path = backup.write_backup(site, PASSPHRASE, tmp_path / "b")
    path.write_bytes(path.read_bytes().replace(b'"version": 1', b'"version": 99'))
    with pytest.raises(backup.BackupError, match="not supported"):
        backup.read_backup(path, PASSPHRASE)


# ── Header and restore ───────────────────────────


def test_header_is_readable_without_the_passphrase(site, tmp_path):
    """Lets the UI say which site a file holds before asking for anything."""
    blob = backup.write_backup(site, PASSPHRASE, tmp_path / "b").read_bytes()
    info = backup.describe(blob)
    assert info["site"] == site.name
    assert info["version"] == backup.FORMAT_VERSION


def test_restore_refuses_to_clobber(site, tmp_path):
    path = backup.write_backup(site, PASSPHRASE, tmp_path / "b")
    with pytest.raises(backup.BackupError, match="already exists"):
        backup.restore(path, PASSPHRASE)


def test_restore_after_loss(site, tmp_path):
    path = backup.write_backup(site, PASSPHRASE, tmp_path / "b")
    original_key = site.server_wg_private_key

    store.delete_site(site.name)
    assert store.list_sites() == []

    restored = backup.restore(path, PASSPHRASE)
    assert restored.server_wg_private_key == original_key
    assert store.load_site(site.name).ca_key_pem == site.ca_key_pem


def test_restore_can_overwrite_when_asked(site, tmp_path):
    path = backup.write_backup(site, PASSPHRASE, tmp_path / "b")
    provision.add_peer(site, "extra")
    assert len(store.load_site(site.name).peers) == 2

    backup.restore(path, PASSPHRASE, overwrite=True)
    assert len(store.load_site(site.name).peers) == 1


@pytest.mark.parametrize("weak", ["short", "vpn", "password"])
def test_weak_passphrases_are_flagged(weak):
    assert backup.passphrase_problems(weak)


def test_a_reasonable_passphrase_is_not_flagged():
    assert backup.passphrase_problems(PASSPHRASE) == []


# ── wg dump parsing ──────────────────────────────


SERVER_PRIVATE = "iOelPLZ7oCK1n4Wj8Vf0KRAeMY1DhLcVXjTsbTZ8Wl4="

DUMP = (
    f"{SERVER_PRIVATE}\tsXPkQxZ+Vv2wHc1kK9YyC0eQZ1mJ8hT7bN3aR5uW6Xo=\t51820\toff\n"
    "peerKeyOne=\tpskOne=\t198.51.100.4:53211\t10.66.66.2/32\t1786978072\t596\t476\t25\n"
    "peerKeyTwo=\tpskTwo=\t(none)\t10.66.66.3/32\t0\t0\t0\toff\n"
)


def test_dump_parsing_drops_the_server_private_key():
    """
    Field 2 of the interface line is the server's private key. Anything that
    retains it can impersonate the server, and a status display has no use for
    it whatsoever.
    """
    status = deploy.parse_wg_dump(DUMP)
    assert SERVER_PRIVATE not in repr(status)
    for peer in status.peers:
        assert SERVER_PRIVATE not in repr(peer)


def test_dump_parsing_drops_preshared_keys():
    status = deploy.parse_wg_dump(DUMP)
    assert "pskOne=" not in repr(status)


def test_dump_parsing_reads_peer_fields():
    status = deploy.parse_wg_dump(DUMP)
    assert status.wg_active is True
    assert len(status.peers) == 2

    first = status.peers[0]
    assert first.public_key == "peerKeyOne="
    assert first.endpoint == "198.51.100.4:53211"
    assert first.allowed_ips == "10.66.66.2/32"
    assert first.rx_bytes == 596 and first.tx_bytes == 476


def test_peer_that_never_connected():
    never = deploy.parse_wg_dump(DUMP).peers[1]
    assert never.last_handshake == 0
    assert never.endpoint == ""
    assert never.connected is False
    assert never.describe_handshake() == "never"


def test_empty_dump_means_wireguard_is_down():
    status = deploy.parse_wg_dump("")
    assert status.wg_active is False
    assert status.peers == []


def test_recent_handshake_counts_as_connected():
    """WireGuard rekeys about every two minutes, so ~3 minutes is the cutoff."""
    now = int(time.time())
    assert deploy.PeerStatus(public_key="k", last_handshake=now - 30).connected is True
    assert deploy.PeerStatus(public_key="k", last_handshake=now - 600).connected is False


def test_handshake_ages_read_naturally():
    now = int(time.time())
    describe = lambda ago: deploy.PeerStatus(public_key="k", last_handshake=now - ago).describe_handshake()
    assert describe(30).endswith("s ago")
    assert describe(300).endswith("m ago")
    assert describe(7200).endswith("h ago")
    assert describe(200000).endswith("d ago")


def test_transfer_is_human_readable():
    peer = deploy.PeerStatus(public_key="k", rx_bytes=1048576, tx_bytes=512)
    assert "1.0 MiB" in peer.describe_transfer()
    assert "512 B" in peer.describe_transfer()


def test_malformed_dump_lines_are_skipped():
    status = deploy.parse_wg_dump("iface\tkey\t51820\toff\ngarbage\n")
    assert status.peers == []


def test_status_is_refused_for_native_sites(site):
    from server.model import MODE_NATIVE

    site.mode = MODE_NATIVE
    result = deploy.server_status(site)
    assert result.reachable is False
    assert "remote" in result.error.lower()
