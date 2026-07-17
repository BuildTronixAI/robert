"""
SSRF protection for Robert — URL allowlist + private IP blocking.
v1.4: vendor domains for Robert tools; supabase.co project-host helper.
All fetch paths must call validate_url() before making any HTTP request.
"""
import ipaddress
import os
import socket
from urllib.parse import urlparse

# ── IP PINNING RULE (enforced) ────────────────────────────────────────────────
# Any domain added to ALLOWED_DOMAINS requires EITHER:
#   (a) IP pinning implementation, or
#   (b) Explicit written sign-off that the domain is fully controlled by a
#       trusted operator with no third-party DNS delegation.
# Current domains are fixed vendor infrastructure (not user-controlled).
# ─────────────────────────────────────────────────────────────────────────────
ALLOWED_DOMAINS = {
    "api.weatherapi.com",
    "graph.microsoft.com",
    "openrouter.ai",
    "api.telegram.org",
    "api.resend.com",
    "api.sendgrid.com",
    "api.github.com",
    "pypi.org",
    "files.pythonhosted.org",
    "docs.anthropic.com",
    "platform.openai.com",
    "nextjs.org",
    "supabase.com",
    "python.langchain.com",
    "langchain-ai.github.io",
}

PRIVATE_IP_RANGES = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("::ffff:0:0/96"),
]


def _is_supabase_host(hostname: str) -> bool:
    """Allow only *.supabase.co project hosts (and configured SUPABASE_URL host)."""
    if not hostname:
        return False
    host = hostname.lower()
    if host.endswith(".supabase.co") or host == "supabase.co":
        return True
    configured = os.environ.get("SUPABASE_URL", "")
    if configured:
        try:
            cfg_host = urlparse(configured).hostname or ""
            if cfg_host and host == cfg_host.lower():
                return True
        except Exception:
            pass
    return False


def is_allowed_hostname(hostname: str) -> bool:
    if not hostname:
        return False
    host = hostname.lower()
    if host in ALLOWED_DOMAINS:
        return True
    if _is_supabase_host(host):
        return True
    return False


def validate_url(url: str) -> None:
    """
    Validate that a URL is safe to fetch.
    Raises ValueError if unsafe.
    """
    parsed = urlparse(url)

    if not parsed.hostname:
        raise ValueError("URL has no hostname")

    if parsed.scheme not in ("https",):
        raise ValueError(f"Only HTTPS allowed. Got: {parsed.scheme}")

    if not is_allowed_hostname(parsed.hostname):
        raise ValueError(f"Domain not in allowlist: {parsed.hostname}")

    if parsed.port is not None and parsed.port != 443:
        raise ValueError(f"Non-standard port not allowed: {parsed.port}")

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
