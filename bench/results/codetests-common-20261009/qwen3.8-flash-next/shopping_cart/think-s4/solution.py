from __future__ import annotations

import numbers
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

TWO_PLACES = Decimal("0.01")
ZERO = Decimal("0.00")


def _to_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, bool):
        raise ValueError("value must be a finite decimal number")
    elif isinstance(value, str):
        try:
            result = Decimal(value)
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError("value must be a finite decimal number") from exc
    elif isinstance(value, float):
        try:
            result = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError("value must be a finite decimal number") from exc
    else:
        try:
            result = Decimal(value)
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError("value must be a finite decimal number") from exc

    if not result.is_finite():
        raise ValueError("value must be a finite decimal number")
    return result


def _quantize(value: Decimal) -> Decimal:
    if value.is_zero():
        return ZERO
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


class Cart:
    def __init__(self, tax_rate: str | Decimal = "0") -> None:
        rate = _to_decimal(tax_rate)
        if rate < Decimal(0) or rate > Decimal(1):
            raise ValueError("tax_rate must be between 0 and 1 inclusive")

        self._tax_rate = rate
        self._items: dict[str, tuple[Decimal, int]] = {}
        self._coupon: str | None = None

    def add_item(self, sku: str, price: str | Decimal, qty: int = 1) -> None:
        if isinstance(qty, bool) or not isinstance(qty, numbers.Integral) or qty < 1:
            raise ValueError("qty must be an integer >= 1")
        qty = int(qty)

        unit_price = _to_decimal(price)
        if unit_price < 0:
            raise ValueError("price must be >= 0")

        existing = self._items.get(sku)
        if existing is not None:
            existing_price, existing_qty = existing
            if existing_price != unit_price:
                raise ValueError("price mismatch for SKU")
            self._items[sku] = (existing_price, existing_qty + qty)
        else:
            self._items[sku] = (unit_price, qty)

    def remove_item(self, sku: str, qty: int | None = None) -> None:
        if sku not in self._items:
            raise KeyError(sku)

        if qty is None:
            del self._items[sku]
            return

        if isinstance(qty, bool) or not isinstance(qty, numbers.Integral) or qty < 1:
            raise ValueError("qty must be an integer >= 1")
        qty = int(qty)

        unit_price, current_qty = self._items[sku]
        if qty > current_qty:
            raise ValueError("qty is more than the quantity in the cart")

        if qty == current_qty:
            del self._items[sku]
        else:
            self._items[sku] = (unit_price, current_qty - qty)

    def apply_coupon(self, code: str) -> None:
        if code == "SAVE10" or code == "FIVEOFF":
            self._coupon = code
        else:
            raise ValueError("unknown coupon code")

    def item_count(self) -> int:
        return sum(qty for _, qty in self._items.values())

    def summary(self) -> dict[str, Decimal]:
        subtotal = sum(
            (unit_price * Decimal(qty) for unit_price, qty in self._items.values()),
            ZERO,
        )
        subtotal = _quantize(subtotal)

        if self._coupon == "SAVE10":
            discount = _quantize(subtotal * Decimal("0.10"))
        elif self._coupon == "FIVEOFF":
            discount = _quantize(min(Decimal("5.00"), subtotal))
        else:
            discount = ZERO

        taxable = subtotal - discount
        tax = _quantize(taxable * self._tax_rate)
        total = _quantize(taxable + tax)

        return {
            "subtotal": subtotal,
            "discount": discount,
            "tax": tax,
            "total": total,
        }
