import ipaddress
import socket
import asyncio
from urllib.parse import urlparse

async def is_safe_url(url: str) -> bool:
    """
    Prevents Server-Side Request Forgery (SSRF) by ensuring the URL
    does not point to a local, private, or loopback IP address.
    """
    try:
        # Ignore ytsearch prefixes before parsing
        if url.startswith("ytsearch"):
            return True

        parsed_url = urlparse(url)
        hostname = parsed_url.hostname
        if not hostname:
            return False

        # Resolve hostname to IP asynchronously
        loop = asyncio.get_event_loop()
        addr_info = await loop.getaddrinfo(hostname, None)
        if not addr_info:
            return False

        ip_addr = addr_info[0][4][0]
        ip = ipaddress.ip_address(ip_addr)

        # Check against private, loopback, and other restricted networks
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            return False

        return True
    except Exception:
        # If hostname cannot be resolved or any other error, fail safe
        return False
