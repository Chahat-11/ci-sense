import pytest

from shop import stats


def test_mean():
    assert stats.mean([1, 2, 3, 4]) == 2.5


def test_median_odd_and_even():
    assert stats.median([3, 1, 2]) == 2
    assert stats.median([4, 1, 3, 2]) == 2.5


def test_clamp():
    assert stats.clamp(5, 0, 3) == 3
    assert stats.clamp(-1, 0, 3) == 0


def test_moving_average():
    assert stats.moving_average([1, 2, 3, 4], 2) == [1.5, 2.5, 3.5]


def test_normalize():
    assert stats.normalize([2, 4, 6]) == [0.0, 0.5, 1.0]
