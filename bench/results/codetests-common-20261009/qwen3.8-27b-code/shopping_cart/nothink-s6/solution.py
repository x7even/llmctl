from decimal import Decimal, ROUND_HALF_UP


class Cart:
    _TWO_PLACES = Decimal("0.01")

    def __init__(self, tax_rate: str | Decimal = "0") -> None:
        rate = Decimal(tax_rate)
        if rate < 0 or rate > 1:
            raise ValueError("tax_rate must be between 0 and 1 inclusive")
        self._tax_rate: Decimal = rate
        # sku -> (price: Decimal, qty: int)
        self._items: dict[str, tuple[Decimal, int]] = {}
        self._coupon: str | None = None

    def add_item(self, sku: str, price: str | Decimal, qty: int = 1) -> None:
        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
            raise ValueError("qty must be an int >= 1")
        unit_price = Decimal(price) if isinstance(price, str) else price
        if unit_price < 0:
            raise ValueError("price must be >= 0")

        if sku in self._items:
            existing_price, existing_qty = self._items[sku]
            if existing_price != unit_price:
                raise ValueError(
                    f"SKU {sku!r} already in cart with a different price"
                )
            self._items[sku] = (existing_price, existing_qty + qty)
        else:
            self._items[sku] = (unit_price, qty)

    def remove_item(self, sku: str, qty: int | None = None) -> None:
        if sku not in self._items:
            raise KeyError(sku)

        if qty is None:
            del self._items[sku]
            return

        if not isinstance(qty, int) or isinstance(qty, bool):
            raise ValueError("qty must be an int or None")
        if qty < 1:
            raise ValueError("qty must be >= 1")

        existing_price, existing_qty = self._items[sku]
        if qty > existing_qty:
            raise ValueError("qty exceeds the quantity in the cart")

        remaining = existing_qty - qty
        if remaining == 0:
            del self._items[sku]
        else:
            self._items[sku] = (existing_price, remaining)

    def apply_coupon(self, code: str) -> None:
        if code not in ("SAVE10", "FIVEOFF"):
            raise ValueError(f"Unknown coupon code: {code!r}")
        self._coupon = code

    def item_count(self) -> int:
        return sum(qty for _, qty in self._items.values())

    def _round_cents(self, value: Decimal) -> Decimal:
        return value.quantize(self._TWO_PLACES, rounding=ROUND_HALF_UP)

    def summary(self) -> dict[str, Decimal]:
        subtotal = Decimal("0")
        for price, qty in self._items.values():
            subtotal += price * qty

        discount = Decimal("0")
        if self._coupon == "SAVE10":
            discount = subtotal * Decimal("0.10")
        elif self._coupon == "FIVEOFF":
            discount = min(Decimal("5.00"), subtotal)

        discount = self._round_cents(discount)
        taxable = subtotal - discount
        tax = self._round_cents(taxable * self._tax_rate)
        total = subtotal - discount + tax

        return {
            "subtotal": self._round_cents(subtotal),
            "discount": discount,
            "tax": tax,
            "total": self._round_cents(total),
        }
