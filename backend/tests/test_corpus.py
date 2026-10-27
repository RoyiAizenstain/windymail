"""Realistic emails with the verdict each should get (ADR-010, Layer 5).

Rules only: tests never call the LLM, and the verdicts must hold without it (ADR-005).
Run with `-s` to see the score table:  pytest tests/test_corpus.py -s
"""

import json
from pathlib import Path

import pytest

from app.analysis import analyze
from app.models import AnalyzeRequest

CORPUS = sorted((Path(__file__).parent / "fixtures" / "corpus").glob("*.json"))


def load(path: Path) -> tuple[AnalyzeRequest, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return AnalyzeRequest.model_validate(data["request"]), data["expect"]["verdict"]


@pytest.mark.parametrize("path", CORPUS, ids=[p.stem for p in CORPUS])
def test_corpus_verdict(path: Path) -> None:
    request, expected = load(path)
    result = analyze(request)
    reasons = ", ".join(f"{r.id}({r.severity})" for r in result.reasons) or "-"
    assert result.verdict == expected, f"score {result.score}: {reasons}"


def test_corpus_has_both_kinds() -> None:
    verdicts = [load(path)[1] for path in CORPUS]
    assert verdicts.count("safe") >= 8 and len(verdicts) - verdicts.count("safe") >= 6


def test_print_score_table() -> None:
    rows = []
    for path in CORPUS:
        request, expected = load(path)
        result = analyze(request)
        mark = "ok " if result.verdict == expected else "BAD"
        reasons = ", ".join(f"{r.id}({r.severity[0]})" for r in result.reasons) or "-"
        rows.append(f"{mark} {path.stem:28} {result.score:3} {result.verdict:10} {reasons}")
    print("\n" + "\n".join(rows))
