from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

_CENT = Decimal("0.01")
_ZERO = Decimal("0.00")
_FIVEOFF_AMOUNT = Decimal("5.00")
_SAVE10_RATE = Decimal("0.10")


def _to_decimal(value: str | Decimal, *, field: str) -> Decimal:
    if isinstance(value, Decimal):
        dec = value
    elif isinstance(value, str):
        try:
            dec = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError(f"Invalid {field}: {value!r}") from exc
    else:
        try:
            dec = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid {field}: {value!r}") from exc

    if not dec.is_finite():
        raise ValueError(f"Invalid {field}: {value!r}")
    return dec


def _round_cents(value: Decimal) -> Decimal:
    rounded = value.quantize(_CENT, rounding=ROUND_HALF_UP)
    if rounded == 0:
        return _ZERO
    return rounded


class Cart:
    def __init__(self, tax_rate: str | Decimal = "0") -> None:
        rate = _to_decimal(tax_rate, field="tax_rate")
        if not (Decimal("0") <= rate <= Decimal("1")):
            raise ValueError("tax_rate must be between 0 and 1 inclusive")
        if rate == 0:
            rate = Decimal("0")

        self._tax_rate = rate
        self._items: dict[str, tuple[Decimal, int]] = {}
        self._coupon: str | None = None

    def add_item(self, sku: str, price: str | Decimal, qty: int = 1) -> None:
        if not isinstance(qty, int) or qty < 1:
            raise ValueError("qty must be an int >= 1")

        unit_price = _to_decimal(price, field="price")
        if unit_price < 0:
            raise ValueError("price must be >= 0")
        if unit_price == 0:
            unit_price = Decimal("0")

        if sku in self._items:
            existing_price, existing_qty = self._items[sku]
            if existing_price != unit_price:
                raise ValueError("price for SKU differs from existing price")
            self._items[sku] = (existing_price, existing_qty + qty)
        else:
            self._items[sku] = (unit_price, qty)

    def remove_item(self, sku: str, qty: int | None = None) -> None:
        if sku not in self._items:
            raise KeyError(sku)

        if qty is None:
            del self._items[sku]
            return

        if not isinstance(qty, int) or qty < 1:
            raise ValueError("qty must be an int >= 1")

        existing_price, existing_qty = self._items[sku]
        if qty > existing_qty:
            raise ValueError("qty cannot exceed quantity in cart")

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
            raise ValueError("Unknown coupon code")

    def item_count(self) -> int:
        return sum(qty for _, qty in self._items.values())

    def summary(self) -> dict[str, Decimal]:
        subtotal_exact = Decimal("0")
        for price, qty in self._items.values():
            subtotal_exact += price * qty

        if self._coupon == "SAVE10":
            discount_exact = subtotal_exact * _SAVE10_RATE
        elif self._coupon == "FIVEOFF":
            discount_exact = min(_FIVEOFF_AMOUNT, subtotal_exact)
        else:
            discount_exact = Decimal("0")

        subtotal = _round_cents(subtotal_exact)
        discount = _round_cents(discount_exact)
        tax = _round_cents((subtotal - discount) * self._tax_rate)
        total = _round_cents(subtotal - discount + tax)

        return {
            "subtotal": subtotal,
            "discount": discount,
            "tax": tax,
            "total": total,
        }
