import pytest

from shop import dates


def test_is_leap():
    assert dates.is_leap(2024)
    assert not dates.is_leap(2023)
    assert not dates.is_leap(1900)


def test_days_in_month():
    assert dates.days_in_month(2023, 2) == 28
    assert dates.days_in_month(2024, 2) == 29
    assert dates.days_in_month(2023, 4) == 30


def test_days_in_month_rejects_bad_month():
    with pytest.raises(ValueError):
        dates.days_in_month(2023, 13)


def test_day_of_year():
    assert dates.day_of_year(2023, 3, 1) == 60


def test_quarter():
    assert dates.quarter(1) == 1
    assert dates.quarter(5) == 2


def test_format_duration():
    assert dates.format_duration(3725) == "1h 02m"
    assert dates.format_duration(65) == "1m 05s"
