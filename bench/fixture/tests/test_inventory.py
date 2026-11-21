import pytest

from shop import inventory


def test_available():
    assert inventory.available({"a": 3}, "a") == 3
    assert inventory.available({}, "b") == 0


def test_restock():
    assert inventory.restock({"a": 1}, "a", 4) == {"a": 5}


def test_reserve():
    assert inventory.reserve({"a": 5}, "a", 2) == {"a": 3}


def test_reserve_out_of_stock():
    with pytest.raises(inventory.OutOfStock):
        inventory.reserve({"a": 1}, "a", 3)


def test_low_stock():
    assert inventory.low_stock({"a": 1, "b": 10, "c": 4}) == ["a", "c"]


def test_reorder_amount():
    assert inventory.reorder_amount(3, 20, 6) == 18
    assert inventory.reorder_amount(25, 20, 6) == 0
