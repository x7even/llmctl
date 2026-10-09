from decimal import Decimal, ROUND_HALF_UP
from typing import Optional


class Cart:
    def __init__(self, tax_rate: str | Decimal = "0") -> None:
        if isinstance(tax_rate, str):
            tax_rate = Decimal(tax_rate)
        elif not isinstance(tax_rate, Decimal):
            tax_rate = Decimal(str(tax_rate))
        
        if tax_rate < Decimal("0") or tax_rate > Decimal("1"):
            raise ValueError("tax_rate must be between 0 and 1 inclusive")
        
        self._tax_rate = tax_rate
        self._items: dict[str, tuple[Decimal, int]] = {}  # sku -> (price, quantity)
        self._coupon: Optional[str] = None

    def add_item(self, sku: str, price: str | Decimal, qty: int = 1) -> None:
        if not isinstance(qty, int) or qty < 1:
            raise ValueError("qty must be an int >= 1")
        
        if isinstance(price, str):
            price = Decimal(price)
        elif not isinstance(price, Decimal):
            price = Decimal(str(price))
        
        if price < Decimal("0"):
            raise ValueError("price must be >= 0")
        
        if sku in self._items:
            existing_price, existing_qty = self._items[sku]
            if existing_price != price:
                raise ValueError("price differs from existing price for this SKU")
            self._items[sku] = (existing_price, existing_qty + qty)
        else:
            self._items[sku] = (price, qty)

    def remove_item(self, sku: str, qty: Optional[int] = None) -> None:
        if sku not in self._items:
            raise KeyError(f"SKU '{sku}' not in cart")
        
        current_price, current_qty = self._items[sku]
        
        if qty is None:
            # Remove entire line
            del self._items[sku]
        else:
            if not isinstance(qty, int) or qty < 1:
                raise ValueError("qty must be >= 1")
            if qty > current_qty:
                raise ValueError("qty cannot exceed quantity in cart")
            new_qty = current_qty - qty
            if new_qty == 0:
                del self._items[sku]
            else:
                self._items[sku] = (current_price, new_qty)

    def apply_coupon(self, code: str) -> None:
        if code not in ("SAVE10", "FIVEOFF"):
            raise ValueError(f"Invalid coupon code: {code}")
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
            discount = discount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        elif self._coupon == "FIVEOFF":
            discount = Decimal("5.00")
            if discount > subtotal:
                discount = subtotal
            discount = discount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        # Calculate tax
        taxable_amount = subtotal - discount
        tax = taxable_amount * self._tax_rate
        tax = tax.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        # Calculate total
        total = subtotal - discount + tax
        total = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        # Ensure all values are properly quantized
        subtotal = subtotal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        discount = discount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        tax = tax.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        return {
            "subtotal": subtotal,
            "discount": discount,
            "tax": tax,
            "total": total,
        }
