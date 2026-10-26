import pytest

from app.models import AnalyzeRequest
from app.signals.hidden import MIN_HIDDEN_CHARS, check, is_hidden

LONG = "word " * 60  # 240 letters


def request(html: str | None) -> AnalyzeRequest:
    return AnalyzeRequest.model_validate(
        {
            "message_id": "m",
            "from": "a@example.com",
            "subject": "",
            "body_text": "",
            "body_html": html,
        }
    )


@pytest.mark.parametrize(
    "style",
    [
        "display:none",
        "DISPLAY: NONE !important",
        "color:red; visibility:hidden",
        "opacity:0",
        "opacity:0.0",
        "opacity:.0",
        "font-size:0",
        "font-size:0px",
        "font-size:1px",
        "max-height:0; overflow:hidden",
        "height:0px;overflow:hidden",
    ],
)
def test_hiding_styles(style: str) -> None:
    assert is_hidden(style)


@pytest.mark.parametrize(
    "style",
    [
        "",
        "color:red",
        "display:block",
        "opacity:0.5",
        "opacity:",
        "font-size:12px",
        "font-size:.5em",
        "font-size:10px",
        "max-height:0",  # without overflow:hidden the content still shows
        "height:100px;overflow:hidden",
        "line-height:0",
    ],
)
def test_visible_styles(style: str) -> None:
    assert not is_hidden(style)


def test_large_hidden_block_is_low() -> None:
    [finding] = check(request(f'<p>Hi</p><div style="display:none">{LONG}</div>'))
    assert finding.id == "hidden_text"
    assert finding.values == ("chars=240",)


def test_newsletter_preheader_is_ignored() -> None:
    # Short preview text padded with invisible characters, as newsletters send it.
    padding = "&zwnj;&nbsp;" * 150
    style = "display:none;max-height:0;overflow:hidden"
    html = f'<div style="{style}">Our autumn sale is here{padding}</div>'
    assert check(request(html)) == []


def test_hidden_link_is_medium() -> None:
    html = '<span style="font-size:0"><a href="https://evil.xyz">x</a></span>'
    [finding] = check(request(html))
    assert (finding.id, finding.values) == ("hidden_link", ("links=1",))


def test_nested_hidden_elements_counted_once() -> None:
    text = "a" * (MIN_HIDDEN_CHARS // 2 + 1)
    html = f'<div style="display:none">{text}<span style="opacity:0">x</span></div>'
    assert check(request(html)) == []


def test_visible_email_and_no_html() -> None:
    assert check(request(f"<p>{LONG}</p>")) == []
    assert check(request(None)) == []
