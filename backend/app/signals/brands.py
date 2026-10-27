"""Well-known brands that phishing imitates, and the domains they really send from.

Kept short on purpose (ADR-013): a brand is only listed with the domains its mail
actually comes from, so a match outside them is a meaningful signal.
"""

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Brand:
    words: tuple[str, ...]
    # Domains the brand's own mail comes from.
    sends_from: tuple[str, ...]
    # Real domains it owns where anyone can have an address (gmail.com): never
    # proof that a sender is the brand, and never a lookalike of it either.
    also_owns: tuple[str, ...] = ()
    # Hebrew names, matched in display names only, as whole phrases: a bare "לאומי"
    # also means "national" (ביטוח לאומי), so the bank is "בנק לאומי".
    hebrew: tuple[str, ...] = ()


BRANDS: dict[str, Brand] = {
    "paypal": Brand(("paypal",), ("paypal.com",), hebrew=("פייפאל", "פייפל")),
    "microsoft": Brand(
        ("microsoft", "outlook", "office 365", "office365", "onedrive", "sharepoint"),
        ("microsoft.com", "microsoftonline.com", "office.com"),
        ("outlook.com", "live.com", "hotmail.com"),
        hebrew=("מיקרוסופט",),
    ),
    "google": Brand(
        ("google", "gmail"), ("google.com", "youtube.com"), ("gmail.com",), hebrew=("גוגל",)
    ),
    "apple": Brand(("apple", "icloud", "itunes"), ("apple.com",), ("icloud.com", "me.com")),
    "amazon": Brand(
        ("amazon",), ("amazon.com", "amazon.co.uk", "amazon.de", "amazon.fr"), hebrew=("אמזון",)
    ),
    "netflix": Brand(("netflix",), ("netflix.com",), hebrew=("נטפליקס",)),
    "dhl": Brand(("dhl",), ("dhl.com", "dhl.de")),
    "fedex": Brand(("fedex",), ("fedex.com",)),
    "linkedin": Brand(("linkedin",), ("linkedin.com",)),
    "docusign": Brand(("docusign",), ("docusign.com", "docusign.net")),
    "dropbox": Brand(("dropbox",), ("dropbox.com", "dropboxmail.com")),
    "meta": Brand(
        ("facebook", "instagram", "whatsapp"),
        ("facebook.com", "facebookmail.com", "meta.com", "instagram.com", "whatsapp.com"),
    ),
    "leumi": Brand(("leumi",), ("leumi.co.il",), hebrew=("בנק לאומי",)),
    "hapoalim": Brand(("hapoalim",), ("bankhapoalim.co.il",), hebrew=("בנק הפועלים",)),
    "upwind": Brand(("upwind",), ("upwind.io",)),
}

# Characters that pass for others at a glance. Uppercase I is mapped before lowercasing.
_SWAPS = (("I", "l"), ("0", "o"), ("1", "l"), ("rn", "m"), ("vv", "w"))
_MIN_COMPACT_LEN = 6


def _hebrew_text(text: str) -> str:
    """Display name with vowel marks and format characters removed, spaces collapsed."""
    text = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", text))
    text = "".join(ch for ch in text if unicodedata.category(ch) not in ("Cf", "Mn"))
    return re.sub(r"\s+", " ", text)


def skeleton(text: str) -> str:
    """`PayPaI`, `paypa1`, `rnicrosoft` → `paypal`, `paypal`, `microsoft`."""
    for look, real in _SWAPS:
        text = text.replace(look, real) if look == "I" else text.lower().replace(look, real)
    return text.lower()


def brands_named_in(text: str) -> list[str]:
    """Brands a display name refers to, whole words only (`pineapple` is not Apple).

    Long brand words also match with separators removed, so `P-a-y-P-a-l` still counts.
    """
    shape = skeleton(text)
    words = " ".join(re.findall(r"[a-z0-9]+", shape))
    compact = words.replace(" ", "")
    hebrew = _hebrew_text(text)
    found = []
    for brand_id, brand in BRANDS.items():
        if any(name in hebrew for name in brand.hebrew):
            found.append(brand_id)
            continue
        for name in brand.words:
            whole_word = re.search(rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])", words)
            spaced_out = len(name) >= _MIN_COMPACT_LEN and name.replace(" ", "") in compact
            if whole_word or spaced_out:
                found.append(brand_id)
                break
    return found


def is_official(brand_id: str, domain: str | None) -> bool:
    """True only for domains the brand's own mail comes from."""
    return domain is not None and domain in BRANDS[brand_id].sends_from


def owner_of(domain: str) -> str | None:
    """The brand that really owns this registered domain, if any."""
    for brand_id, brand in BRANDS.items():
        if domain in brand.sends_from or domain in brand.also_owns:
            return brand_id
    return None
