import pytest

from app.models import AnalyzeRequest
from app.signals.links import MAX_LINKS, check, destination, extract_links, link_findings


def request(html: str | None = None, text: str = "") -> AnalyzeRequest:
    return AnalyzeRequest.model_validate(
        {"message_id": "m", "from": "a@example.com", "subject": "", "body_text": text,
         "body_html": html}
    )  # fmt: skip


def ids(findings: list) -> list[str]:
    return [f.id for f in findings]


# Normalization: where a browser would really go (T3)


@pytest.mark.parametrize(
    ("href", "host"),
    [
        ("https://paypal.com@evil.xyz/login", "evil.xyz"),  # user@host trick
        ("https:\\\\evil.xyz", "evil.xyz"),  # backslashes
        ("//evil.xyz/a", "evil.xyz"),  # scheme-relative
        ("www.Evil.XYZ", "www.evil.xyz"),
        ("http://%65vil.xyz", "evil.xyz"),  # percent-encoded host
        ("http://ev\nil.xyz", "evil.xyz"),  # newline inside the URL
        ("\x00 http://evil.xyz", "evil.xyz"),  # leading control character
        ("http://pаypal.com", "xn--pypal-4ve.com"),  # Cyrillic а
        ("HTTP://EVIL.XYZ.", "evil.xyz"),
    ],
)
def test_destination_host(href: str, host: str) -> None:
    dest = destination(href)
    assert dest is not None
    assert dest.host == host


@pytest.mark.parametrize(
    ("href", "ip"),
    [
        ("http://3232235777/", "192.168.1.1"),  # decimal
        ("http://0xC0A80001", "192.168.0.1"),  # hex
        ("http://0300.0250.0.1", "192.168.0.1"),  # octal
        ("http://192.168.1", "192.168.0.1"),  # short form
        ("http://1.2.3.4:8080/x", "1.2.3.4"),
        ("http://[::1]/", "::1"),
    ],
)
def test_ip_forms(href: str, ip: str) -> None:
    dest = destination(href)
    assert dest is not None
    assert (dest.host, dest.is_ip) == (ip, True)


@pytest.mark.parametrize("href", ["javascript:alert(1)", " java\tscript:x", "JaVaScRiPt:x",
                                  "data:text/html,x", "vbscript:x"])  # fmt: skip
def test_script_schemes(href: str) -> None:
    dest = destination(href)
    assert dest is not None
    assert dest.host is None
    assert dest.scheme in {"javascript", "data", "vbscript"}


@pytest.mark.parametrize(
    "href",
    ["mailto:a@b.com", "tel:123", "#top", "/relative", "", "http://[bad", "http://exa mple.com",
     "http://", "http://256.256.256.256.256"],
)  # fmt: skip
def test_ignored_or_invalid(href: str) -> None:
    assert destination(href) is None


# Findings per link


def test_text_vs_destination_mismatch() -> None:
    findings = link_findings("https://evil.xyz/login", "www.paypal.com")
    assert ids(findings) == ["link_text_mismatch"]
    assert findings[0].values == ("paypal.com", "evil.xyz")


def test_text_with_user_at_host_trick() -> None:
    assert ids(link_findings("https://evil.xyz", "https://paypal.com@evil.xyz")) == []
    assert ids(link_findings("https://paypal.com", "https://paypal.com@evil.xyz")) == [
        "link_text_mismatch"
    ]


@pytest.mark.parametrize(
    ("href", "text"),
    [
        ("https://www.paypal.com/signin", "paypal.com"),  # same registered domain
        ("https://evil.xyz", "Click here"),  # text is not an address
        ("https://evil.xyz", "Sign in to your account"),
        ("https://click.sendgrid.net/ls/x", "www.shop.com"),  # newsletter click tracking
    ],
)
def test_no_mismatch(href: str, text: str) -> None:
    assert "link_text_mismatch" not in ids(link_findings(href, text))


def test_script_link_is_high() -> None:
    assert link_findings("javascript:steal()", "Open")[0].values == ("javascript",)


def test_ip_link() -> None:
    findings = link_findings("http://3232235777/login", "Sign in")
    assert [(f.id, f.values) for f in findings] == [("link_ip", ("192.168.1.1",))]


def test_shortener() -> None:
    assert ids(link_findings("https://bit.ly/abc", "Track your parcel")) == ["link_shortener"]


def test_lookalike_destination() -> None:
    findings = link_findings("https://login.paypa1.com", "Sign in")
    assert [(f.id, f.values) for f in findings] == [("link_lookalike", ("paypal", "paypa1.com"))]


def test_brand_in_destination() -> None:
    assert ids(link_findings("https://paypal-support.com", "Help")) == ["link_brand_in_domain"]


def test_real_brand_link_is_clean() -> None:
    assert link_findings("https://www.paypal.com/signin", "Sign in") == []


def test_mismatch_and_lookalike_together() -> None:
    assert ids(link_findings("https://paypa1.com", "paypal.com")) == [
        "link_text_mismatch",
        "link_lookalike",
    ]


# Extraction


def test_extracts_html_anchors_and_text_urls() -> None:
    links = extract_links(
        request('<a href="https://a.com/x">A <b>site</b></a><a>no href</a>', "see https://b.com/y.")
    )
    assert links == [("https://a.com/x", "A site"), ("https://b.com/y", "https://b.com/y")]


def test_duplicate_links_counted_once() -> None:
    html = '<a href="https://bit.ly/a">x</a>' * 3
    assert len(extract_links(request(html))) == 1


def test_links_capped() -> None:
    html = "".join(f'<a href="https://s{i}.com">x</a>' for i in range(MAX_LINKS + 50))
    assert len(extract_links(request(html))) == MAX_LINKS


def test_malformed_html_does_not_crash() -> None:
    assert check(request('<a href="http://[bad">x</a><<<a href=' + "<p>" * 5000)) == []


def test_check_reports_each_link() -> None:
    html = '<a href="https://bit.ly/a">1</a><a href="https://tinyurl.com/b">2</a>'
    assert ids(check(request(html))) == ["link_shortener", "link_shortener"]
