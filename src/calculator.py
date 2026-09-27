"""Basic arithmetic helpers."""


def add(a, b):
    return a + b


def safe_divide(a, b):
    if b == 0:
        raise ValueError("cannot divide by zero")
    return a / b
