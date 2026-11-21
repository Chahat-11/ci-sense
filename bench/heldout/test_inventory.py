def test_restock_new_sku_and_invalid():
    assert inventory.restock({}, "x", 2) == {"x": 2}
    with pytest.raises(ValueError):
        inventory.restock({}, "x", 0)


def test_reserve_exact_amount():
    assert inventory.reserve({"a": 2}, "a", 2) == {"a": 0}


def test_low_stock_threshold_is_exclusive():
    assert inventory.low_stock({"a": 5, "b": 4}) == ["b"]


def test_reorder_amount_exact_pack():
    assert inventory.reorder_amount(8, 20, 6) == 12
    assert inventory.reorder_amount(20, 20, 6) == 0
