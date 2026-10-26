"""Domains that imitate a well-known brand (US-03).

Two strengths:
* `lookalike` (high): the domain is the brand's name with a trick applied: a
  swapped character (`paypa1`), a letter from another alphabet (Cyrillic `а`), or a
  one-letter typo (`paypall`, `linkedln`).
* `brand_in_domain` (medium): the brand's exact name on a domain it doesn't own
  (`paypal.xyz`, also real regional sites like `amazon.ca`, hence medium), or used as
  a word inside someone else's domain (`paypal-support.com`, `paypal.com.evil.xyz`).
A punycode domain that mixes alphabets without matching a brand is `mixed_script`.
"""

import unicodedata
from dataclasses import dataclass
from typing import Literal

import idna

from app.models import AnalyzeRequest
from app.signals.base import Finding
from app.signals.brands import BRANDS, owner_of, skeleton
from app.signals.domains import parse_address, split_host

Kind = Literal["lookalike", "brand_in_domain", "mixed_script"]

# Letters from other alphabets that look Latin. Not the full Unicode confusables
# table: the common ones used in brand spoofing.
_CONFUSABLES = str.maketrans(
    {
        "а": "a", "в": "b", "с": "c", "ԁ": "d", "е": "e", "һ": "h", "і": "i", "ј": "j",
        "к": "k", "ӏ": "l", "м": "m", "п": "n", "о": "o", "р": "p", "ԛ": "q", "ѕ": "s",
        "т": "t", "у": "y", "х": "x", "ԝ": "w", "ɡ": "g", "ο": "o", "α": "a", "ε": "e",
        "ι": "i", "κ": "k", "ν": "v", "ρ": "p", "τ": "t", "υ": "u", "χ": "x",
    }
)  # fmt: skip

BRAND_WORDS = {
    word.replace(" ", ""): brand_id for brand_id, brand in BRANDS.items() for word in brand.words
}


@dataclass(frozen=True)
class Match:
    kind: Kind
    brand: str | None
    domain: str


def assess(host: str) -> Match | None:
    """How a hostname imitates a brand, if it does. None for ordinary or brand-owned domains."""
    parts = split_host(host)
    if parts is None:
        return None
    subdomain, label, suffix = parts
    domain = f"{label}.{suffix}"
    if owner_of(domain):
        return None

    unicode_label = _decode(label)
    folded = _fold(unicode_label)
    tricked = folded != unicode_label  # another alphabet or accents were involved

    best: Match | None = None
    for candidate in [folded, *folded.split("-")] if "-" in folded else [folded]:
        for word, brand_id in BRAND_WORDS.items():
            kind = _compare(candidate, word, tricked)
            if kind == "lookalike":
                return Match("lookalike", brand_id, domain)
            if kind and best is None:
                best = Match(kind, brand_id, domain)

    for token in subdomain.replace("-", ".").split("."):
        brand_id = BRAND_WORDS.get(skeleton(token))
        if brand_id and best is None:
            best = Match("brand_in_domain", brand_id, domain)

    if best is None and unicode_label != label and _mixes_alphabets(unicode_label):
        best = Match("mixed_script", None, domain)
    return best


def _compare(candidate: str, word: str, tricked: bool) -> Kind | None:
    shape = skeleton(candidate)
    if shape == word:
        if tricked or candidate != word:
            return "lookalike"  # paypa1, pаypal, secure-paypa1
        return "brand_in_domain"  # paypal.xyz, paypal-help
    if shape.replace("i", "l") == word.replace("i", "l"):
        return "lookalike"  # netfllx, upwlnd: i and l look alike
    if _is_typo(shape, word):
        return "lookalike"  # paypall, micorsoft, linkedln
    return None


def _is_typo(shape: str, word: str) -> bool:
    """One slip of the keyboard away from a brand name.

    Names of 8+ letters allow any single edit (two from 9); shorter names only an
    added, missing, or swapped-order letter, since one substituted letter turns
    `google` into the real word `googly`.
    """
    if len(word) >= 8:
        return _edit_distance(shape, word) <= (2 if len(word) >= 9 else 1)
    if len(word) >= 6:
        if abs(len(shape) - len(word)) == 1:
            return _edit_distance(shape, word) == 1
        return len(shape) == len(word) and _is_transposition(shape, word)
    return False


def _is_transposition(a: str, b: str) -> bool:
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    return (
        len(diff) == 2
        and diff[1] == diff[0] + 1
        and a[diff[0]] == b[diff[1]]
        and a[diff[1]] == b[diff[0]]
    )


def _decode(label: str) -> str:
    if not label.startswith("xn--"):
        return label
    try:
        return idna.decode(label)
    except idna.IDNAError:
        return label


def _fold(label: str) -> str:
    """Maps lookalike letters to Latin and strips accents (`pàypal` → `paypal`)."""
    mapped = label.translate(_CONFUSABLES)
    stripped = unicodedata.normalize("NFKD", mapped)
    return "".join(ch for ch in stripped if not unicodedata.combining(ch))


def _mixes_alphabets(label: str) -> bool:
    scripts = {unicodedata.name(ch, "").split(" ")[0] for ch in label if ch.isalpha()}
    return len(scripts) > 1


def _edit_distance(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


# The sender's own addresses. Link destinations use `assess` from links.py.

_SENDER_IDS: dict[Kind, str] = {
    "lookalike": "sender_lookalike",
    "brand_in_domain": "sender_brand_in_domain",
    "mixed_script": "sender_mixed_script",
}


def check(request: AnalyzeRequest) -> list[Finding]:
    findings = []
    for value in (request.sender, request.reply_to):
        _, host = parse_address(value)
        match = assess(host) if host else None
        if match:
            values = (match.brand, match.domain) if match.brand else (match.domain,)
            findings.append(Finding(_SENDER_IDS[match.kind], values))
    return findings
