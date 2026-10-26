"""End-to-end: the Step 8 test emails, as JSON, through the real /analyze endpoint."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

FIXTURES = sorted((Path(__file__).parent / "fixtures").glob("*.json"))


@pytest.mark.parametrize("path", FIXTURES, ids=[p.stem for p in FIXTURES])
def test_fixture(client: TestClient, path: Path) -> None:
    fixture = json.loads(path.read_text())
    response = client.post("/api/v1/analyze", json=fixture["request"])
    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == fixture["expect"]["verdict"]
    assert [r["id"] for r in body["reasons"]] == fixture["expect"]["reasons"]
    # Nothing from the subject or body is echoed (ADR-017).
    assert fixture["request"]["subject"] not in response.text


def test_fixtures_present() -> None:
    assert {p.stem for p in FIXTURES} == {"clean", "phishing", "newsletter"}
