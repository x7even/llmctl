"""Simple online-shop shopping cart with tax and coupon support."""

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Optional


_TWO_PLACES = Decimal("0.01")


def _to_decimal(value: str | Decimal) -> Decimal:
    """Convert a str or Decimal to Decimal, raising ValueError on bad input."""
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Cannot convert {value!r} to Decimal") from exc


def _round_cents(value: Decimal) -> Decimal:
    return value.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


class Cart:
    """A shopping cart that tracks line items, a single coupon, and tax."""

    _VALID_COUPONS = frozenset({"SAVE10", "FIVEOFF"})

    def __init__(self, tax_rate: str | Decimal = "0") -> None:
        rate = _to_decimal(tax_rate)
        if rate < 0 or rate > 1:
            raise ValueError(
                f"tax_rate must be between 0 and 1 inclusive, got {rate}"
            )
        self._tax_rate: Decimal = rate
        # sku -> (unit_price: Decimal, quantity: int)
        self._items: dict[str, tuple[Decimal, int]] = {}
        self._coupon: Optional[str] = None

    # ------------------------------------------------------------------
    # Item management
    # ------------------------------------------------------------------

    def add_item(self, sku: str, price: str | Decimal, qty: int = 1) -> None:
        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
            raise ValueError(f"qty must be an int >= 1, got {qty!r}")

        unit_price = _to_decimal(price)
        if unit_price < 0:
            raise ValueError(f"price must be >= 0, got {unit_price}")

        if sku in self._items:
            existing_price, existing_qty = self._items[sku]
            if existing_price != unit_price:
                raise ValueError(
                    f"SKU {sku!r} already in cart at price {existing_price}; "
                    f"cannot add at price {unit_price}"
                )
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
            raise ValueError(f"qty must be an int >= 1, got {qty!r}")

        _, current_qty = self._items[sku]
        if qty > current_qty:
            raise ValueError(
                f"Cannot remove {qty} units of {sku!r}; only {current_qty} in cart"
            )

        new_qty = current_qty - qty
        if new_qty == 0:
            del self._items[sku]
        else:
            self._items[sku] = (self._items[sku][0], new_qty)

    # ------------------------------------------------------------------
    # Coupons
    # ------------------------------------------------------------------

    def apply_coupon(self, code: str) -> None:
        if code not in self._VALID_COUPONS:
            raise ValueError(f"Unknown coupon code: {code!r}")
        self._coupon = code

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def item_count(self) -> int:
        return sum(qty for _, qty in self._items.values())

    def summary(self) -> dict[str, Decimal]:
        # Subtotal
        subtotal_raw = sum(
            (price * qty for price, qty in self._items.values()),
            Decimal("0"),
        )
        subtotal = _round_cents(subtotal_raw)

        # Discount
        if self._coupon == "SAVE10":
            discount_raw = subtotal * Decimal("0.10")
        elif self._coupon == "FIVEOFF":
            discount_raw = min(Decimal("5.00"), subtotal)
        else:
            discount_raw = Decimal("0")
        discount = _round_cents(discount_raw)

        # Tax
        taxable = subtotal - discount
        tax = _round_cents(taxable * self._tax_rate)

        # Total
        total = _round_cents(subtotal - discount + tax)

        return {
            "subtotal": subtotal,
            "discount": discount,
            "tax": tax,
            "total": total,
        }
