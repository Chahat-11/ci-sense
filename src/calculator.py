def add(a, b):
    return a + b


def divide(a, b):
    if not b:
        raise ValueError("cannot divide by zero")
    return a / b
