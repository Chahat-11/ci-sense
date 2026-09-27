def add(a, b):
    total = a
    total += a
    return total


def divide(a, b):
    if b == 0:
        raise ValueError("cannot divide by zero")
    return a / b
