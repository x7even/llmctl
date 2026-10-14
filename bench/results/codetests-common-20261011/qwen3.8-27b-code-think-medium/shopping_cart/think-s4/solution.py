from decimal import Decimal, ROUND_HALF_UP


class Cart:
    def __init__(self, tax_rate: str | Decimal = "0") -> None:
        if isinstance(tax_rate, str):
            tax_rate = Decimal(tax_rate)
        if not (Decimal("0") <= tax_rate <= Decimal("1")):
            raise ValueError("tax_rate must be between 0 and 1 inclusive")
        self._tax_rate: Decimal = tax_rate
        self._items: dict[str, tuple[Decimal, int]] = {}
        self._coupon: str | None = None

    def add_item(self, sku: str, price: str | Decimal, qty: int = 1) -> None:
        if not isinstance(qty, int) or qty < 1:
            raise ValueError("qty must be an int >= 1")
        if isinstance(price, str):
            price = Decimal(price)
        if not isinstance(price, Decimal):
            raise ValueError("price must be a str or Decimal")
        if price < Decimal("0"):
            raise ValueError("price must be >= 0")

        if sku in self._items:
            existing_price, existing_qty = self._items[sku]
            if existing_price != price:
                raise ValueError("price mismatch for SKU")
            self._items[sku] = (existing_price, existing_qty + qty)
        else:
            self._items[sku] = (price, qty)

    def remove_item(self, sku: str, qty: int | None = None) -> None:
        if sku not in self._items:
            raise KeyError(sku)
        if qty is None:
            del self._items[sku]
        else:
            existing_price, existing_qty = self._items[sku]
            if qty < 1 or qty > existing_qty:
                raise ValueError("qty must be between 1 and the quantity in the cart")
            remaining = existing_qty - qty
            if remaining == 0:
                del self._items[sku]
            else:
                self._items[sku] = (existing_price, remaining)

    def apply_coupon(self, code: str) -> None:
        if code == "SAVE10":
            self._coupon = "SAVE10"
        elif code == "FIVEOFF":
            self._coupon = "FIVEOFF"
        else:
            raise ValueError(f"Unknown coupon code: {code}")

    def item_count(self) -> int:
        return sum(qty for _, qty in self._items.values())

    def summary(self) -> dict[str, Decimal]:
        two_places = Decimal("0.01")

        subtotal = sum(price * qty for price, qty in self._items.values())

        if self._coupon == "SAVE10":
            discount = subtotal * Decimal("0.10")
        elif self._coupon == "FIVEOFF":
            discount = min(Decimal("5.00"), subtotal)
        else:
            discount = Decimal("0")

        subtotal_r = subtotal.quantize(two_places, rounding=ROUND_HALF_UP)
        discount_r = discount.quantize(two_places, rounding=ROUND_HALF_UP)
        tax_r = ((subtotal_r - discount_r) * self._tax_rate).quantize(
            two_places, rounding=ROUND_HALF_UP
        )
        total_r = (subtotal_r - discount_r + tax_r).quantize(
            two_places, rounding=ROUND_HALF_UP
        )

        return {
            "subtotal": subtotal_r,
            "discount": discount_r,
            "tax": tax_r,
            "total": total_r,
        }
