from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Optional

# Ensure sufficient precision for monetary calculations
getcontext().prec = 28


def _to_decimal(value: str | Decimal) -> Decimal:
    """Convert a string or Decimal to Decimal."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _round_to_cents(value: Decimal) -> Decimal:
    """Round a Decimal to 2 decimal places using ROUND_HALF_UP."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class Cart:
    def __init__(self, tax_rate: str | Decimal = "0") -> None:
        rate = _to_decimal(tax_rate)
        if rate < Decimal("0") or rate > Decimal("1"):
            raise ValueError("tax_rate must be between 0 and 1 inclusive")
        self._tax_rate = rate
        # Dictionary mapping SKU -> (price, quantity)
        self._items: dict[str, tuple[Decimal, int]] = {}
        self._coupon: Optional[str] = None

    def add_item(self, sku: str, price: str | Decimal, qty: int = 1) -> None:
        if not isinstance(qty, int) or qty < 1:
            raise ValueError("qty must be an int >= 1")
        price_dec = _to_decimal(price)
        if price_dec < Decimal("0"):
            raise ValueError("price must be >= 0")

        if sku in self._items:
            existing_price, existing_qty = self._items[sku]
            if existing_price != price_dec:
                raise ValueError("price differs from existing price for this SKU")
            self._items[sku] = (existing_price, existing_qty + qty)
        else:
            self._items[sku] = (price_dec, qty)

    def remove_item(self, sku: str, qty: int | None = None) -> None:
        if sku not in self._items:
            raise KeyError(f"SKU '{sku}' not in cart")
        existing_price, existing_qty = self._items[sku]

        if qty is None:
            # Remove the entire line
            del self._items[sku]
        else:
            if not isinstance(qty, int) or qty < 1:
                raise ValueError("qty must be an int >= 1")
            if qty > existing_qty:
                raise ValueError("qty is more than the quantity in the cart")
            new_qty = existing_qty - qty
            if new_qty == 0:
                del self._items[sku]
            else:
                self._items[sku] = (existing_price, new_qty)

    def apply_coupon(self, code: str) -> None:
        valid_coupons = {"SAVE10", "FIVEOFF"}
        if code not in valid_coupons:
            raise ValueError(f"Invalid coupon code: {code}")
        self._coupon = code

    def item_count(self) -> int:
        return sum(qty for _, qty in self._items.values())

    def summary(self) -> dict[str, Decimal]:
        # Calculate subtotal
        subtotal = Decimal("0")
        for price, qty in self._items.values():
            subtotal += price * Decimal(qty)
        subtotal = _round_to_cents(subtotal)

        # Calculate discount
        discount = Decimal("0")
        if self._coupon == "SAVE10":
            discount = subtotal * Decimal("0.10")
        elif self._coupon == "FIVEOFF":
            discount = Decimal("5.00")
            if discount > subtotal:
                discount = subtotal
        discount = _round_to_cents(discount)

        # Calculate tax
        taxable = subtotal - discount
        tax = taxable * self._tax_rate
        tax = _round_to_cents(tax)

        # Calculate total
        total = subtotal - discount + tax
        total = _round_to_cents(total)

        return {
            "subtotal": subtotal,
            "discount": discount,
            "tax": tax,
            "total": total,
        }
