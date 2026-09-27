import pytest

from src.calculator import add, divide


def test_add():
    assert add(2, 3) == 5


def test_divide():
    assert divide(10, 2) == 5
    with pytest.raises(ValueError, match="cannot divide by zero"):
        divide(1, 0)


def test_divide_negative():
    assert divide(-9, 3) == -3
