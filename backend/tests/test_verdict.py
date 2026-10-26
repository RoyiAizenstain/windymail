import pytest

from app.verdict import verdict_for


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0, "safe"),
        (29, "safe"),
        (30, "suspicious"),
        (69, "suspicious"),
        (70, "malicious"),
        (100, "malicious"),
    ],
)
def test_verdict_thresholds(score: int, expected: str) -> None:
    assert verdict_for(score) == expected


@pytest.mark.parametrize("score", [-1, 101])
def test_verdict_rejects_out_of_range(score: int) -> None:
    with pytest.raises(ValueError):
        verdict_for(score)
