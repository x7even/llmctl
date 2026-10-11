from decimal import Decimal, ROUND_HALF_UP
from typing import Optional


class Cart:
    def __init__(self, tax_rate: str | Decimal = "0") -> None:
        if isinstance(tax_rate, str):
            tax_rate = Decimal(tax_rate)
        if tax_rate < Decimal("0") or tax_rate > Decimal("1"):
            raise ValueError("tax_rate must be between 0 and 1 inclusive")
        self._tax_rate = tax_rate
        self._items: dict[str, tuple[Decimal, int]] = {}  # sku -> (price, qty)
        self._coupon: Optional[str] = None

    def add_item(self, sku: str, price: str | Decimal, qty: int = 1) -> None:
        if not isinstance(qty, int) or qty < 1:
            raise ValueError("qty must be an int >= 1")
        if isinstance(price, str):
            price = Decimal(price)
        if price < Decimal("0"):
            raise ValueError("price must be >= 0")
        if sku in self._items:
            existing_price, existing_qty = self._items[sku]
            if existing_price != price:
                raise ValueError("price mismatch for existing SKU")
            self._items[sku] = (existing_price, existing_qty + qty)
        else:
            self._items[sku] = (price, qty)

    def remove_item(self, sku: str, qty: int | None = None) -> None:
        if sku not in self._items:
            raise KeyError(sku)
        existing_price, existing_qty = self._items[sku]
        if qty is None:
            del self._items[sku]
        else:
            if not isinstance(qty, int) or qty < 1:
                raise ValueError("qty must be >= 1")
            if qty > existing_qty:
                raise ValueError("qty exceeds quantity in cart")
            new_qty = existing_qty - qty
            if new_qty == 0:
                del self._items[sku]
            else:
                self._items[sku] = (existing_price, new_qty)

    def apply_coupon(self, code: str) -> None:
        if code not in ("SAVE10", "FIVEOFF"):
            raise ValueError("Invalid coupon code")
        self._coupon = code

    def item_count(self) -> int:
        return sum(qty for _, qty in self._items.values())

    def summary(self) -> dict[str, Decimal]:
        # Calculate subtotal
        subtotal = Decimal("0")
        for price, qty in self._items.values():
            subtotal += price * Decimal(qty)

        # Calculate discount
        discount = Decimal("0")
        if self._coupon == "SAVE10":
            discount = subtotal * Decimal("0.10")
        elif self._coupon == "FIVEOFF":
            discount = Decimal("5.00")
            if discount > subtotal:
                discount = subtotal

        # Round discount to cents with ROUND_HALF_UP
        discount = discount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Calculate tax
        taxable = subtotal - discount
        tax = taxable * self._tax_rate
        tax = tax.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Calculate total
        total = subtotal - discount + tax
        total = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Round subtotal to cents as well
        subtotal = subtotal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        return {
            "subtotal": subtotal,
            "discount": discount,
            "tax": tax,
            "total": total,
        }
