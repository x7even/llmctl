from decimal import Decimal, ROUND_HALF_UP

_CENT = Decimal("0.01")


class Cart:
    def __init__(self, tax_rate: str | Decimal = "0") -> None:
        rate = Decimal(tax_rate) if isinstance(tax_rate, str) else tax_rate
        if rate < Decimal("0") or rate > Decimal("1"):
            raise ValueError("tax_rate must be between 0 and 1 inclusive")
        self._tax_rate: Decimal = rate
        self._items: dict[str, tuple[Decimal, int]] = {}
        self._coupon: str | None = None

    def add_item(self, sku: str, price: str | Decimal, qty: int = 1) -> None:
        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
            raise ValueError("qty must be an int >= 1")
        p = Decimal(price) if isinstance(price, str) else price
        if p < Decimal("0"):
            raise ValueError("price must be >= 0")
        if sku in self._items:
            existing_price, existing_qty = self._items[sku]
            if existing_price != p:
                raise ValueError(
                    "price differs from the price already set for this SKU"
                )
            self._items[sku] = (existing_price, existing_qty + qty)
        else:
            self._items[sku] = (p, qty)

    def remove_item(self, sku: str, qty: int | None = None) -> None:
        if sku not in self._items:
            raise KeyError(sku)
        if qty is None:
            del self._items[sku]
            return
        if qty < 1:
            raise ValueError("qty must be >= 1")
        _, existing_qty = self._items[sku]
        if qty > existing_qty:
            raise ValueError("qty exceeds quantity in cart")
        new_qty = existing_qty - qty
        if new_qty == 0:
            del self._items[sku]
        else:
            self._items[sku] = (self._items[sku][0], new_qty)

    def apply_coupon(self, code: str) -> None:
        if code == "SAVE10":
            self._coupon = "SAVE10"
        elif code == "FIVEOFF":
            self._coupon = "FIVEOFF"
        else:
            raise ValueError(f"Unknown coupon code: {code!r}")

    def item_count(self) -> int:
        return sum(qty for _, qty in self._items.values())

    def summary(self) -> dict[str, Decimal]:
        subtotal = sum(
            (p * q for p, q in self._items.values()), Decimal("0")
        )
        subtotal = subtotal.quantize(_CENT, rounding=ROUND_HALF_UP)

        if self._coupon == "SAVE10":
            discount = subtotal * Decimal("0.10")
        elif self._coupon == "FIVEOFF":
            discount = min(Decimal("5.00"), subtotal)
        else:
            discount = Decimal("0")
        discount = discount.quantize(_CENT, rounding=ROUND_HALF_UP)

        tax = ((subtotal - discount) * self._tax_rate).quantize(
            _CENT, rounding=ROUND_HALF_UP
        )

        total = (subtotal - discount + tax).quantize(
            _CENT, rounding=ROUND_HALF_UP
        )

        return {
            "subtotal": subtotal,
            "discount": discount,
            "tax": tax,
            "total": total,
        }
