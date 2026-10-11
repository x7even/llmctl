from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

__all__ = ["Cart"]

_CENT = Decimal("0.01")
_ZERO = Decimal("0")
_ONE = Decimal("1")
_FIVE_OFF = Decimal("5.00")
_SAVE10_RATE = Decimal("0.10")


class Cart:
    def __init__(self, tax_rate: str | Decimal = "0") -> None:
        self._tax_rate = self._parse_decimal(tax_rate, "tax_rate")
        if not self._tax_rate.is_finite() or not (_ZERO <= self._tax_rate <= _ONE):
            raise ValueError("tax_rate must be between 0 and 1 inclusive")

        self._items: dict[str, tuple[Decimal, int]] = {}
        self._coupon: str | None = None

    @staticmethod
    def _parse_decimal(value, name: str) -> Decimal:
        if isinstance(value, Decimal):
            result = value
        elif isinstance(value, str):
            try:
                result = Decimal(value)
            except InvalidOperation:
                raise ValueError(f"{name} must be a valid decimal") from None
        elif isinstance(value, int) and not isinstance(value, bool):
            result = Decimal(value)
        else:
            raise ValueError(f"{name} must be a str or Decimal")

        if not result.is_finite():
            raise ValueError(f"{name} must be finite")

        return result

    @staticmethod
    def _validate_qty(qty: int) -> int:
        if isinstance(qty, bool) or not isinstance(qty, int):
            raise ValueError("qty must be an int")
        if qty < 1:
            raise ValueError("qty must be at least 1")
        return qty

    @staticmethod
    def _quantize(value: Decimal) -> Decimal:
        return value.quantize(_CENT, rounding=ROUND_HALF_UP)

    def add_item(self, sku: str, price: str | Decimal, qty: int = 1) -> None:
        qty = self._validate_qty(qty)
        unit_price = self._parse_decimal(price, "price")

        if unit_price < _ZERO:
            raise ValueError("price must be non-negative")

        if sku in self._items:
            existing_price, existing_qty = self._items[sku]
            if existing_price != unit_price:
                raise ValueError("price for this SKU has changed")
            self._items[sku] = (existing_price, existing_qty + qty)
        else:
            self._items[sku] = (unit_price, qty)

    def remove_item(self, sku: str, qty: int | None = None) -> None:
        if sku not in self._items:
            raise KeyError(sku)

        if qty is None:
            del self._items[sku]
            return

        qty = self._validate_qty(qty)
        price, current_qty = self._items[sku]

        if qty > current_qty:
            raise ValueError("qty cannot exceed the quantity in the cart")

        remaining_qty = current_qty - qty
        if remaining_qty == 0:
            del self._items[sku]
        else:
            self._items[sku] = (price, remaining_qty)

    def apply_coupon(self, code: str) -> None:
        if not isinstance(code, str):
            raise ValueError("coupon code must be a str")
        if code not in ("SAVE10", "FIVEOFF"):
            raise ValueError("unknown coupon code")

        self._coupon = code

    def item_count(self) -> int:
        return sum(qty for _, qty in self._items.values())

    def _coupon_discount(self, subtotal: Decimal) -> Decimal:
        if self._coupon == "SAVE10":
            return subtotal * _SAVE10_RATE
        if self._coupon == "FIVEOFF":
            return min(_FIVE_OFF, subtotal)
        return _ZERO

    def summary(self) -> dict[str, Decimal]:
        exact_subtotal = sum(
            (price * qty for price, qty in self._items.values()),
            _ZERO,
        )

        subtotal = self._quantize(exact_subtotal)
        discount = self._quantize(self._coupon_discount(subtotal))
        tax = self._quantize((subtotal - discount) * self._tax_rate)
        total = self._quantize(subtotal - discount + tax)

        return {
            "subtotal": subtotal,
            "discount": discount,
            "tax": tax,
            "total": total,
        }
