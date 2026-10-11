from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_CENT = Decimal("0.01")
_ZERO = Decimal("0.00")
_SAVE10_RATE = Decimal("0.10")
_FIVEOFF_AMOUNT = Decimal("5.00")


class Cart:
    def __init__(self, tax_rate: str | Decimal = "0") -> None:
        self._tax_rate = self._to_decimal(tax_rate, "tax_rate")
        if not (Decimal(0) <= self._tax_rate <= Decimal(1)):
            raise ValueError("tax_rate must be between 0 and 1")
        if self._tax_rate == 0:
            self._tax_rate = _ZERO

        self._lines: dict[str, tuple[Decimal, int]] = {}
        self._coupon: str | None = None

    @staticmethod
    def _to_decimal(value: str | Decimal, name: str) -> Decimal:
        if isinstance(value, Decimal):
            result = value
        elif isinstance(value, str):
            try:
                result = Decimal(value)
            except InvalidOperation:
                raise ValueError(f"{name} must be a valid decimal") from None
        elif isinstance(value, bool):
            raise ValueError(f"{name} must be a string or Decimal")
        elif isinstance(value, int):
            result = Decimal(value)
        elif isinstance(value, float):
            result = Decimal(str(value))
        else:
            raise ValueError(f"{name} must be a string or Decimal")

        if not result.is_finite():
            raise ValueError(f"{name} must be finite")

        return result

    @staticmethod
    def _round(value: Decimal) -> Decimal:
        rounded = value.quantize(_CENT, rounding=ROUND_HALF_UP)
        return _ZERO if rounded == 0 else rounded

    def add_item(self, sku: str, price: str | Decimal, qty: int = 1) -> None:
        if isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:
            raise ValueError("qty must be an integer >= 1")

        unit_price = self._to_decimal(price, "price")
        if unit_price < 0:
            raise ValueError("price must be >= 0")
        if unit_price == 0:
            unit_price = _ZERO

        existing = self._lines.get(sku)
        if existing is None:
            self._lines[sku] = (unit_price, qty)
            return

        existing_price, existing_qty = existing
        if existing_price != unit_price:
            raise ValueError("price for SKU does not match existing line")

        self._lines[sku] = (existing_price, existing_qty + qty)

    def remove_item(self, sku: str, qty: int | None = None) -> None:
        if sku not in self._lines:
            raise KeyError(sku)

        if qty is None:
            del self._lines[sku]
            return

        if isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:
            raise ValueError("qty must be an integer >= 1")

        price, current_qty = self._lines[sku]
        if qty > current_qty:
            raise ValueError("qty cannot exceed quantity in cart")

        if qty == current_qty:
            del self._lines[sku]
        else:
            self._lines[sku] = (price, current_qty - qty)

    def apply_coupon(self, code: str) -> None:
        if code not in ("SAVE10", "FIVEOFF"):
            raise ValueError("unknown coupon code")
        self._coupon = code

    def item_count(self) -> int:
        return sum(qty for _, qty in self._lines.values())

    def summary(self) -> dict[str, Decimal]:
        exact_subtotal = sum(
            (price * qty for price, qty in self._lines.values()),
            Decimal(0),
        )
        subtotal = self._round(exact_subtotal)

        if self._coupon == "SAVE10":
            discount = self._round(subtotal * _SAVE10_RATE)
        elif self._coupon == "FIVEOFF":
            discount = self._round(min(_FIVEOFF_AMOUNT, subtotal))
        else:
            discount = _ZERO

        taxable = subtotal - discount
        if taxable < 0:
            taxable = Decimal(0)

        tax = self._round(taxable * self._tax_rate)
        total = self._round(subtotal - discount + tax)

        return {
            "subtotal": subtotal,
            "discount": discount,
            "tax": tax,
            "total": total,
        }
