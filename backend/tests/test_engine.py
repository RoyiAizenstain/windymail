import logging

import pytest

from app.models import AnalyzeRequest, Reason
from app.scoring import provisional_score
from app.signals.base import Finding
from app.signals.engine import run_checks, summarize, to_reasons
from app.signals.messages import CATALOG, Message


def make_request(**overrides: object) -> AnalyzeRequest:
    fields = {"message_id": "m", "from": "a@example.com", "subject": "s", "body_text": "hi"}
    return AnalyzeRequest.model_validate({**fields, **overrides})


def test_clean_request_has_no_reasons() -> None:
    assert run_checks(make_request()) == []


def test_truncated_body_is_a_finding() -> None:
    [reason] = run_checks(make_request(truncated=True))
    assert reason.id == "body_truncated"
    assert reason.severity == "low"


def test_failing_check_degrades_instead_of_crashing(caplog: pytest.LogCaptureFixture) -> None:
    def broken(request: AnalyzeRequest) -> list[Finding]:
        raise ValueError("SECRET-BODY-CONTENT")

    with caplog.at_level(logging.ERROR):
        [reason] = run_checks(make_request(), [("broken", broken)])
    assert reason.id == "check_failed"
    assert reason.details == "Checks that failed: broken"
    assert "SECRET-BODY-CONTENT" not in caplog.text
    assert "ValueError" in caplog.text


def test_one_failing_check_keeps_the_others() -> None:
    def broken(request: AnalyzeRequest) -> list[Finding]:
        raise RuntimeError

    def working(request: AnalyzeRequest) -> list[Finding]:
        return [Finding("body_truncated")]

    ids = {r.id for r in run_checks(make_request(), [("broken", broken), ("ok", working)])}
    assert ids == {"check_failed", "body_truncated"}


def test_repeated_findings_become_one_reason_with_count() -> None:
    [reason] = to_reasons([Finding("check_failed", ("a",)), Finding("check_failed", ("b",))])
    assert reason.text == "2 of the checks couldn't run on this email."
    assert reason.details == "Checks that failed: a, b"


@pytest.mark.parametrize(
    "value",
    ["<script>", "Evil.COM", "has space", "https://x.com/path", "a" * 254, "", "‮exe"],
)
def test_unsafe_values_are_never_echoed(value: str) -> None:
    [reason] = to_reasons([Finding("check_failed", (value,))])
    assert reason.details == "Checks that failed"


def test_values_are_deduplicated_and_capped() -> None:
    findings = [Finding("check_failed", (f"v{i}", "v0")) for i in range(20)]
    [reason] = to_reasons(findings)
    assert reason.details.count("v0") == 1
    assert len(reason.details.split(": ")[1].split(", ")) == 10


def reason(severity: str) -> Reason:
    return Reason(id="x", category="content", severity=severity, text="t", details="d")


def test_reasons_sorted_most_severe_first(monkeypatch: pytest.MonkeyPatch) -> None:
    high = Message(category="link", severity="high", text="h", text_many="h", details="d")
    monkeypatch.setitem(CATALOG, "test_high", high)
    reasons = to_reasons([Finding("check_failed"), Finding("test_high")])
    assert [r.severity for r in reasons] == ["high", "low"]


@pytest.mark.parametrize(
    ("severities", "score"),
    [
        ([], 0),
        (["low"], 5),
        (["medium"], 15),
        (["high"], 35),
        (["high", "high"], 70),
        (["high", "medium", "low"], 55),
        (["high"] * 4, 100),
    ],
)
def test_provisional_score(severities: list[str], score: int) -> None:
    assert provisional_score([reason(s) for s in severities]) == score


def test_summary_wording() -> None:
    assert summarize([]) == "No warning signs found."
    assert summarize([reason("low")]) == "WindyMail found 1 warning sign."
    assert summarize([reason("low"), reason("high")]) == "WindyMail found 2 warning signs."
