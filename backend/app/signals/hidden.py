"""Text hidden from the reader with inline styles (T3).

Hidden text is a classic way to slip words past filters, or instructions past an
LLM. Here it is only reported, not interpreted; injection is Layer 3's concern.
Newsletters hide a short preview line on purpose, so only a substantial block of
hidden text counts, and a link inside hidden content counts more.

Inline styles only: stylesheets and media queries are not evaluated.
"""

import re

from bs4 import BeautifulSoup, Tag

from app.models import AnalyzeRequest
from app.signals.base import Finding

# Letters and digits only, so padding (zero-width characters, &nbsp;) never counts.
MIN_HIDDEN_CHARS = 200

_HIDING_RULES = (
    re.compile(r"(?:^|;)display:none"),
    re.compile(r"(?:^|;)visibility:hidden"),
    re.compile(r"(?:^|;)opacity:(?:0+(?:\.0*)?|\.0+)%?(?:;|$)"),
    re.compile(r"(?:^|;)font-size:(?:0+(?:\.0*)?|\.0+)(?:px|pt|em|rem|%)?(?:;|$)"),
    re.compile(r"(?:^|;)font-size:1px(?:;|$)"),
)
_ZERO_BOX = re.compile(r"(?:^|;)(?:max-)?height:0(?:px)?(?:;|$)")
_OVERFLOW_HIDDEN = re.compile(r"(?:^|;)overflow:hidden")


def is_hidden(style: str) -> bool:
    style = re.sub(r"\s+|!important", "", style.lower())
    if any(rule.search(style) for rule in _HIDING_RULES):
        return True
    return bool(_ZERO_BOX.search(style) and _OVERFLOW_HIDDEN.search(style))


def check(request: AnalyzeRequest) -> list[Finding]:
    if not request.body_html:
        return []
    soup = BeautifulSoup(request.body_html, "html.parser")

    hidden_chars = 0
    hidden_links = 0
    for element in soup.find_all(style=True):
        if not isinstance(element, Tag) or not is_hidden(str(element["style"])):
            continue
        if any(isinstance(p, Tag) and p.has_attr("style") and is_hidden(str(p["style"]))
               for p in element.parents):  # fmt: skip
            continue  # already counted with its hidden ancestor
        hidden_chars += sum(ch.isalnum() for ch in element.get_text())
        hidden_links += len(element.find_all("a", href=True))

    if hidden_links:
        return [Finding("hidden_link", (f"links={hidden_links}",))]
    if hidden_chars >= MIN_HIDDEN_CHARS:
        return [Finding("hidden_text", (f"chars={hidden_chars}",))]
    return []
