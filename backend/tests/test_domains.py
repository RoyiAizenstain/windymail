import pytest

from app.signals.domains import normalize_host, parse_address, registered_domain


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("login.paypal.com", "paypal.com"),
        ("A.B.PayPal.co.uk.", "paypal.co.uk"),
        ("pаypal.com", "xn--pypal-4ve.com"),  # Cyrillic а
        ("192.168.0.1", None),
        ("localhost", None),
        ("", None),
    ],
)
def test_registered_domain(host: str, expected: str | None) -> None:
    assert registered_domain(host) == expected


def test_normalize_rejects_invalid_and_overlong() -> None:
    assert normalize_host("bad host.com") is None
    assert normalize_host("a" * 254) is None


@pytest.mark.parametrize(
    ("value", "name", "host"),
    [
        ("PayPal Security <alert@Secure-PayPal.xyz>", "PayPal Security", "secure-paypal.xyz"),
        ("alice@example.com", "", "example.com"),
        ('"Bob, IT" <bob@corp.example>', "Bob, IT", "corp.example"),
        ("not an address", "", None),
        (None, "", None),
        ("support@paypal.com <x@evil.xyz>", "support@paypal.com", "evil.xyz"),
        # Two bracketed parts: the last one is the real address, the rest is the name.
        ('"PayPal" <a@b.com> <x@evil.xyz>', 'PayPal" <a@b.com>', "evil.xyz"),
    ],
)
def test_parse_address(value: str | None, name: str, host: str | None) -> None:
    assert parse_address(value) == (name, host)
