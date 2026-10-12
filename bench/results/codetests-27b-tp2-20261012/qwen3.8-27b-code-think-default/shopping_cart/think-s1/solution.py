from decimal import Decimal, ROUND_HALF_UP

_TWO_PLACES = Decimal("0.01")


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
        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
            raise ValueError("qty must be an int >= 1")
        if isinstance(price, str):
            price = Decimal(price)
        if price < Decimal("0"):
            raise ValueError("price must be >= 0")
        if sku in self._items:
            existing_price, existing_qty = self._items[sku]
            if existing_price != price:
                raise ValueError(
                    f"price for SKU {sku!r} already in cart differs"
                )
            self._items[sku] = (price, existing_qty + qty)
        else:
            self._items[sku] = (price, qty)

    def remove_item(self, sku: str, qty: int | None = None) -> None:
        if sku not in self._items:
            raise KeyError(sku)
        if qty is None:
            del self._items[sku]
        else:
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
        if code not in ("SAVE10", "FIVEOFF"):
            raise ValueError(f"Unknown coupon code: {code!r}")
        self._coupon = code

    def item_count(self) -> int:
        return sum(qty for _, qty in self._items.values())

    def summary(self) -> dict[str, Decimal]:
        subtotal_raw = sum(
            (price * qty for price, qty in self._items.values()),
            Decimal("0"),
        )

        if self._coupon is None:
            discount_raw = Decimal("0")
        elif self._coupon == "SAVE10":
            discount_raw = subtotal_raw * Decimal("0.10")
        else:  # FIVEOFF
            discount_raw = min(Decimal("5.00"), subtotal_raw)

        discount = discount_raw.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
        tax = ((subtotal_raw - discount) * self._tax_rate).quantize(
            _TWO_PLACES, rounding=ROUND_HALF_UP
        )
        subtotal = subtotal_raw.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
        total = (subtotal_raw - discount + tax).quantize(
            _TWO_PLACES, rounding=ROUND_HALF_UP
        )

        return {
            "subtotal": subtotal,
            "discount": discount,
            "tax": tax,
            "total": total,
        }
