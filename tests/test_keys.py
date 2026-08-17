"""
Key generation.

The RFC vector is the important one: WireGuard keys are raw X25519 scalars in
base64, so matching it proves this module produces exactly what `wg pubkey`
would. If it ever stops matching, every key the app has generated is wrong and
no tunnel will handshake — a failure with no other visible symptom until a
client tries to connect.
"""

import base64

import pytest

from server import keys

# RFC 7748, section 6.1
RFC_PRIVATE_HEX = "77076d0a7318a57d3c16c17251b26645df4c2f87ebc0992ab177fba51db92c2a"
RFC_PUBLIC_HEX = "8520f0098930a754748b7ddcb43ef75a0dbf3a0d26381af4eba4a98eaa9b4e6a"


def _b64(hex_string: str) -> str:
    return base64.b64encode(bytes.fromhex(hex_string)).decode()


def test_matches_rfc7748_vector():
    assert keys.derive_wg_public(_b64(RFC_PRIVATE_HEX)) == _b64(RFC_PUBLIC_HEX)


def test_keypair_roundtrips():
    private, public = keys.generate_wg_keypair()
    assert keys.derive_wg_public(private) == public


def test_keys_are_32_bytes():
    private, public = keys.generate_wg_keypair()
    assert len(base64.b64decode(private)) == keys.KEY_BYTES
    assert len(base64.b64decode(public)) == keys.KEY_BYTES


def test_keypairs_are_unique():
    generated = {keys.generate_wg_keypair()[0] for _ in range(25)}
    assert len(generated) == 25


def test_preshared_key_is_32_bytes():
    assert len(base64.b64decode(keys.generate_preshared_key())) == keys.KEY_BYTES


@pytest.mark.parametrize(
    "bad",
    ["", "not!base64!", "AAAA", "short", "x" * 43],
)
def test_malformed_keys_are_rejected(bad):
    assert keys.validate_wg_key(bad) is False


def test_truncated_key_is_rejected_rather_than_padded():
    """
    base64 decoding without validation silently tolerates junk. A key that
    decodes to the wrong length must fail loudly here, not become a valid-
    looking key that produces a tunnel nothing can connect to.
    """
    private, _ = keys.generate_wg_keypair()
    assert keys.validate_wg_key(private[:-4]) is False


def test_derive_raises_on_garbage():
    with pytest.raises(ValueError):
        keys.derive_wg_public("definitely not base64 !!")


def test_tls_crypt_key_has_openvpn_static_key_shape():
    """
    OpenVPN parses this format strictly: 256 bytes as 16 lines of 32 hex
    characters, between the two markers. Anything else and the daemon refuses
    to start.
    """
    text = keys.generate_tls_crypt_key()
    lines = text.strip().splitlines()

    assert lines[0] == "-----BEGIN OpenVPN Static key V1-----"
    assert lines[-1] == "-----END OpenVPN Static key V1-----"

    body = lines[1:-1]
    assert len(body) == 16
    assert all(len(line) == 32 for line in body)
    assert len(bytes.fromhex("".join(body))) == keys.TLS_CRYPT_BYTES
