from decimal import Decimal, ROUND_HALF_UP


class Cart:
    _COUPONS = {
        "SAVE10": ("percent", Decimal("0.10")),
        "FIVEOFF": ("fixed", Decimal("5.00")),
    }

    def __init__(self, tax_rate: str | Decimal = "0") -> None:
        if isinstance(tax_rate, str):
            tax_rate = Decimal(tax_rate)
        if not isinstance(tax_rate, Decimal):
            raise ValueError("tax_rate must be a str or Decimal")
        if tax_rate < 0 or tax_rate > 1:
            raise ValueError("tax_rate must be between 0 and 1 inclusive")
        self._tax_rate: Decimal = tax_rate
        self._items: dict[str, dict[str, Decimal | int]] = {}
        self._coupon: str | None = None

    def _quantize(self, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def add_item(self, sku: str, price: str | Decimal, qty: int = 1) -> None:
        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
            raise ValueError("qty must be an int >= 1")
        if isinstance(price, str):
            price = Decimal(price)
        if not isinstance(price, Decimal):
            raise ValueError("price must be a str or Decimal")
        if price < 0:
            raise ValueError("price must be >= 0")

        if sku in self._items:
            existing_price = self._items[sku]["price"]
            if existing_price != price:
                raise ValueError(
                    f"Price mismatch for SKU {sku!r}: "
                    f"{existing_price} vs {price}"
                )
            self._items[sku]["qty"] += qty
        else:
            self._items[sku] = {"price": price, "qty": qty}

    def remove_item(self, sku: str, qty: int | None = None) -> None:
        if sku not in self._items:
            raise KeyError(sku)
        if qty is None:
            del self._items[sku]
            return
        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
            raise ValueError("qty must be an int >= 1 or None")
        current_qty = self._items[sku]["qty"]
        if qty > current_qty:
            raise ValueError(
                f"qty {qty} exceeds quantity in cart {current_qty}"
            )
        if qty == current_qty:
            del self._items[sku]
        else:
            self._items[sku]["qty"] = current_qty - qty

    def apply_coupon(self, code: str) -> None:
        if code not in self._COUPONS:
            raise ValueError(f"Unknown coupon code: {code!r}")
        self._coupon = code

    def item_count(self) -> int:
        return sum(line["qty"] for line in self._items.values())

    def _compute_discount(self, subtotal: Decimal) -> Decimal:
        if self._coupon is None:
            return Decimal("0.00")
        kind, value = self._COUPONS[self._coupon]
        if kind == "percent":
            discount = subtotal * value
        else:
            discount = min(value, subtotal)
        return self._quantize(discount)

    def summary(self) -> dict[str, Decimal]:
        subtotal = Decimal("0")
        for line in self._items.values():
            subtotal += line["price"] * line["qty"]

        discount = self._compute_discount(subtotal)
        taxable = subtotal - discount
        tax = self._quantize(taxable * self._tax_rate)
        total = subtotal - discount + tax

        return {
            "subtotal": self._quantize(subtotal),
            "discount": discount,
            "tax": tax,
            "total": self._quantize(total),
        }
