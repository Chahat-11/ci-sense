def add(a, b):
    return round(a + b, 1)


def divide(a, b):
    if b == 0:
        raise ValueError("cannot divide by zero")
    return a / b
