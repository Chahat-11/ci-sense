def add(a, b):
    return a + b


def divide(a, b):
    if b == 0:
        raise ValueError("division by zero is undefined")
    return a / b


def multiply(a, b):
    return a * b
