"""Simple online-shop shopping cart using Decimal for all monetary values."""

from decimal import Decimal, ROUND_HALF_UP

_TWO_PLACES = Decimal("0.01")


class Cart:
    def __init__(self, tax_rate: str | Decimal = "0") -> None:
        rate = Decimal(tax_rate) if isinstance(tax_rate, str) else tax_rate
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
        p = Decimal(price) if isinstance(price, str) else price
        if p < 0:
            raise ValueError("price must be >= 0")

        if sku in self._items:
            existing_price, existing_qty = self._items[sku]
            if p != existing_price:
                raise ValueError(
                    f"price mismatch for SKU '{sku}': "
                    f"cart has {existing_price}, got {p}"
                )
            self._items[sku] = (existing_price, existing_qty + qty)
        else:
            self._items[sku] = (p, qty)

    def remove_item(self, sku: str, qty: int | None = None) -> None:
        if sku not in self._items:
            raise KeyError(sku)

        existing_price, existing_qty = self._items[sku]

        if qty is None:
            del self._items[sku]
            return

        if qty < 1:
            raise ValueError("qty must be >= 1")
        if qty > existing_qty:
            raise ValueError("qty exceeds quantity in cart")

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
        # Raw subtotal (exact arithmetic)
        subtotal_raw = sum(
            (price * qty for price, qty in self._items.values()),
            Decimal("0"),
        )

        # Raw discount from coupon
        if self._coupon == "SAVE10":
            discount_raw = subtotal_raw * Decimal("0.10")
        elif self._coupon == "FIVEOFF":
            discount_raw = min(Decimal("5.00"), subtotal_raw)
        else:
            discount_raw = Decimal("0")

        # Round to cents
        subtotal = subtotal_raw.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
        discount = discount_raw.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)

        # Tax on the discounted amount
        tax = ((subtotal - discount) * self._tax_rate).quantize(
            _TWO_PLACES, rounding=ROUND_HALF_UP
        )

        # Total (already exact to 2 dp since all components are)
        total = subtotal - discount + tax

        return {
            "subtotal": subtotal,
            "discount": discount,
            "tax": tax,
            "total": total,
        }
