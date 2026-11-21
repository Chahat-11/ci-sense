def test_subtotal_empty():
    assert pricing.subtotal([]) == 0


def test_apply_discount_bounds():
    assert pricing.apply_discount(80, 0) == 80
    assert pricing.apply_discount(80, 100) == 0


def test_apply_discount_rejects_negative():
    with pytest.raises(ValueError):
        pricing.apply_discount(100, -5)


def test_bulk_discount_exact_thresholds():
    assert pricing.bulk_discount(10, 10) == 95
    assert pricing.bulk_discount(100, 10) == 850


def test_tax_zero_and_negative():
    assert pricing.tax(50, 0) == 0
    with pytest.raises(ValueError):
        pricing.tax(50, -1)


def test_total_without_extras():
    assert pricing.total([{"price": 3, "qty": 3}]) == 9


def test_split_bill_even_and_invalid():
    assert pricing.split_bill(9, 3) == [3, 3, 3]
    with pytest.raises(ValueError):
        pricing.split_bill(9, 0)
