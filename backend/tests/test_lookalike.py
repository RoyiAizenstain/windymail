import pytest

from app.models import AnalyzeRequest
from app.signals.lookalike import assess, check


@pytest.mark.parametrize(
    ("host", "brand"),
    [
        ("paypa1.com", "paypal"),  # digit for letter
        ("rnicrosoft.com", "microsoft"),  # rn for m
        ("g00gle.com", "google"),
        ("netfllx.com", "netflix"),  # l for i
        ("upwlnd.io", "upwind"),
        ("xn--pypal-4ve.com", "paypal"),  # Cyrillic а
        ("pаypal.com", "paypal"),  # same, before IDNA encoding
        ("xn--80ak6aa92e.com", "apple"),  # all-Cyrillic аррӏе
        ("pàypal.com", "paypal"),  # accent
        ("paypall.com", "paypal"),  # added letter
        ("paypl.com", "paypal"),  # missing letter
        ("papyal.com", "paypal"),  # swapped letters
        ("micorsoft.com", "microsoft"),
        ("linkedln.com", "linkedin"),
        ("secure-paypa1.xyz", "paypal"),  # trick inside a hyphenated name
        ("login.paypa1.com", "paypal"),
    ],
)
def test_lookalikes_are_high(host: str, brand: str) -> None:
    match = assess(host)
    assert match is not None
    assert (match.kind, match.brand) == ("lookalike", brand)


@pytest.mark.parametrize(
    ("host", "brand"),
    [
        ("paypal.xyz", "paypal"),  # exact name, domain the brand doesn't own
        ("amazon.ca", "amazon"),  # real regional site: why this is medium, not high
        ("paypal-support.com", "paypal"),
        ("office365-login.net", "microsoft"),
        ("paypal.com.secure-login.xyz", "paypal"),  # brand in someone else's subdomain
    ],
)
def test_brand_in_domain_is_medium(host: str, brand: str) -> None:
    match = assess(host)
    assert match is not None
    assert (match.kind, match.brand) == ("brand_in_domain", brand)


@pytest.mark.parametrize(
    "host",
    [
        "paypal.com",
        "mail.paypal.com",
        "gmail.com",  # owned by Google, never its lookalike
        "outlook.com",
        "bankhapoalim.co.il",
        "example.com",
        "googly.com",  # one substituted letter in a short name is a real word
        "goggle.com",
        "corn.com",
        "192.168.0.1",
        "not a host",
    ],
)
def test_ordinary_and_owned_domains_pass(host: str) -> None:
    assert assess(host) is None


def test_mixed_alphabets_without_brand() -> None:
    match = assess("exаmple.com")  # Cyrillic а in an unbranded name
    assert match is not None
    assert (match.kind, match.brand) == ("mixed_script", None)


def test_single_alphabet_idn_is_not_flagged() -> None:
    assert assess("דוגמה.com") is None


def request(sender: str, reply_to: str | None = None) -> AnalyzeRequest:
    return AnalyzeRequest.model_validate(
        {"message_id": "m", "from": sender, "reply_to": reply_to, "subject": "", "body_text": ""}
    )


def test_check_covers_from_and_reply_to() -> None:
    findings = check(request("Alice <a@example.com>", "billing@paypal-support.com"))
    assert [(f.id, f.values) for f in findings] == [
        ("sender_brand_in_domain", ("paypal", "paypal-support.com"))
    ]
    findings = check(request("PayPal <service@paypa1.com>"))
    assert [(f.id, f.values) for f in findings] == [("sender_lookalike", ("paypal", "paypa1.com"))]


def test_check_reports_punycode_form() -> None:
    [finding] = check(request("x@pаypal.com"))
    assert finding.values == ("paypal", "xn--pypal-4ve.com")


def test_check_ignores_real_brand_mail() -> None:
    assert check(request("PayPal <service@paypal.com>")) == []
