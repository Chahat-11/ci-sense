def test_mean_empty():
    with pytest.raises(ValueError):
        stats.mean([])


def test_median_single_and_empty():
    assert stats.median([7]) == 7
    with pytest.raises(ValueError):
        stats.median([])


def test_clamp_inside_and_invalid():
    assert stats.clamp(2, 0, 3) == 2
    assert stats.clamp(3, 0, 3) == 3
    with pytest.raises(ValueError):
        stats.clamp(1, 5, 0)


def test_moving_average_edges():
    assert stats.moving_average([1, 2, 3], 3) == [2.0]
    assert stats.moving_average([1, 2], 3) == []
    assert stats.moving_average([1, 2], 0) == []


def test_normalize_constant():
    assert stats.normalize([5, 5]) == [0.0, 0.0]
    assert stats.normalize([0, 10]) == [0.0, 1.0]
