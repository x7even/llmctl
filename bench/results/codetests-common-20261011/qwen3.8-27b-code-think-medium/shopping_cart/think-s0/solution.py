from decimal import Decimal, ROUND_HALF_UP


class Cart:
    def __init__(self, tax_rate: str | Decimal = "0") -> None:
        self._tax_rate = Decimal(tax_rate)
        if self._tax_rate < 0 or self._tax_rate > 1:
            raise ValueError("tax_rate must be between 0 and 1 inclusive")
        self._items: dict[str, tuple[Decimal, int]] = {}
        self._coupon: str | None = None

    def add_item(self, sku: str, price: str | Decimal, qty: int = 1) -> None:
        if not isinstance(qty, int) or qty < 1:
            raise ValueError("qty must be an int >= 1")
        if isinstance(price, str):
            price = Decimal(price)
        if price < 0:
            raise ValueError("price must be >= 0")
        if sku in self._items:
            existing_price, existing_qty = self._items[sku]
            if existing_price != price:
                raise ValueError("SKU already in cart with a different price")
            self._items[sku] = (existing_price, existing_qty + qty)
        else:
            self._items[sku] = (price, qty)

    def remove_item(self, sku: str, qty: int | None = None) -> None:
        if sku not in self._items:
            raise KeyError(sku)
        if qty is None:
            del self._items[sku]
        else:
            if qty < 1:
                raise ValueError("qty must be >= 1")
            existing_price, existing_qty = self._items[sku]
            if qty > existing_qty:
                raise ValueError("qty exceeds quantity in cart")
            if qty == existing_qty:
                del self._items[sku]
            else:
                self._items[sku] = (existing_price, existing_qty - qty)

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

        two_places = Decimal("0.01")
        subtotal = raw_subtotal.quantize(two_places, rounding=ROUND_HALF_UP)
        discount = raw_discount.quantize(two_places, rounding=ROUND_HALF_UP)
        tax = ((raw_subtotal - discount) * self._tax_rate).quantize(
            two_places, rounding=ROUND_HALF_UP
        )
        total = subtotal - discount + tax

        return {
            "subtotal": subtotal,
            "discount": discount,
            "tax": tax,
            "total": total,
        }
