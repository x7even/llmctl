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
        self._items: dict[str, tuple[Decimal, int]] = {}
        self._coupon: str | None = None

    def add_item(self, sku: str, price: str | Decimal, qty: int = 1) -> None:
        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
            raise ValueError("qty must be an int >= 1")
        p = Decimal(price) if isinstance(price, str) else price
        if p < 0:
            raise ValueError("price must be >= 0")
        if sku in self._items:
            existing_price, existing_qty = self._items[sku]
            if existing_price != p:
                raise ValueError("price conflict for existing SKU")
            self._items[sku] = (existing_price, existing_qty + qty)
        else:
            self._items[sku] = (p, qty)

    def remove_item(self, sku: str, qty: int | None = None) -> None:
        if sku not in self._items:
            raise KeyError(sku)
        if qty is None:
            del self._items[sku]
            return
        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
            raise ValueError("qty must be an int >= 1")
        existing_price, existing_qty = self._items[sku]
        if qty > existing_qty:
            raise ValueError("qty exceeds quantity in cart")
        remaining = existing_qty - qty
        if remaining == 0:
            del self._items[sku]
        else:
            self._items[sku] = (existing_price, remaining)

    def apply_coupon(self, code: str) -> None:
        if code not in self._COUPONS:
            raise ValueError(f"unknown coupon code: {code}")
        self._coupon = code

    def item_count(self) -> int:
        return sum(qty for _, qty in self._items.values())

    def summary(self) -> dict[str, Decimal]:
        subtotal = sum(
            (price * qty for price, qty in self._items.values()),
            Decimal("0"),
        )

        discount = Decimal("0")
        if self._coupon is not None:
            kind, value = self._COUPONS[self._coupon]
            if kind == "percent":
                discount = subtotal * value
            else:  # fixed
                discount = min(value, subtotal)

        taxable = subtotal - discount
        tax = taxable * self._tax_rate

        def round_cents(d: Decimal) -> Decimal:
            return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        subtotal_r = round_cents(subtotal)
        discount_r = round_cents(discount)
        tax_r = round_cents(tax)
        total_r = subtotal_r - discount_r + tax_r

        return {
            "subtotal": subtotal_r,
            "discount": discount_r,
            "tax": tax_r,
            "total": total_r,
        }
