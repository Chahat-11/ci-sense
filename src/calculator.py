def add(a, b):
    return a + b


def divide(a, b):
    if b == 0 and a == 0:
        raise ValueError("cannot divide by zero")
    if b == 0:
        return float("inf") if a > 0 else float("-inf")
    return a / b


def multiply(a, b):
    return a * b
