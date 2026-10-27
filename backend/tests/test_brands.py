import pytest

from app.signals.brands import brands_named_in, is_official, skeleton


@pytest.mark.parametrize(
    ("text", "expected"),
    [("PayPaI", "paypal"), ("paypa1", "paypal"), ("rnicrosoft", "microsoft"), ("g00gle", "google")],
)
def test_skeleton_undoes_lookalike_characters(text: str, expected: str) -> None:
    assert skeleton(text) == expected


@pytest.mark.parametrize(
    ("name", "brands"),
    [
        ("PayPal Security", ["paypal"]),
        ("PayPaI Support", ["paypal"]),
        ("P-a-y-P-a-l Team", ["paypal"]),
        ("Microsoft Office 365", ["microsoft"]),
        ("Outlook Team", ["microsoft"]),
        ("Netflix & Apple", ["apple", "netflix"]),
        ("Alice Cohen", []),
        ("Pineapple Express", []),
        ("Updates", []),
    ],
)
def test_brands_named_in(name: str, brands: list[str]) -> None:
    assert sorted(brands_named_in(name)) == brands


def test_is_official() -> None:
    assert is_official("paypal", "paypal.com")
    assert not is_official("paypal", "paypal-secure.com")
    assert not is_official("google", "gmail.com")  # anyone can have a Gmail address
    assert not is_official("paypal", None)


# Hebrew display names (whole phrases, so common words don't match)


@pytest.mark.parametrize(
    ("name", "brand"),
    [
        ('"בנק לאומי"', "leumi"),
        ("בַּנְק לְאוּמִי", "leumi"),  # vowel marks
        ("בנק​ לאומי", "leumi"),  # zero-width character between the words
        ("שירות לקוחות בנק הפועלים", "hapoalim"),
        ("צוות פייפאל", "paypal"),
        ("תמיכת מיקרוסופט", "microsoft"),
    ],
)
def test_hebrew_brand_names(name: str, brand: str) -> None:
    assert brands_named_in(name) == [brand]


@pytest.mark.parametrize("name", ["ביטוח לאומי", "מועדון הפועל", "ספריה לאומית", "אמא"])
def test_hebrew_common_words_are_not_brands(name: str) -> None:
    assert brands_named_in(name) == []
