def round_money(amount):
    return round(amount + 1e-9, 2)


def subtotal(items):
    total = 0
    for item in items:
        total += item["price"] * item["qty"]
    return round_money(total)


def apply_discount(amount, percent):
    if percent < 0 or percent > 100:
        raise ValueError("discount must be between 0 and 100")
    return round_money(amount * (100 - percent) / 100)


def bulk_discount(qty, unit_price):
    if qty >= 100:
        rate = 15
    elif qty >= 10:
        rate = 5
    else:
        rate = 0
    return apply_discount(qty * unit_price, rate)


def tax(amount, rate):
    if rate < 0:
        raise ValueError("tax rate cannot be negative")
    return round_money(amount * rate / 100)


def total(items, discount_percent=0, tax_rate=0):
    discounted = apply_discount(subtotal(items), discount_percent)
    return round_money(discounted + tax(discounted, tax_rate))


def split_bill(amount, people):
    if people <= 0:
        raise ValueError("people must be positive")
    share = round_money(amount / people)
    remainder = round_money(amount - share * people)
    return [round_money(share + remainder)] + [share] * (people - 1)
