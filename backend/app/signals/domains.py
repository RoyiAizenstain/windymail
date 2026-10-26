"""Address and domain helpers shared by the checks.

The registered domain comes from tldextract's bundled Public Suffix List snapshot:
no network call per request, and no attacker-influenced lookups (ADR-016).
"""

import re
from email.utils import parseaddr

import idna
import tldextract

_extract = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)

# `Name <user@host>`: the address is the last bracketed part, as mail clients read it.
_ANGLE_ADDRESS = re.compile(r"^(?P<name>.*)<(?P<address>[^<>]*)>\s*$", re.DOTALL)


def normalize_host(host: str) -> str | None:
    """Lowercase ASCII (IDNA) form of a hostname, or None if it is not a valid one."""
    host = host.strip().rstrip(".").lower()
    if not host or len(host) > 253:
        return None
    try:
        return idna.encode(host, uts46=True).decode("ascii")
    except idna.IDNAError:
        return None


def registered_domain(host: str) -> str | None:
    """`login.paypal.co.uk` → `paypal.co.uk`. None for IPs and hosts without a public suffix."""
    normalized = normalize_host(host)
    if normalized is None:
        return None
    parts = _extract(normalized)
    if not parts.domain or not parts.suffix:
        return None
    return f"{parts.domain}.{parts.suffix}"


def parse_address(value: str | None) -> tuple[str, str | None]:
    """Splits `Name <user@host>` into the display name and the normalized host."""
    name, address = parseaddr(value or "")
    if not address:
        # The strict parser rejects names like `support@paypal.com <x@evil.xyz>`,
        # which is exactly the impersonation pattern to catch.
        match = _ANGLE_ADDRESS.match(value or "")
        if match:
            name, address = match["name"].strip().strip('"'), match["address"].strip()
    _, at, host = address.rpartition("@")
    return name.strip(), normalize_host(host) if at else None
