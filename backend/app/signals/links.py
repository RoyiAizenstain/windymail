"""Where do the links really go? (US-03)

Every link is normalized the way a browser would read it before any check (T3):
whitespace and backslashes, `user@host` (`https://paypal.com@evil.xyz` goes to
evil.xyz), percent-encoding, punycode, and numeric IPv4 forms (`http://3232235777`).
URLs are never fetched or resolved: no network call on attacker-supplied input.
"""

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup

from app.models import AnalyzeRequest
from app.signals import lookalike
from app.signals.base import Finding
from app.signals.domains import normalize_host, registered_domain

MAX_LINKS = 200

SCRIPT_SCHEMES = {"javascript", "vbscript", "data"}
WEB_SCHEMES = {"http", "https"}

SHORTENERS = {
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "is.gd", "buff.ly", "rebrand.ly",
    "cutt.ly", "shorturl.at", "rb.gy", "t.ly", "tiny.cc", "bl.ink", "s.id", "lnkd.in",
}  # fmt: skip

# Newsletter services send every link through their own click-tracking domain, so
# text and destination differ on most legitimate newsletters. The text check skips
# them; the other checks still run.
CLICK_TRACKERS = {
    "sendgrid.net", "list-manage.com", "mailchimp.com", "mandrillapp.com", "hubspotlinks.com",
    "hs-sites.com", "mailgun.org", "sparkpostmail.com", "exct.net", "mcsv.net", "rs6.net",
    "awstrack.me", "klclick.com", "ctrk.klclick.com", "substack.com",
}  # fmt: skip

_TAB_OR_NEWLINE = re.compile(r"[\t\n\r]")
_C0_OR_SPACE = "".join(chr(code) for code in range(0x21))
_TEXT_URL = re.compile(r"https?://[^\s<>\"']+|www\.[^\s<>\"']+", re.IGNORECASE)
_LOOKS_LIKE_URL = re.compile(
    r"(?:[a-z][a-z0-9+.-]*://)?[^\s/@]+(?:@[^\s/]+)?\.[a-z]{2,}\.?(?:[/?#:]\S*)?", re.IGNORECASE
)


@dataclass(frozen=True)
class Destination:
    scheme: str
    host: str | None  # normalized hostname, or the IP in standard form
    is_ip: bool = False


def destination(href: str) -> Destination | None:
    """Where a browser would go for this href. None for relative, mailto, tel, or junk."""
    # Browsers trim control characters and spaces at the ends, drop tabs and newlines
    # anywhere, and treat \\ as / (WHATWG URL parsing).
    url = _TAB_OR_NEWLINE.sub("", href.strip(_C0_OR_SPACE)).replace("\\", "/")
    if url.lower().startswith("www."):
        url = "http://" + url
    elif url.startswith("//"):
        url = "https:" + url
    scheme, _, _ = url.partition(":")
    scheme = scheme.lower()
    if scheme in SCRIPT_SCHEMES:
        return Destination(scheme, None)
    if scheme not in WEB_SCHEMES:
        return None
    try:
        raw_host = urlsplit(url).hostname
    except ValueError:
        return None
    if not raw_host:
        return None
    host = unquote(raw_host).strip().rstrip(".").lower()
    ip = _ip(host)
    if ip:
        return Destination(scheme, ip, is_ip=True)
    normalized = normalize_host(host)
    return Destination(scheme, normalized) if normalized else None


def _ip(host: str) -> str | None:
    if ":" in host:
        try:
            return str(ipaddress.IPv6Address(host))
        except ValueError:
            return None
    return _ipv4(host)


def _ipv4(host: str) -> str | None:
    """IPv4 as browsers parse it (WHATWG): `3232235777`, `0xC0A80001`, `0300.0250.0.1`."""
    parts = host.split(".")
    if not 1 <= len(parts) <= 4:
        return None
    numbers = []
    for part in parts:
        if not part.isascii():
            return None
        try:
            if part[:2] in ("0x", "0X"):
                numbers.append(int(part[2:] or "0", 16))
            elif len(part) > 1 and part.startswith("0"):
                numbers.append(int(part, 8))
            elif part.isdigit():
                numbers.append(int(part))
            else:
                return None
        except ValueError:
            return None
    last = numbers.pop()
    if any(n > 255 for n in numbers) or last >= 256 ** (4 - len(numbers)):
        return None
    value = sum(n << (8 * (3 - i)) for i, n in enumerate(numbers)) + last
    return str(ipaddress.IPv4Address(value))


def extract_links(request: AnalyzeRequest) -> list[tuple[str, str]]:
    """(href, visible text) pairs from the HTML body, then bare URLs in the text body."""
    links: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(href: str, text: str) -> None:
        if (href, text) not in seen and len(links) < MAX_LINKS:
            seen.add((href, text))
            links.append((href, text))

    if request.body_html:
        soup = BeautifulSoup(request.body_html, "html.parser")
        for anchor in soup.find_all("a", href=True):
            add(str(anchor["href"]), anchor.get_text(" ", strip=True))
    for match in _TEXT_URL.finditer(request.body_text):
        url = match.group(0).rstrip(".,;:!?)]}'\"")
        add(url, url)
    return links


def _site(dest: Destination) -> str | None:
    """What to compare and report: the registered domain, or the IP itself."""
    if dest.host is None:
        return None
    return dest.host if dest.is_ip else registered_domain(dest.host)


def _text_destination(text: str) -> Destination | None:
    """Where the visible text claims to go, if the text itself is a URL or domain."""
    text = text.strip()
    if not _LOOKS_LIKE_URL.fullmatch(text):
        return None
    return destination(text if "://" in text else "http://" + text)


_LOOKALIKE_IDS = {
    "lookalike": "link_lookalike",
    "brand_in_domain": "link_brand_in_domain",
    "mixed_script": "link_mixed_script",
}


def link_findings(href: str, text: str) -> list[Finding]:
    dest = destination(href)
    if dest is None:
        return []
    if dest.scheme in SCRIPT_SCHEMES:
        return [Finding("link_script", (dest.scheme,))]
    site = _site(dest)
    if site is None:
        return []

    findings = []
    claimed = _text_destination(text)
    claimed_site = _site(claimed) if claimed else None
    if claimed_site and claimed_site != site and site not in CLICK_TRACKERS:
        findings.append(Finding("link_text_mismatch", (claimed_site, site)))

    if dest.is_ip:
        findings.append(Finding("link_ip", (site,)))
    elif site in SHORTENERS:
        findings.append(Finding("link_shortener", (site,)))
    else:
        match = lookalike.assess(dest.host or "")
        if match:
            values = (match.brand, match.domain) if match.brand else (match.domain,)
            findings.append(Finding(_LOOKALIKE_IDS[match.kind], values))
    return findings


def check(request: AnalyzeRequest) -> list[Finding]:
    findings = []
    for href, text in extract_links(request):
        findings += link_findings(href, text)
    return findings
