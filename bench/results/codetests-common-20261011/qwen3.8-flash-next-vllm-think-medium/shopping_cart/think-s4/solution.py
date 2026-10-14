"""Simple online-shop shopping cart using decimal arithmetic."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

_CENT = Decimal("0.01")


def _to_decimal(value: str | Decimal) -> Decimal:
    """Convert a str or Decimal to Decimal."""
    if isinstance(value, Decimal):
        return value
    return Decimal(value)


def _round(value: Decimal) -> Decimal:
    """Round a Decimal to 2 decimal places using ROUND_HALF_UP."""
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


class Cart:
    """A shopping cart that tracks items, coupons, and computes totals."""

    def __init__(self, tax_rate: str | Decimal = "0") -> None:
        rate = _to_decimal(tax_rate)
        if rate < Decimal("0") or rate > Decimal("1"):
            raise ValueError(
                f"tax_rate must be between 0 and 1 inclusive, got {rate}"
            )
        self._tax_rate: Decimal = rate
        # sku -> (unit_price, quantity)
        self._items: dict[str, tuple[Decimal, int]] = {}
        self._coupon: Optional[str] = None

    # ------------------------------------------------------------------
    # Item management
    # ------------------------------------------------------------------

    def add_item(self, sku: str, price: str | Decimal, qty: int = 1) -> None:
        if not isinstance(qty, int) or qty < 1:
            raise ValueError(f"qty must be an int >= 1, got {qty!r}")
        unit_price = _to_decimal(price)
        if unit_price < Decimal("0"):
            raise ValueError(f"price must be >= 0, got {unit_price}")

        if sku in self._items:
            existing_price, existing_qty = self._items[sku]
            if existing_price != unit_price:
                raise ValueError(
                    f"SKU {sku!r} already in cart at price {existing_price}, "
                    f"cannot add at price {unit_price}"
                )
            self._items[sku] = (existing_price, existing_qty + qty)
        else:
            self._items[sku] = (unit_price, qty)

    def remove_item(self, sku: str, qty: int | None = None) -> None:
        if sku not in self._items:
            raise KeyError(sku)

        existing_price, existing_qty = self._items[sku]

        if qty is None:
            del self._items[sku]
            return

        if not isinstance(qty, int) or qty < 1:
            raise ValueError(f"qty must be an int >= 1, got {qty!r}")
        if qty > existing_qty:
            raise ValueError(
                f"Cannot remove {qty} units of {sku!r}; only {existing_qty} in cart"
            )

        remaining = existing_qty - qty
        if remaining == 0:
            del self._items[sku]
        else:
            self._items[sku] = (existing_price, remaining)

    # ------------------------------------------------------------------
    # Coupons
    # ------------------------------------------------------------------

    def apply_coupon(self, code: str) -> None:
        if code not in ("SAVE10", "FIVEOFF"):
            raise ValueError(f"Unknown coupon code: {code!r}")
        self._coupon = code

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def item_count(self) -> int:
        return sum(qty for _, qty in self._items.values())

    def summary(self) -> dict[str, Decimal]:
        # Subtotal
        subtotal = Decimal("0")
        for unit_price, qty in self._items.values():
            subtotal += unit_price * qty
        subtotal = _round(subtotal)

        # Discount
        if self._coupon == "SAVE10":
            discount = _round(subtotal * Decimal("0.10"))
        elif self._coupon == "FIVEOFF":
            discount = _round(min(Decimal("5.00"), subtotal))
        else:
            discount = Decimal("0.00")

        # Tax
        taxable = subtotal - discount
        tax = _round(taxable * self._tax_rate)

        # Total
        total = _round(subtotal - discount + tax)

        return {
            "subtotal": subtotal,
            "discount": discount,
            "tax": tax,
            "total": total,
        }
