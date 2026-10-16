"""Simple shopping-cart module using only the standard library."""

from decimal import Decimal, ROUND_HALF_UP

_TWO_PLACES = Decimal("0.01")


class Cart:
    """A minimal online-shop shopping cart with coupon and tax support."""

    def __init__(self, tax_rate: str | Decimal = "0") -> None:
        rate = Decimal(tax_rate) if isinstance(tax_rate, str) else tax_rate
        if not (Decimal("0") <= rate <= Decimal("1")):
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
        unit_price = Decimal(price) if isinstance(price, str) else price
        if unit_price < 0:
            raise ValueError("price must be >= 0")

        if sku in self._items:
            existing_price, existing_qty = self._items[sku]
            if existing_price != unit_price:
                raise ValueError(
                    f"price mismatch for SKU '{sku}': "
                    f"existing {existing_price}, new {unit_price}"
                )
            self._items[sku] = (existing_price, existing_qty + qty)
        else:
            self._items[sku] = (unit_price, qty)

    def remove_item(self, sku: str, qty: int | None = None) -> None:
        if sku not in self._items:
            raise KeyError(sku)

        current_qty = self._items[sku][1]

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
            self._items[sku] = (self._items[sku][0], remaining)

    # ------------------------------------------------------------------
    # Coupons
    # ------------------------------------------------------------------

    def apply_coupon(self, code: str) -> None:
        if code not in ("SAVE10", "FIVEOFF"):
            raise ValueError(f"Invalid coupon code: {code!r}")
        self._coupon = code

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def item_count(self) -> int:
        return sum(qty for _, qty in self._items.values())

    def summary(self) -> dict[str, Decimal]:
        # Subtotal
        subtotal = sum(
            (price * qty for price, qty in self._items.values()),
            Decimal("0"),
        ).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)

        # Discount
        if self._coupon == "SAVE10":
            discount = (subtotal * Decimal("0.10")).quantize(
                _TWO_PLACES, rounding=ROUND_HALF_UP
            )
        elif self._coupon == "FIVEOFF":
            discount = min(Decimal("5.00"), subtotal).quantize(
                _TWO_PLACES, rounding=ROUND_HALF_UP
            )
        else:
            discount = Decimal("0.00")

        # Tax
        taxable = subtotal - discount
        tax = (taxable * self._tax_rate).quantize(
            _TWO_PLACES, rounding=ROUND_HALF_UP
        )

        # Total
        total = (subtotal - discount + tax).quantize(
            _TWO_PLACES, rounding=ROUND_HALF_UP
        )

        return {
            "subtotal": subtotal,
            "discount": discount,
            "tax": tax,
            "total": total,
        }
