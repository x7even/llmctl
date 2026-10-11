from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

_CENT = Decimal("0.01")
_ZERO = Decimal("0")
_ONE = Decimal("1")
_SAVE10_RATE = Decimal("0.10")
_FIVEOFF_AMOUNT = Decimal("5.00")


class Cart:
    def __init__(self, tax_rate: str | Decimal = "0") -> None:
        self._tax_rate = self._as_decimal(tax_rate, "tax_rate")
        if not self._tax_rate.is_finite() or self._tax_rate < _ZERO or self._tax_rate > _ONE:
            raise ValueError("tax_rate must be between 0 and 1 inclusive")

        self._items: dict[str, tuple[Decimal, int]] = {}
        self._coupon: str | None = None

    @staticmethod
    def _as_decimal(value: object, name: str) -> Decimal:
        if isinstance(value, Decimal):
            return value
        if isinstance(value, bool):
            raise ValueError(f"{name} must be a decimal value")
        if isinstance(value, str):
            try:
                return Decimal(value)
            except (InvalidOperation, ValueError):
                raise ValueError(f"{name} must be a valid decimal") from None
        if isinstance(value, int):
            return Decimal(value)

        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError, OverflowError):
            raise ValueError(f"{name} must be a valid decimal") from None

    def add_item(self, sku: str, price: str | Decimal, qty: int = 1) -> None:
        if isinstance(qty, bool) or not isinstance(qty, int):
            raise ValueError("qty must be an integer >= 1")
        if qty < 1:
            raise ValueError("qty must be an integer >= 1")

        unit_price = self._as_decimal(price, "price")
        if not unit_price.is_finite() or unit_price < _ZERO:
            raise ValueError("price must be >= 0")

        if sku in self._items:
            existing_price, existing_qty = self._items[sku]
            if existing_price != unit_price:
                raise ValueError("price for existing SKU must not change")
            self._items[sku] = (existing_price, existing_qty + qty)
        else:
            self._items[sku] = (unit_price, qty)

    def remove_item(self, sku: str, qty: int | None = None) -> None:
        if sku not in self._items:
            raise KeyError(sku)

        if qty is None:
            del self._items[sku]
            return

        if isinstance(qty, bool) or not isinstance(qty, int):
            raise ValueError("qty must be an integer >= 1")
        if qty < 1:
            raise ValueError("qty must be an integer >= 1")

        price, current_qty = self._items[sku]
        if qty > current_qty:
            raise ValueError("qty cannot exceed quantity in cart")

        if qty == current_qty:
            del self._items[sku]
        else:
            self._items[sku] = (price, current_qty - qty)

    def apply_coupon(self, code: str) -> None:
        if not isinstance(code, str):
            raise ValueError("coupon code must be a string")

        if code == "SAVE10":
            self._coupon = code
        elif code == "FIVEOFF":
            self._coupon = code
        else:
            raise ValueError("unknown coupon code")

    def item_count(self) -> int:
        return sum(qty for _, qty in self._items.values())

    def summary(self) -> dict[str, Decimal]:
        raw_subtotal = sum((price * qty for price, qty in self._items.values()), _ZERO)
        subtotal = raw_subtotal.quantize(_CENT, rounding=ROUND_HALF_UP)

        discount = self._coupon_discount(subtotal)
        discount = discount.quantize(_CENT, rounding=ROUND_HALF_UP)

        taxable = subtotal - discount
        if taxable < _ZERO:
            taxable = _ZERO

        tax = (taxable * self._tax_rate).quantize(_CENT, rounding=ROUND_HALF_UP)
        total = (subtotal - discount + tax).quantize(_CENT, rounding=ROUND_HALF_UP)

        return {
            "subtotal": subtotal,
            "discount": discount,
            "tax": tax,
            "total": total,
        }

    def _coupon_discount(self, subtotal: Decimal) -> Decimal:
        if self._coupon == "SAVE10":
            return subtotal * _SAVE10_RATE
        if self._coupon == "FIVEOFF":
            return min(_FIVEOFF_AMOUNT, subtotal)
        return _ZERO
