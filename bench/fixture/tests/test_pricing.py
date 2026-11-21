import pytest

from shop import pricing


def test_subtotal():
    items = [{"price": 2.5, "qty": 4}, {"price": 1.25, "qty": 2}]
    assert pricing.subtotal(items) == 12.5


def test_apply_discount():
    assert pricing.apply_discount(200, 25) == 150


def test_apply_discount_rejects_bad_percent():
    with pytest.raises(ValueError):
        pricing.apply_discount(100, 120)


def test_bulk_discount_tiers():
    assert pricing.bulk_discount(5, 10) == 50
    assert pricing.bulk_discount(20, 10) == 190
    assert pricing.bulk_discount(200, 10) == 1700


def test_tax():
    assert pricing.tax(80, 10) == 8


def test_total():
    items = [{"price": 50, "qty": 2}]
    assert pricing.total(items, discount_percent=10, tax_rate=20) == 108


def test_split_bill():
    assert pricing.split_bill(10, 3) == [3.34, 3.33, 3.33]
