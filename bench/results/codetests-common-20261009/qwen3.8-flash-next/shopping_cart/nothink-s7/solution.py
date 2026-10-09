from decimal import Decimal, ROUND_HALF_UP
from typing import Optional


class Cart:
    def __init__(self, tax_rate: str | Decimal = "0") -> None:
        # Convert tax_rate to Decimal
        if isinstance(tax_rate, str):
            self._tax_rate = Decimal(tax_rate)
        else:
            self._tax_rate = tax_rate
        
        # Validate tax_rate is between 0 and 1 inclusive
        if self._tax_rate < Decimal("0") or self._tax_rate > Decimal("1"):
            raise ValueError("tax_rate must be between 0 and 1 inclusive")
        
        # Dictionary to store cart items: {sku: (price, quantity)}
        self._items: dict[str, tuple[Decimal, int]] = {}
        
        # Currently applied coupon code (None if no coupon)
        self._coupon: Optional[str] = None
    
    def add_item(self, sku: str, price: str | Decimal, qty: int = 1) -> None:
        # Validate qty
        if not isinstance(qty, int) or qty < 1:
            raise ValueError("qty must be an integer >= 1")
        
        # Convert price to Decimal
        if isinstance(price, str):
            price = Decimal(price)
        
        # Validate price
        if price < Decimal("0"):
            raise ValueError("price must be >= 0")
        
        # Check if sku already exists
        if sku in self._items:
            existing_price, existing_qty = self._items[sku]
            # If price differs, raise ValueError
            if existing_price != price:
                raise ValueError("Price for this SKU differs from existing price in cart")
            # Add to existing quantity
            self._items[sku] = (existing_price, existing_qty + qty)
        else:
            # Add new item
            self._items[sku] = (price, qty)
    
    def remove_item(self, sku: str, qty: int | None = None) -> None:
        # Check if sku exists
        if sku not in self._items:
            raise KeyError(f"SKU '{sku}' not found in cart")
        
        existing_price, existing_qty = self._items[sku]
        
        if qty is None:
            # Remove entire line
            del self._items[sku]
        else:
            # Validate qty
            if not isinstance(qty, int) or qty < 1:
                raise ValueError("qty must be an integer >= 1")
            if qty > existing_qty:
                raise ValueError("qty cannot be more than the quantity in the cart")
            
            new_qty = existing_qty - qty
            if new_qty == 0:
                # Remove the line
                del self._items[sku]
            else:
                self._items[sku] = (existing_price, new_qty)
    
    def apply_coupon(self, code: str) -> None:
        # Validate coupon code
        if code not in ("SAVE10", "FIVEOFF"):
            raise ValueError(f"Invalid coupon code: {code}")
        
        self._coupon = code
    
    def item_count(self) -> int:
        return sum(qty for _, qty in self._items.values())
    
    def summary(self) -> dict[str, Decimal]:
        # Calculate subtotal
        subtotal = Decimal("0")
        for price, qty in self._items.values():
            subtotal += price * qty
        
        # Calculate discount based on coupon
        discount = Decimal("0")
        if self._coupon == "SAVE10":
            discount = subtotal * Decimal("0.10")
        elif self._coupon == "FIVEOFF":
            discount = Decimal("5.00")
            if discount > subtotal:
                discount = subtotal
        
        # Round discount to cents with ROUND_HALF_UP
        discount = discount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        # Calculate taxable amount and tax
        taxable = subtotal - discount
        tax = taxable * self._tax_rate
        tax = tax.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        # Calculate total
        total = subtotal - discount + tax
        
        # Round subtotal to cents
        subtotal = subtotal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        # Round total to cents
        total = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        return {
            "subtotal": subtotal,
            "discount": discount,
            "tax": tax,
            "total": total,
        }
