"""Well-known brands that phishing imitates, and the domains they really send from.

Kept short on purpose (ADR-013): a brand is only listed with the domains its mail
actually comes from, so a match outside them is a meaningful signal.
"""

import re

# Brand ID → (words that name it, official registered domains).
BRANDS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "paypal": (("paypal",), ("paypal.com",)),
    "microsoft": (
        ("microsoft", "outlook", "office 365", "office365", "onedrive", "sharepoint"),
        ("microsoft.com", "microsoftonline.com", "office.com", "outlook.com", "live.com"),
    ),
    "google": (("google", "gmail"), ("google.com", "youtube.com")),
    "apple": (("apple", "icloud", "itunes"), ("apple.com",)),
    "amazon": (("amazon",), ("amazon.com", "amazon.co.uk", "amazon.de", "amazon.fr")),
    "netflix": (("netflix",), ("netflix.com",)),
    "dhl": (("dhl",), ("dhl.com", "dhl.de")),
    "fedex": (("fedex",), ("fedex.com",)),
    "linkedin": (("linkedin",), ("linkedin.com",)),
    "docusign": (("docusign",), ("docusign.com", "docusign.net")),
    "dropbox": (("dropbox",), ("dropbox.com", "dropboxmail.com")),
    "meta": (
        ("facebook", "instagram", "whatsapp"),
        ("facebook.com", "facebookmail.com", "meta.com", "instagram.com", "whatsapp.com"),
    ),
    "leumi": (("leumi",), ("leumi.co.il",)),
    "hapoalim": (("hapoalim",), ("bankhapoalim.co.il",)),
    "upwind": (("upwind",), ("upwind.io",)),
}

# Characters that pass for others at a glance. Uppercase I is mapped before lowercasing.
_SWAPS = (("I", "l"), ("0", "o"), ("1", "l"), ("rn", "m"), ("vv", "w"))
_MIN_COMPACT_LEN = 6


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
    found = []
    for brand, (names, _) in BRANDS.items():
        for name in names:
            whole_word = re.search(rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])", words)
            spaced_out = len(name) >= _MIN_COMPACT_LEN and name.replace(" ", "") in compact
            if whole_word or spaced_out:
                found.append(brand)
                break
    return found


def is_official(brand: str, domain: str | None) -> bool:
    return domain is not None and domain in BRANDS[brand][1]
