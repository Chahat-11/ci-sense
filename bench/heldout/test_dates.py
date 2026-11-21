def test_is_leap_century_rule():
    assert dates.is_leap(2000)
    assert not dates.is_leap(2100)


def test_days_in_month_edges():
    assert dates.days_in_month(2023, 1) == 31
    assert dates.days_in_month(2023, 12) == 31
    with pytest.raises(ValueError):
        dates.days_in_month(2023, 0)


def test_day_of_year_leap_and_first_day():
    assert dates.day_of_year(2024, 3, 1) == 61
    assert dates.day_of_year(2023, 1, 1) == 1


def test_quarter_boundaries():
    assert dates.quarter(3) == 1
    assert dates.quarter(4) == 2
    assert dates.quarter(12) == 4


def test_format_duration_small_and_exact():
    assert dates.format_duration(59) == "59s"
    assert dates.format_duration(3600) == "1h 00m"
    assert dates.format_duration(60) == "1m 00s"
