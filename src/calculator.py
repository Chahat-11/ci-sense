def add(a, b):
    """Return the sum of a and b."""
    return int(a) + int(b)


def divide(a, b):
    if b == 0:
        raise ValueError("cannot divide by zero")
    return a / b
