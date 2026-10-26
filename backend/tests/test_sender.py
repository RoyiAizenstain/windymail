import pytest

from app.models import AnalyzeRequest
from app.signals.sender import auth_findings, check, parse_auth_results

GMAIL_ALL_OK = (
    "mx.google.com; dkim=pass header.i=@example.com header.s=s1 header.b=abc; "
    "spf=pass (google.com: domain of a@example.com designates 1.2.3.4 as permitted sender) "
    "smtp.mailfrom=a@example.com; dmarc=pass (p=REJECT sp=REJECT dis=NONE) header.from=example.com"
)


def ids(findings: list) -> list[str]:
    return [f.id for f in findings]


def request(**overrides: object) -> AnalyzeRequest:
    fields = {
        "message_id": "m",
        "from": "Alice <alice@example.com>",
        "subject": "s",
        "body_text": "",
        "auth_results": GMAIL_ALL_OK,
    }
    return AnalyzeRequest.model_validate({**fields, **overrides})


# Authentication-Results


def test_parses_gmail_header_with_comments() -> None:
    assert parse_auth_results(GMAIL_ALL_OK) == {
        "dkim": ["pass"],
        "spf": ["pass"],
        "dmarc": ["pass"],
    }


def test_all_pass_has_no_findings() -> None:
    assert auth_findings(GMAIL_ALL_OK) == []


@pytest.mark.parametrize("header", [None, "", "mx.google.com", "mx.google.com; none"])
def test_missing_results_are_low_unknown(header: str | None) -> None:
    assert ids(auth_findings(header)) == ["auth_unknown"]


def test_forged_header_from_another_server_is_ignored() -> None:
    forged = "mail.attacker.xyz; spf=pass; dkim=pass; dmarc=pass"
    assert ids(auth_findings(forged)) == ["auth_unknown"]


def test_lookalike_authserv_id_is_ignored() -> None:
    assert ids(auth_findings("mx.google.com.evil.xyz; dmarc=pass")) == ["auth_unknown"]


def test_authserv_id_with_version_is_accepted() -> None:
    assert auth_findings("mx.google.com 1; spf=pass; dkim=pass; dmarc=pass") == []


def test_dmarc_fail_is_reported_alone() -> None:
    findings = auth_findings("mx.google.com; spf=fail; dkim=fail; dmarc=fail (p=NONE)")
    assert ids(findings) == ["dmarc_fail"]
    assert findings[0].values == ("dmarc=fail",)


@pytest.mark.parametrize("result", ["fail", "softfail", "SoftFail"])
def test_spf_failure(result: str) -> None:
    findings = auth_findings(f"mx.google.com; spf={result}; dkim=pass; dmarc=pass")
    assert ids(findings) == ["spf_fail"]
    assert findings[0].values == (f"spf={result.lower()}",)


@pytest.mark.parametrize("result", ["neutral", "none", "temperror"])
def test_inconclusive_spf_is_not_a_failure(result: str) -> None:
    assert auth_findings(f"mx.google.com; spf={result}; dkim=pass; dmarc=pass") == []


def test_dkim_fail_without_any_pass() -> None:
    assert ids(auth_findings("mx.google.com; dkim=fail; spf=pass; dmarc=pass")) == ["dkim_fail"]


def test_one_valid_dkim_signature_is_enough() -> None:
    assert auth_findings("mx.google.com; dkim=fail; dkim=pass; spf=pass; dmarc=pass") == []


def test_semicolon_inside_comment_does_not_split() -> None:
    header = "mx.google.com; spf=pass (note; dmarc=fail) smtp.mailfrom=x; dmarc=pass"
    assert auth_findings(header) == []


# Display name


def test_ordinary_sender_has_no_findings() -> None:
    assert check(request()) == []


@pytest.mark.parametrize(
    "sender",
    ["support@paypal.com <x@evil.xyz>", '"paypal.com" <x@evil.xyz>'],
)
def test_display_name_showing_another_domain(sender: str) -> None:
    findings = check(request(**{"from": sender}))
    assert "display_name_mismatch" in ids(findings)
    mismatch = next(f for f in findings if f.id == "display_name_mismatch")
    assert mismatch.values == ("paypal.com", "evil.xyz")


def test_display_name_with_own_domain_is_fine() -> None:
    assert check(request(**{"from": "alice@example.com <alice@example.com>"})) == []


def test_display_name_brand_from_other_domain() -> None:
    findings = check(request(**{"from": "PayPal Security <alert@secure-login.xyz>"}))
    assert ids(findings) == ["display_name_brand"]
    assert findings[0].values == ("paypal", "secure-login.xyz")


def test_display_name_brand_from_official_subdomain_is_fine() -> None:
    assert check(request(**{"from": "PayPal <service@mail.paypal.com>"})) == []


def test_brand_from_free_mail_is_flagged() -> None:
    assert ids(check(request(**{"from": "Google Support <help.google@gmail.com>"}))) == [
        "display_name_brand"
    ]


# Reply-To


def test_reply_to_other_domain() -> None:
    findings = check(request(reply_to="Billing <pay@other.net>"))
    assert ids(findings) == ["reply_to_mismatch"]
    assert findings[0].values == ("example.com", "other.net")


def test_reply_to_same_registered_domain_is_fine() -> None:
    assert check(request(reply_to="team@support.example.com")) == []


def test_unparseable_sender_skips_name_checks() -> None:
    assert check(request(**{"from": "PayPal", "reply_to": "x@other.net"})) == []
