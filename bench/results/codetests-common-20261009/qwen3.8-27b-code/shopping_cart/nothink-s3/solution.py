from decimal import Decimal, ROUND_HALF_UP


class Cart:
    _COUPONS = {
        "SAVE10": ("percent", Decimal("0.10")),
        "FIVEOFF": ("fixed", Decimal("5.00")),
    }

    def __init__(self, tax_rate: str | Decimal = "0") -> None:
        rate = Decimal(tax_rate)
        if rate < 0 or rate > 1:
            raise ValueError("tax_rate must be between 0 and 1 inclusive")
        self._tax_rate = rate
        self._items: dict[str, dict] = {}
        self._coupon: str | None = None

    def add_item(self, sku: str, price: str | Decimal, qty: int = 1) -> None:
        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
            raise ValueError("qty must be an int >= 1")
        price_d = Decimal(price)
        if price_d < 0:
            raise ValueError("price must be >= 0")

        if sku in self._items:
            existing = self._items[sku]
            if existing["price"] != price_d:
                raise ValueError("price mismatch for existing SKU")
            existing["qty"] += qty
        else:
            self._items[sku] = {"price": price_d, "qty": qty}

    def remove_item(self, sku: str, qty: int | None = None) -> None:
        if sku not in self._items:
            raise KeyError(sku)

        if qty is None:
            del self._items[sku]
            return

        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
            raise ValueError("qty must be an int >= 1")

        entry = self._items[sku]
        if qty > entry["qty"]:
            raise ValueError("qty exceeds quantity in cart")

        entry["qty"] -= qty
        if entry["qty"] == 0:
            del self._items[sku]

    def apply_coupon(self, code: str) -> None:
        if code not in self._COUPONS:
            raise ValueError(f"Unknown coupon code: {code}")
        self._coupon = code

    def item_count(self) -> int:
        return sum(entry["qty"] for entry in self._items.values())

    def _compute_discount(self, subtotal: Decimal) -> Decimal:
        if self._coupon is None:
            return Decimal("0.00")

        kind, value = self._COUPONS[self._coupon]
        if kind == "percent":
            discount = subtotal * value
        else:
            discount = min(value, subtotal)

        return discount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def summary(self) -> dict[str, Decimal]:
        subtotal = sum(
            (entry["price"] * entry["qty"] for entry in self._items.values()),
            Decimal("0"),
        )

        discount = self._compute_discount(subtotal)

        taxable = subtotal - discount
        tax = (taxable * self._tax_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        total = subtotal - discount + tax

        zero = Decimal("0.00")
        if not self._items:
            return {
                "subtotal": zero,
                "discount": zero,
                "tax": zero,
                "total": zero,
            }

        return {
            "subtotal": subtotal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "discount": discount,
            "tax": tax,
            "total": total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        }
