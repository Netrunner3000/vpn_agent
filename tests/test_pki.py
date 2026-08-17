"""
The OpenVPN certificate authority.

The extended-key-usage assertions matter most. The client asserts
`remote-cert-tls server`; if the server certificate were not marked serverAuth,
or client certificates were not confined to clientAuth, anyone holding a client
certificate from this same CA could impersonate the server to your other
devices — a working tunnel to an attacker, with no warning.
"""

import datetime as dt
import ipaddress

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID

from server import pki


@pytest.fixture
def ca():
    return pki.create_ca("Test Site")


def _load(pem: str) -> x509.Certificate:
    return x509.load_pem_x509_certificate(pem.encode())


def _eku(cert: x509.Certificate):
    return cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value


def test_ca_is_a_ca_and_self_signed(ca):
    cert = _load(ca[0])
    constraints = cert.extensions.get_extension_for_class(x509.BasicConstraints).value
    assert constraints.ca is True
    assert constraints.path_length == 0
    assert cert.subject == cert.issuer


def test_ca_can_sign_certificates(ca):
    usage = _load(ca[0]).extensions.get_extension_for_class(x509.KeyUsage).value
    assert usage.key_cert_sign is True
    assert usage.crl_sign is True


def test_server_cert_is_serverauth_only(ca):
    cert_pem, _ = pki.issue_server_cert(*ca, common_name="Test server")
    usages = list(_eku(_load(cert_pem)))
    assert usages == [ExtendedKeyUsageOID.SERVER_AUTH]


def test_client_cert_is_clientauth_only(ca):
    cert_pem, _ = pki.issue_client_cert(*ca, common_name="laptop")
    usages = list(_eku(_load(cert_pem)))
    assert usages == [ExtendedKeyUsageOID.CLIENT_AUTH]


def test_client_cannot_masquerade_as_server(ca):
    """The whole point of pinning EKUs — stated as its own test."""
    client_pem, _ = pki.issue_client_cert(*ca, common_name="laptop")
    assert ExtendedKeyUsageOID.SERVER_AUTH not in list(_eku(_load(client_pem)))


def test_leaves_are_not_cas(ca):
    for pem, _ in (
        pki.issue_server_cert(*ca, common_name="s"),
        pki.issue_client_cert(*ca, common_name="c"),
    ):
        assert _load(pem).extensions.get_extension_for_class(
            x509.BasicConstraints
        ).value.ca is False


def test_leaf_is_signed_by_the_ca(ca):
    ca_cert = _load(ca[0])
    leaf = _load(pki.issue_client_cert(*ca, common_name="laptop")[0])
    assert leaf.issuer == ca_cert.subject
    # Raises InvalidSignature if the chain does not hold.
    ca_cert.public_key().verify(
        leaf.signature,
        leaf.tbs_certificate_bytes,
        ec.ECDSA(leaf.signature_hash_algorithm),
    )


def test_private_key_matches_its_certificate(ca):
    cert_pem, key_pem = pki.issue_server_cert(*ca, common_name="Test server")
    key = serialization.load_pem_private_key(key_pem.encode(), password=None)
    assert key.public_key().public_numbers() == _load(cert_pem).public_key().public_numbers()


def test_server_cert_covers_a_literal_ip_endpoint(ca):
    """
    A client verifying the server by address needs that address in the SAN.
    Without it, a VPS reached by IP fails verification.
    """
    cert_pem, _ = pki.issue_server_cert(*ca, common_name="s", endpoint_host="203.0.113.10")
    san = _load(cert_pem).extensions.get_extension_for_class(
        x509.SubjectAlternativeName
    ).value
    assert ipaddress.ip_address("203.0.113.10") in san.get_values_for_type(x509.IPAddress)


def test_server_cert_covers_a_dns_endpoint(ca):
    cert_pem, _ = pki.issue_server_cert(*ca, common_name="s", endpoint_host="vpn.example.org")
    san = _load(cert_pem).extensions.get_extension_for_class(
        x509.SubjectAlternativeName
    ).value
    assert "vpn.example.org" in san.get_values_for_type(x509.DNSName)


def test_display_names_become_valid_dns_sans(ca):
    """
    Site names are human text ("Home Server"); a DNSName entry must look like a
    hostname or cryptography rejects the whole certificate.
    """
    cert_pem, _ = pki.issue_server_cert(*ca, common_name="Home Server v2!")
    names = _load(cert_pem).extensions.get_extension_for_class(
        x509.SubjectAlternativeName
    ).value.get_values_for_type(x509.DNSName)
    assert names and all(" " not in n and "!" not in n for n in names)


def test_serial_numbers_are_unique(ca):
    serials = {_load(pki.issue_client_cert(*ca, common_name=f"p{i}")[0]).serial_number
               for i in range(10)}
    assert len(serials) == 10


def test_certificates_are_valid_now(ca):
    """Clock skew between this machine and the server must not break the tunnel."""
    now = dt.datetime.now(dt.timezone.utc)
    cert = _load(pki.issue_client_cert(*ca, common_name="laptop")[0])
    assert cert.not_valid_before_utc <= now < cert.not_valid_after_utc


def test_describe_cert_reports_expiry(ca):
    info = pki.describe_cert(ca[0])
    assert info["expired"] is False
    assert info["days_remaining"] > 3000
    assert "Test Site" in info["common_name"]
