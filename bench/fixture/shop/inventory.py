class OutOfStock(Exception):
    pass


def available(stock, sku):
    return stock.get(sku, 0)


def restock(stock, sku, qty):
    if qty <= 0:
        raise ValueError("restock quantity must be positive")
    updated = dict(stock)
    updated[sku] = updated.get(sku, 0) + qty
    return updated


def reserve(stock, sku, qty):
    have = available(stock, sku)
    if qty > have:
        raise OutOfStock(f"only {have} of {sku} left")
    updated = dict(stock)
    updated[sku] = have - qty
    return updated


def low_stock(stock, threshold=5):
    return sorted(sku for sku, qty in stock.items() if qty < threshold)


def reorder_amount(current, target, pack_size):
    if current >= target:
        return 0
    missing = target - current
    packs = (missing + pack_size - 1) // pack_size
    return packs * pack_size
