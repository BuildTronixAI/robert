"""Tests for url_validator.py — SSRF protection v1.3"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from tools.url_validator import validate_url


def test_http_not_allowed():
    with pytest.raises(ValueError, match="Only HTTPS"):
        validate_url("http://api.weatherapi.com/v1/current.json")

def test_unlisted_domain_blocked():
    with pytest.raises(ValueError, match="not in allowlist"):
        validate_url("https://evil.com/steal-creds")

def test_nonstandard_port_blocked():
    with pytest.raises(ValueError, match="Non-standard port"):
        validate_url("https://api.weatherapi.com:9000/v1/current.json")

def test_loopback_blocked():
    with pytest.raises(ValueError):
        validate_url("http://127.0.0.1:8080/")

def test_no_hostname():
    with pytest.raises(ValueError, match="no hostname"):
        validate_url("https://")

def test_ipv4_mapped_ipv6_range():
    """Verify ::ffff:0:0/96 catches IPv4-mapped IPv6 addresses."""
    import ipaddress
    mapped = ipaddress.ip_address("::ffff:192.168.1.1")
    net = ipaddress.ip_network("::ffff:0:0/96")
    assert mapped in net, "::ffff: IPv4-mapped address must be caught"

def test_cgnat_range_present():
    """Verify CGNAT range is in the blocklist."""
    import ipaddress
    from tools.url_validator import PRIVATE_IP_RANGES
    cgnat = ipaddress.ip_network("100.64.0.0/10")
    assert cgnat in PRIVATE_IP_RANGES, "CGNAT range must be blocked"
