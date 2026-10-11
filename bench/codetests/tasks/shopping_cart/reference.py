from decimal import Decimal, ROUND_HALF_UP

_CENT = Decimal("0.01")


def _q(x):
    return x.quantize(_CENT, rounding=ROUND_HALF_UP)


class Cart:
    def __init__(self, tax_rate="0"):
        rate = Decimal(tax_rate)
        if not (Decimal(0) <= rate <= Decimal(1)):
            raise ValueError("tax_rate must be between 0 and 1")
        self.tax_rate = rate
        self._lines = {}  # sku -> [price, qty]
        self._coupon = None

    def add_item(self, sku, price, qty=1):
        price = Decimal(price)
        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
            raise ValueError("qty must be an int >= 1")
        if price < 0:
            raise ValueError("price must be >= 0")
        if sku in self._lines:
            if self._lines[sku][0] != price:
                raise ValueError("price mismatch for sku")
            self._lines[sku][1] += qty
        else:
            self._lines[sku] = [price, qty]

    def remove_item(self, sku, qty=None):
        if sku not in self._lines:
            raise KeyError(sku)
        have = self._lines[sku][1]
        if qty is None:
            qty = have
        if not isinstance(qty, int) or qty < 1 or qty > have:
            raise ValueError("bad qty")
        if qty == have:
            del self._lines[sku]
        else:
            self._lines[sku][1] -= qty

    def apply_coupon(self, code):
        if code not in ("SAVE10", "FIVEOFF"):
            raise ValueError("unknown coupon")
        self._coupon = code

    def item_count(self):
        return sum(q for _, q in self._lines.values())

    def summary(self):
        subtotal = sum((p * q for p, q in self._lines.values()), Decimal(0))
        if self._coupon == "SAVE10":
            discount = subtotal * Decimal("0.10")
        elif self._coupon == "FIVEOFF":
            discount = min(Decimal("5.00"), subtotal)
        else:
            discount = Decimal(0)
        discount = _q(discount)
        subtotal = _q(subtotal)
        tax = _q((subtotal - discount) * self.tax_rate)
        return {"subtotal": subtotal, "discount": discount, "tax": tax,
                "total": subtotal - discount + tax}
