"""Simple shopping-cart module using only the standard library."""

from decimal import Decimal, ROUND_HALF_UP

_CENTS = Decimal("0.01")


class Cart:
    """A minimal online-shop shopping cart with tax and coupon support."""

    def __init__(self, tax_rate: str | Decimal = "0") -> None:
        rate = Decimal(tax_rate) if isinstance(tax_rate, str) else tax_rate
        if rate < Decimal("0") or rate > Decimal("1"):
            raise ValueError("tax_rate must be between 0 and 1 inclusive")
        self._tax_rate: Decimal = rate
        # sku -> (unit_price, quantity)
        self._items: dict[str, tuple[Decimal, int]] = {}
        self._coupon: str | None = None

    # ------------------------------------------------------------------
    # Item management
    # ------------------------------------------------------------------

    def add_item(self, sku: str, price: str | Decimal, qty: int = 1) -> None:
        if isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:
            raise ValueError("qty must be an int >= 1")
        p = Decimal(price) if isinstance(price, str) else price
        if p < Decimal("0"):
            raise ValueError("price must be >= 0")

        if sku in self._items:
            existing_price, existing_qty = self._items[sku]
            if existing_price != p:
                raise ValueError(
                    f"price mismatch for SKU {sku!r}: "
                    f"existing {existing_price}, requested {p}"
                )
            self._items[sku] = (existing_price, existing_qty + qty)
        else:
            self._items[sku] = (p, qty)

    def remove_item(self, sku: str, qty: int | None = None) -> None:
        if sku not in self._items:
            raise KeyError(sku)

        current_price, current_qty = self._items[sku]

        if qty is None:
            del self._items[sku]
            return

        if isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:
            raise ValueError("qty must be >= 1")
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
        if code == "SAVE10" or code == "FIVEOFF":
            self._coupon = code
        else:
            raise ValueError(f"Invalid coupon code: {code!r}")

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def item_count(self) -> int:
        return sum(qty for _, qty in self._items.values())

    def summary(self) -> dict[str, Decimal]:
        # --- subtotal ---
        subtotal = sum(
            (price * qty for price, qty in self._items.values()),
            Decimal("0"),
        ).quantize(_CENTS, rounding=ROUND_HALF_UP)

        # --- discount ---
        discount = Decimal("0.00")
        if self._coupon == "SAVE10":
            discount = (subtotal * Decimal("0.10")).quantize(
                _CENTS, rounding=ROUND_HALF_UP
            )
        elif self._coupon == "FIVEOFF":
            discount = Decimal("5.00")
            if discount > subtotal:
                discount = subtotal
            discount = discount.quantize(_CENTS, rounding=ROUND_HALF_UP)

        # --- tax ---
        taxable = subtotal - discount
        tax = (taxable * self._tax_rate).quantize(
            _CENTS, rounding=ROUND_HALF_UP
        )

        # --- total ---
        total = (subtotal - discount + tax).quantize(
            _CENTS, rounding=ROUND_HALF_UP
        )

        return {
            "subtotal": subtotal,
            "discount": discount,
            "tax": tax,
            "total": total,
        }
