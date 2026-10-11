from decimal import Decimal, ROUND_HALF_UP, InvalidOperation


class Cart:
    _TWO_PLACES = Decimal("0.01")

    def __init__(self, tax_rate: str | Decimal = "0") -> None:
        rate = self._to_decimal(tax_rate, "tax_rate")
        if rate < 0 or rate > 1:
            raise ValueError("tax_rate must be between 0 and 1 inclusive")
        self._tax_rate: Decimal = rate
        # sku -> {"price": Decimal, "qty": int}
        self._items: dict[str, dict[str, object]] = {}
        self._coupon: str | None = None

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _to_decimal(value: str | Decimal, name: str) -> Decimal:
        if isinstance(value, Decimal):
            return value
        if isinstance(value, str):
            try:
                return Decimal(value)
            except InvalidOperation:
                raise ValueError(f"{name} is not a valid decimal")
        raise ValueError(f"{name} must be a str or Decimal")

    def _quantize(self, value: Decimal) -> Decimal:
        return value.quantize(self._TWO_PLACES, rounding=ROUND_HALF_UP)

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def add_item(self, sku: str, price: str | Decimal, qty: int = 1) -> None:
        unit_price = self._to_decimal(price, "price")
        if unit_price < 0:
            raise ValueError("price must be >= 0")
        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
            raise ValueError("qty must be an int >= 1")

        if sku in self._items:
            existing = self._items[sku]
            existing_price: Decimal = existing["price"]  # type: ignore[assignment]
            if existing_price != unit_price:
                raise ValueError(
                    f"price for SKU {sku!r} already in cart differs"
                )
            existing["qty"] = int(existing["qty"]) + qty  # type: ignore[operator]
        else:
            self._items[sku] = {"price": unit_price, "qty": qty}

    def remove_item(self, sku: str, qty: int | None = None) -> None:
        if sku not in self._items:
            raise KeyError(sku)

        entry = self._items[sku]
        current_qty: int = entry["qty"]  # type: ignore[assignment]

        if qty is None:
            del self._items[sku]
            return

        if not isinstance(qty, int) or isinstance(qty, bool):
            raise ValueError("qty must be an int or None")
        if qty < 1:
            raise ValueError("qty must be >= 1")
        if qty > current_qty:
            raise ValueError("qty exceeds quantity in cart")

        remaining = current_qty - qty
        if remaining == 0:
            del self._items[sku]
        else:
            entry["qty"] = remaining

    def apply_coupon(self, code: str) -> None:
        if code not in ("SAVE10", "FIVEOFF"):
            raise ValueError(f"unknown coupon code: {code!r}")
        self._coupon = code

    def item_count(self) -> int:
        return sum(int(entry["qty"]) for entry in self._items.values())  # type: ignore[arg-type]

    def summary(self) -> dict[str, Decimal]:
        subtotal = Decimal("0")
        for entry in self._items.values():
            price: Decimal = entry["price"]  # type: ignore[assignment]
            qty: int = entry["qty"]  # type: ignore[assignment]
            subtotal += price * qty

        discount = Decimal("0")
        if self._coupon == "SAVE10":
            discount = subtotal * Decimal("0.10")
        elif self._coupon == "FIVEOFF":
            discount = min(Decimal("5.00"), subtotal)

        discount = self._quantize(discount)
        taxable = subtotal - discount
        tax = self._quantize(taxable * self._tax_rate)
        total = subtotal - discount + tax

        return {
            "subtotal": self._quantize(subtotal),
            "discount": discount,
            "tax": tax,
            "total": self._quantize(total),
        }
