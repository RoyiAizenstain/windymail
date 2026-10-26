"""Is the sender who they claim to be? (US-03)

Authentication results are trusted only from Gmail's own `mx.google.com` entry. A
sender can add an `Authentication-Results` header of their own claiming `pass`;
under RFC 8601 the receiving server removes copies carrying its own ID, so any
other ID is ignored.
"""

import re

from app.models import AnalyzeRequest
from app.signals.base import Finding
from app.signals.brands import brands_named_in, is_official
from app.signals.domains import parse_address, registered_domain

TRUSTED_AUTHSERV_ID = "mx.google.com"

_COMMENT = re.compile(r"\([^()]*\)")
_RESULT = re.compile(r"^\s*(spf|dkim|dmarc)\s*=\s*([a-z]+)", re.IGNORECASE)
_DMARC_FAIL_COMMENT = re.compile(r"^\s*dmarc\s*=\s*fail\s*\(([^()]*)\)", re.IGNORECASE)
_POLICY = re.compile(r"\b(p|sp)=([a-z]+)")
_ADDRESS_OR_DOMAIN = re.compile(r"(?:[\w.+-]+@)?((?:[a-z0-9-]+\.)+[a-z]{2,})", re.IGNORECASE)

SPF_FAILURES = {"fail", "softfail"}


def check(request: AnalyzeRequest) -> list[Finding]:
    findings = auth_findings(request.auth_results)

    name, host = parse_address(request.sender)
    sender_domain = registered_domain(host) if host else None
    if sender_domain:
        findings += display_name_findings(name, sender_domain)
        findings += reply_to_findings(request.reply_to, sender_domain)
    return findings


def parse_auth_results(header: str | None) -> dict[str, list[str]] | None:
    """Method → results from the trusted entry, or None if there is no trusted entry."""
    if not header:
        return None
    text = header
    while _COMMENT.search(text):  # comments may nest; strip innermost first
        text = _COMMENT.sub("", text)
    authserv, *entries = text.split(";")
    if authserv.strip().split(" ")[0].lower() != TRUSTED_AUTHSERV_ID:
        return None
    results: dict[str, list[str]] = {}
    for entry in entries:
        match = _RESULT.match(entry)
        if match:
            results.setdefault(match.group(1).lower(), []).append(match.group(2).lower())
    return results or None


def dmarc_unenforced(header: str | None) -> bool:
    """True when the domain asks receivers not to act on DMARC failures (`p=none`).

    Many real newsletters fail DMARC this way: their mailing service isn't set up for
    the domain, and Gmail still delivers them normally. The policy is read only from
    the comment Gmail writes right after `dmarc=fail`; other comments hold text the
    sender controls (addresses), where a planted `p=none` must not lower the warning.
    Both `p` and `sp` (subdomains) must be `none`; anything missing or unclear counts
    as enforced.
    """
    if not header or parse_auth_results(header) is None:
        return False
    for entry in _top_level_entries(header)[1:]:
        match = _DMARC_FAIL_COMMENT.match(entry)
        if match:
            policies = dict(_POLICY.findall(match.group(1).lower()))
            return policies.get("p") == "none" and policies.get("sp", "none") == "none"
    return False


def _top_level_entries(header: str) -> list[str]:
    """`;`-separated entries with comments kept; a `;` inside a comment doesn't split."""
    entries, depth, start = [], 0, 0
    for index, char in enumerate(header):
        if char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
        elif char == ";" and depth == 0:
            entries.append(header[start:index])
            start = index + 1
    entries.append(header[start:])
    return entries


def auth_findings(header: str | None) -> list[Finding]:
    results = parse_auth_results(header)
    if results is None:
        return [Finding("auth_unknown")]

    dmarc, spf, dkim = results.get("dmarc", []), results.get("spf", []), results.get("dkim", [])
    if "fail" in dmarc:
        # DMARC already covers SPF and DKIM alignment; reporting them too would stack.
        if dmarc_unenforced(header):
            return [Finding("dmarc_fail_unenforced", ("dmarc=fail", "p=none"))]
        return [Finding("dmarc_fail", ("dmarc=fail",))]
    findings = []
    if spf and spf[0] in SPF_FAILURES:
        findings.append(Finding("spf_fail", (f"spf={spf[0]}",)))
    # A message can carry several DKIM signatures; one valid signature is enough.
    if "fail" in dkim and "pass" not in dkim:
        findings.append(Finding("dkim_fail", ("dkim=fail",)))
    return findings


def display_name_findings(name: str, sender_domain: str) -> list[Finding]:
    findings = []
    for match in _ADDRESS_OR_DOMAIN.finditer(name):
        claimed = registered_domain(match.group(1))
        if claimed and claimed != sender_domain:
            findings.append(Finding("display_name_mismatch", (claimed, sender_domain)))
            break
    for brand in brands_named_in(name):
        if not is_official(brand, sender_domain):
            findings.append(Finding("display_name_brand", (brand, sender_domain)))
    return findings


def reply_to_findings(reply_to: str | None, sender_domain: str) -> list[Finding]:
    _, host = parse_address(reply_to)
    reply_domain = registered_domain(host) if host else None
    if reply_domain and reply_domain != sender_domain:
        return [Finding("reply_to_mismatch", (sender_domain, reply_domain))]
    return []
