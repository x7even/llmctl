from decimal import Decimal, ROUND_HALF_UP


class Cart:
    def __init__(self, tax_rate: str | Decimal = "0") -> None:
        rate = Decimal(tax_rate) if isinstance(tax_rate, str) else tax_rate
        if rate < 0 or rate > 1:
            raise ValueError("tax_rate must be between 0 and 1 inclusive")
        self._tax_rate: Decimal = rate
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
                raise ValueError("price mismatch for existing SKU")
            self._items[sku] = (p, existing_qty + qty)
        else:
            self._items[sku] = (p, qty)

    def remove_item(self, sku: str, qty: int | None = None) -> None:
        if sku not in self._items:
            raise KeyError(sku)
        if qty is None:
            del self._items[sku]
        else:
            if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
                raise ValueError("qty must be an int >= 1")
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
            self._coupon = code
        elif code == "FIVEOFF":
            self._coupon = code
        else:
            raise ValueError(f"Unknown coupon code: {code}")

    def item_count(self) -> int:
        return sum(qty for _, qty in self._items.values())

    def summary(self) -> dict[str, Decimal]:
        cents = Decimal("0.01")

        raw_subtotal = sum((p * q for p, q in self._items.values()), Decimal(0))
        subtotal = raw_subtotal.quantize(cents, rounding=ROUND_HALF_UP)

        if self._coupon == "SAVE10":
            raw_discount = subtotal * Decimal("0.10")
        elif self._coupon == "FIVEOFF":
            raw_discount = min(Decimal("5.00"), subtotal)
        else:
            raw_discount = Decimal("0")
        discount = raw_discount.quantize(cents, rounding=ROUND_HALF_UP)

        taxable = subtotal - discount
        raw_tax = taxable * self._tax_rate
        tax = raw_tax.quantize(cents, rounding=ROUND_HALF_UP)

        total = (subtotal - discount + tax).quantize(cents, rounding=ROUND_HALF_UP)

        return {
            "subtotal": subtotal,
            "discount": discount,
            "tax": tax,
            "total": total,
        }
