"""Where do the links really go? (US-03)

Every link is normalized the way a browser would read it before any check (T3):
whitespace and backslashes, `user@host` (`https://paypal.com@evil.xyz` goes to
evil.xyz), percent-encoding, punycode, numeric IPv4 forms (`http://3232235777`), and
redirect wrappers (`google.com/url?q=`, Outlook SafeLinks) unwrapped to their target.
URLs are never fetched or resolved: no network call on attacker-supplied input.
"""

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlsplit

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

# Redirectors whose target sits in the link itself (Gmail and Outlook rewrite links
# this way, and attackers borrow the trick). Unwrapped before any check.
GOOGLE_REDIRECT_HOSTS = {"google.com", "www.google.com"}
SAFELINKS_SUFFIX = ".safelinks.protection.outlook.com"
MAX_UNWRAP = 5
MAX_EMBEDDED = 10
_EMBEDDED_URL = re.compile(r"(?:https?:[/\\]|www\.)", re.IGNORECASE)

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


def _clean(href: str) -> str:
    # Browsers trim control characters and spaces at the ends, drop tabs and newlines
    # anywhere, and treat \\ as / (WHATWG URL parsing).
    url = _TAB_OR_NEWLINE.sub("", href.strip(_C0_OR_SPACE)).replace("\\", "/")
    if url.lower().startswith("www."):
        return "http://" + url
    if url.startswith("//"):
        return "https:" + url
    return url


def destination(href: str) -> Destination | None:
    """Where a browser would go for this href. None for relative, mailto, tel, or junk."""
    url = _clean(href)
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
    if _ends_in_number(host):
        return None  # browsers must read it as IPv4; not a valid one, so not a URL
    normalized = normalize_host(host)
    return Destination(scheme, normalized) if normalized else None


def _ip(host: str) -> str | None:
    if ":" in host:
        try:
            return str(ipaddress.IPv6Address(host))
        except ValueError:
            return None
    return _ipv4(host)


def _ends_in_number(host: str) -> bool:
    last = host.rsplit(".", 1)[-1]
    return last.isascii() and (last.isdigit() or last.lower().startswith("0x"))


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


def unwrap(href: str) -> str:
    """The real target of a link wrapped by a known redirector, read from the link itself.

    Attackers hide a phishing link behind `google.com/url?q=` so it seems to go to
    google.com; the checks must see the target inside. Parsed only, never followed.
    """
    for _ in range(MAX_UNWRAP):
        inner = _wrapped_target(href)
        if not inner:
            break
        href = inner
    return href


def _wrapped_target(href: str) -> str | None:
    dest = destination(href)
    if dest is None or dest.host is None or dest.is_ip:
        return None
    try:
        parts = urlsplit(_clean(href))
    except ValueError:
        return None
    if dest.host in GOOGLE_REDIRECT_HOSTS and parts.path == "/url":
        keys = ("q", "url")
    elif dest.host.endswith(SAFELINKS_SUFFIX):
        keys = ("url",)
    else:
        return None
    params = parse_qs(parts.query)
    for key in keys:
        if params.get(key):
            return params[key][0]
    return None


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


def embedded_urls(href: str) -> list[str]:
    """Web addresses carried inside a link's query (`?to=https://...`), on any site.

    Any site with an open redirect can forward to them, so they get the destination
    checks too. They are not trusted as the destination: an attacker could add
    `?x=https://paypal.com` to their own link as a decoy.
    """
    found: list[str] = []
    pending = [href]
    while pending and len(found) < MAX_EMBEDDED:
        try:
            query = urlsplit(_clean(pending.pop())).query
        except ValueError:
            continue
        for values in parse_qs(query).values():
            for value in values:
                if _EMBEDDED_URL.match(value.strip()) and value not in found:
                    found.append(value)
                    pending.append(value)
    return found[:MAX_EMBEDDED]


def link_findings(href: str, text: str) -> list[Finding]:
    href, text = unwrap(href), unwrap(text.strip())
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

    findings += _destination_findings(dest, site)
    for inner in embedded_urls(href):
        inner_dest = destination(inner)
        inner_site = _site(inner_dest) if inner_dest else None
        if inner_dest and inner_site:
            findings += _destination_findings(inner_dest, inner_site)
    return list(dict.fromkeys(findings))  # one finding per link, even if repeated inside


def _destination_findings(dest: Destination, site: str) -> list[Finding]:
    findings = []
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
