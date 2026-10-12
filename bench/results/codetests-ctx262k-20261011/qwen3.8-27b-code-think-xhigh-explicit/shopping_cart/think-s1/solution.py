from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

_CENT = Decimal("0.01")
_FIVE_OFF = Decimal("5.00")
_SAVE10 = Decimal("0.10")
_VALID_COUPONS = {"SAVE10", "FIVEOFF"}


class Cart:
    def __init__(self, tax_rate: str | Decimal = "0") -> None:
        rate = self._to_decimal(tax_rate, "tax_rate")
        if rate < 0 or rate > 1:
            raise ValueError("tax_rate must be between 0 and 1 inclusive")

        self._tax_rate = rate
        self._items: dict[str, tuple[Decimal, int]] = {}
        self._coupon: str | None = None

    @staticmethod
    def _to_decimal(value: str | Decimal | int, name: str) -> Decimal:
        if isinstance(value, Decimal):
            result = value
        elif isinstance(value, str):
            try:
                result = Decimal(value)
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be a valid decimal") from exc
        elif isinstance(value, int) and not isinstance(value, bool):
            result = Decimal(value)
        else:
            raise ValueError(f"{name} must be a str, Decimal, or int")

        if result.is_nan() or result.is_infinite():
            raise ValueError(f"{name} must be a finite decimal")

        return result

    @staticmethod
    def _round(value: Decimal) -> Decimal:
        return value.quantize(_CENT, rounding=ROUND_HALF_UP)

    def add_item(self, sku: str, price: str | Decimal, qty: int = 1) -> None:
        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
            raise ValueError("qty must be an int >= 1")

        unit_price = self._to_decimal(price, "price")
        if unit_price < 0:
            raise ValueError("price must be >= 0")

        if sku in self._items:
            existing_price, existing_qty = self._items[sku]
            if existing_price != unit_price:
                raise ValueError("price for SKU already in cart differs")
            self._items[sku] = (existing_price, existing_qty + qty)
        else:
            self._items[sku] = (unit_price, qty)

    def remove_item(self, sku: str, qty: int | None = None) -> None:
        if sku not in self._items:
            raise KeyError(sku)

        if qty is None:
            del self._items[sku]
            return

        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
            raise ValueError("qty must be an int >= 1")

        _, current_qty = self._items[sku]
        if qty > current_qty:
            raise ValueError("qty cannot exceed the quantity in the cart")

        if qty == current_qty:
            del self._items[sku]
        else:
            price, _ = self._items[sku]
            self._items[sku] = (price, current_qty - qty)

    def apply_coupon(self, code: str) -> None:
        if not isinstance(code, str):
            raise ValueError("coupon code must be a string")
        if code not in _VALID_COUPONS:
            raise ValueError("unknown coupon code")
        self._coupon = code

    def item_count(self) -> int:
        return sum(qty for _, qty in self._items.values())

    def summary(self) -> dict[str, Decimal]:
        exact_subtotal = Decimal(0)
        for price, qty in self._items.values():
            exact_subtotal += price * qty

        subtotal = self._round(exact_subtotal)

        if self._coupon == "SAVE10":
            discount = self._round(subtotal * _SAVE10)
        elif self._coupon == "FIVEOFF":
            discount = self._round(min(_FIVE_OFF, subtotal))
        else:
            discount = Decimal("0.00")

        taxable = subtotal - discount
        if taxable < 0:
            taxable = Decimal("0.00")

        tax = self._round(taxable * self._tax_rate)
        total = self._round(subtotal - discount + tax)

        return {
            "subtotal": subtotal,
            "discount": discount,
            "tax": tax,
            "total": total,
        }
