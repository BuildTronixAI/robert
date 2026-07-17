"""
SSRF protection for Robert — URL allowlist + private IP blocking.
v1.3: Added CGNAT (100.64.0.0/10), IPv4-mapped IPv6, port validation.
All fetch paths must call validate_url() before making any HTTP request.
"""
import ipaddress
import socket
from urllib.parse import urlparse

# ── IP PINNING RULE (enforced) ────────────────────────────────────────────────
# Any domain added to ALLOWED_DOMAINS requires EITHER:
#   (a) IP pinning implementation: resolve once, pass resolved IP to fetcher,
#       verify TLS/SNI against original hostname — no second DNS resolution, or
#   (b) Explicit written sign-off that the domain is fully controlled by a
#       trusted operator with no third-party DNS delegation.
#
# This rule exists because:
#   - Subdomain takeover can make "trusted" domains exploitable with no code change
#   - DNS rebinding: malicious resolver returns public IP on query 1, private on query 2
#   - Split-horizon DNS: domain resolves differently from inside vs outside network
#
# Current domains are fixed vendor infrastructure (not user-controlled or configurable).
# TOCTOU risk is low. IP pinning required before adding any new domain.
# ─────────────────────────────────────────────────────────────────────────────
ALLOWED_DOMAINS = {
    "api.weatherapi.com",
    "graph.microsoft.com",
    "openrouter.ai",
    "api.telegram.org",
    "api.resend.com",
    "api.sendgrid.com",
    # Add each domain explicitly. No wildcards.
    # Read the IP PINNING RULE above before adding any domain.
    # Supabase project hosts are tenant-specific — callers should use
    # safe_fetch(..., skip_allowlist=True) only after host ends with .supabase.co
}

PRIVATE_IP_RANGES = [
    # IPv4
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),      # CGNAT — RFC 6598
    ipaddress.ip_network("127.0.0.0/8"),         # Loopback
    ipaddress.ip_network("169.254.0.0/16"),      # Link-local — AWS/cloud metadata
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    # IPv6
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),           # IPv6 link-local
    ipaddress.ip_network("::ffff:0:0/96"),       # IPv4-mapped IPv6
]


def validate_url(url: str) -> None:
    """
    Validate that a URL is safe to fetch.
    Raises ValueError if:
    - URL has no hostname
    - Scheme is not HTTPS
    - Domain is not in ALLOWED_DOMAINS
    - Non-standard port (anything other than 443)
    - DNS resolves to any private/internal IP

    Call this at the top of every fetch path. Do not bypass.
    """
    parsed = urlparse(url)

    if not parsed.hostname:
        raise ValueError("URL has no hostname")

    if parsed.scheme not in ("https",):
        raise ValueError(f"Only HTTPS allowed. Got: {parsed.scheme}")

    if parsed.hostname not in ALLOWED_DOMAINS:
        raise ValueError(f"Domain not in allowlist: {parsed.hostname}")

    if parsed.port is not None and parsed.port != 443:
        raise ValueError(f"Non-standard port not allowed: {parsed.port}")

    # Use getaddrinfo to check ALL returned addresses (A and AAAA records)
    try:
        results = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        raise ValueError(f"DNS resolution failed for: {parsed.hostname}")

    for (_, _, _, _, sockaddr) in results:
        raw_addr = sockaddr[0]
        try:
            addr = ipaddress.ip_address(raw_addr)
        except ValueError:
            raise ValueError(f"Could not parse resolved address: {raw_addr}")
        for net in PRIVATE_IP_RANGES:
            if addr in net:
                raise ValueError(f"Private/internal IP blocked: {raw_addr} ({parsed.hostname})")
