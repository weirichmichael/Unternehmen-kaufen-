import pytest

from dealscout.parsing import parse_amount_range, parse_german_date


@pytest.mark.parametrize(
    "text, expected",
    [
        ("500.000 €", (500_000, 500_000)),
        ("500.000\xa0€", (500_000, 500_000)),
        ("über 250 - 500 Tsd. Euro", (250_000, 500_000)),
        ("über 50 - 250 Tsd. Euro", (50_000, 250_000)),
        ("über 500 Tsd. - 2,5 Mio. Euro", (500_000, 2_500_000)),
        ("über 2,5 Mio. Euro", (2_500_000, None)),
        ("bis 50 Tsd. Euro", (None, 50_000)),
        ("2.800.000 € VHB", (2_800_000, 2_800_000)),
        ("245.000.00 VHB €", (245_000, 245_000)),
        ("Bis 249.999,00 €", (None, 249_999)),
        ("Nicht veröffentlicht", (None, None)),
        (None, (None, None)),
    ],
)
def test_parse_amount_range(text, expected):
    assert parse_amount_range(text) == expected


def test_parse_german_date():
    assert parse_german_date("04.11.2026") == "2026-11-04"
    assert parse_german_date("kein Datum") is None
