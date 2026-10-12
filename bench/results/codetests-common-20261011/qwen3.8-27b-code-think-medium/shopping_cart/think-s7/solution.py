from decimal import Decimal, ROUND_HALF_UP

_CENTS = Decimal("0.01")


class Cart:
    def __init__(self, tax_rate: str | Decimal = "0") -> None:
        rate = Decimal(tax_rate) if isinstance(tax_rate, str) else tax_rate
        if rate < 0 or rate > 1:
            raise ValueError("tax_rate must be between 0 and 1 inclusive")
        self._tax_rate: Decimal = rate
        self._items: dict[str, tuple[Decimal, int]] = {}
        self._coupon: str | None = None

    def add_item(self, sku: str, price: str | Decimal, qty: int = 1) -> None:
        if not isinstance(qty, int) or qty < 1:
            raise ValueError("qty must be an int >= 1")
        unit_price = Decimal(price) if isinstance(price, str) else price
        if unit_price < 0:
            raise ValueError("price must be >= 0")
        if sku in self._items:
            existing_price, existing_qty = self._items[sku]
            if existing_price != unit_price:
                raise ValueError("price for SKU already in cart differs")
            self._items[sku] = (existing_price, existing_qty + qty)
        else:
            self._items[sku] = (unit_price, qty)

    def remove_item(self, sku: str, qty: int | None = None) -> None:
        if sku not in self._items:
            raise KeyError(sku)
        if qty is None:
            del self._items[sku]
        else:
            if not isinstance(qty, int) or qty < 1:
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
        if code not in ("SAVE10", "FIVEOFF"):
            raise ValueError(f"Unknown coupon code: {code}")
        self._coupon = code

    def item_count(self) -> int:
        return sum(qty for _, qty in self._items.values())

    def summary(self) -> dict[str, Decimal]:
        raw_subtotal = sum(
            (price * qty for price, qty in self._items.values()),
            Decimal("0"),
        )

        if self._coupon == "SAVE10":
            raw_discount = raw_subtotal * Decimal("0.10")
        elif self._coupon == "FIVEOFF":
            raw_discount = min(Decimal("5.00"), raw_subtotal)
        else:
            raw_discount = Decimal("0")
        discount = raw_discount.quantize(_CENTS, rounding=ROUND_HALF_UP)

        raw_tax = (raw_subtotal - discount) * self._tax_rate
        tax = raw_tax.quantize(_CENTS, rounding=ROUND_HALF_UP)

        total = (raw_subtotal - discount + tax).quantize(_CENTS, rounding=ROUND_HALF_UP)
        subtotal = raw_subtotal.quantize(_CENTS, rounding=ROUND_HALF_UP)

        return {
            "subtotal": subtotal,
            "discount": discount,
            "tax": tax,
            "total": total,
        }
