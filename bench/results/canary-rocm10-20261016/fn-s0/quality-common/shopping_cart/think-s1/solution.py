"""Simple online-shop shopping cart with Decimal money and coupon support."""

from decimal import Decimal, ROUND_HALF_UP

_CENTS = Decimal("0.01")
_ZERO = Decimal("0.00")


def _to_decimal(value: str | Decimal) -> Decimal:
    return Decimal(value) if isinstance(value, str) else value


def _round_cents(value: Decimal) -> Decimal:
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


class Cart:
    """A shopping cart that tracks line-items, a single coupon, and tax."""

    def __init__(self, tax_rate: str | Decimal = "0") -> None:
        rate = _to_decimal(tax_rate)
        if rate < 0 or rate > 1:
            raise ValueError("tax_rate must be between 0 and 1 inclusive")
        self._tax_rate: Decimal = rate
        # sku -> (unit_price, quantity)
        self._items: dict[str, tuple[Decimal, int]] = {}
        self._coupon: str | None = None

    # ------------------------------------------------------------------
    # Item management
    # ------------------------------------------------------------------

    def add_item(self, sku: str, price: str | Decimal, qty: int = 1) -> None:
        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
            raise ValueError("qty must be an int >= 1")

        price = _to_decimal(price)
        if price < 0:
            raise ValueError("price must be >= 0")

        if sku in self._items:
            existing_price, existing_qty = self._items[sku]
            if price != existing_price:
                raise ValueError(
                    f"price mismatch for SKU {sku!r}: "
                    f"cart has {existing_price}, got {price}"
                )
            self._items[sku] = (existing_price, existing_qty + qty)
        else:
            self._items[sku] = (price, qty)

    def remove_item(self, sku: str, qty: int | None = None) -> None:
        if sku not in self._items:
            raise KeyError(sku)

        if qty is None:
            del self._items[sku]
            return

        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
            raise ValueError("qty must be >= 1")

        current_price, current_qty = self._items[sku]
        if qty > current_qty:
            raise ValueError(
                f"qty {qty} exceeds quantity in cart ({current_qty})"
            )

        remaining = current_qty - qty
        if remaining == 0:
            del self._items[sku]
        else:
            self._items[sku] = (current_price, remaining)

    # ------------------------------------------------------------------
    # Coupons
    # ------------------------------------------------------------------

    def apply_coupon(self, code: str) -> None:
        if code in ("SAVE10", "FIVEOFF"):
            self._coupon = code
        else:
            raise ValueError(f"Unknown coupon code: {code!r}")

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def item_count(self) -> int:
        return sum(qty for _, qty in self._items.values())

    def summary(self) -> dict[str, Decimal]:
        # --- subtotal (exact) ---
        subtotal = sum(
            (price * qty for price, qty in self._items.values()),
            _ZERO,
        )

        # --- discount (exact, then rounded) ---
        if self._coupon == "SAVE10":
            discount = subtotal * Decimal("0.10")
        elif self._coupon == "FIVEOFF":
            discount = min(Decimal("5.00"), subtotal)
        else:
            discount = _ZERO

        discount = _round_cents(discount)

        # --- tax ---
        tax = _round_cents((subtotal - discount) * self._tax_rate)

        # --- total ---
        total = _round_cents(subtotal - discount + tax)

        return {
            "subtotal": _round_cents(subtotal),
            "discount": discount,
            "tax": tax,
            "total": total,
        }
