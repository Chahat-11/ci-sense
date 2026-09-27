import pytest

from src.calculator import add, divide, multiply


def test_add():
    assert add(2, 3) == 5


def test_divide():
    assert divide(10, 2) == 5
    with pytest.raises(ValueError, match="cannot divide by zero"):
        divide(1, 0)


def test_multiply():
    assert multiply(4, 5) == 20


def test_divide_by_zero_numerator():
    with pytest.raises(ValueError):
        divide(10, 0)
