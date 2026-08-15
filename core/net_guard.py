"""
Purpose: SSRF guard for any user/merchant-supplied URL the server itself fetches or calls.
Used by: ezzy_api.views (webhook registration), product.image_import (product photo download).
Notes: Resolves every address the host maps to — a public hostname can still point at 127.0.0.1.
"""
import ipaddress
import socket
from urllib.parse import urlparse


def validate_public_url(url):
    """Only allow http/https to public hosts.

    Rejects loopback, private, link-local, reserved, multicast and unspecified
    targets. Returns (ok: bool, reason: str).
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False, 'Invalid URL'

    if parsed.scheme not in ('http', 'https'):
        return False, 'Only http/https URLs are allowed'

    host = parsed.hostname
    if not host:
        return False, 'URL must include a host'

    try:
        # Resolve every address the host maps to and reject internal ranges.
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False, 'Host could not be resolved'

    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return False, 'Host resolved to an invalid address'
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return False, 'URL resolves to a non-public address'

    return True, ''
