from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Union


class Cart:
    def __init__(self, tax_rate: Union[str, Decimal] = "0") -> None:
        # Convert tax_rate to Decimal
        if isinstance(tax_rate, str):
            tax_rate = Decimal(tax_rate)
        elif not isinstance(tax_rate, Decimal):
            tax_rate = Decimal(str(tax_rate))
        
        # Validate tax_rate is between 0 and 1 inclusive
        if tax_rate < 0 or tax_rate > 1:
            raise ValueError("tax_rate must be between 0 and 1 inclusive")
        
        self._tax_rate = tax_rate
        self._items: dict[str, tuple[Decimal, int]] = {}  # sku -> (price, qty)
        self._coupon: str | None = None

    def add_item(self, sku: str, price: Union[str, Decimal], qty: int = 1) -> None:
        # Validate qty
        if not isinstance(qty, int) or qty < 1:
            raise ValueError("qty must be an int >= 1")
        
        # Convert price to Decimal
        if isinstance(price, str):
            price = Decimal(price)
        elif not isinstance(price, Decimal):
            price = Decimal(str(price))
        
        # Validate price
        if price < 0:
            raise ValueError("price must be >= 0")
        
        # Check if SKU already exists
        if sku in self._items:
            existing_price, existing_qty = self._items[sku]
            if existing_price != price:
                raise ValueError("price differs from existing price for this SKU")
            self._items[sku] = (existing_price, existing_qty + qty)
        else:
            self._items[sku] = (price, qty)

    def remove_item(self, sku: str, qty: Union[int, None] = None) -> None:
        # Check if SKU exists
        if sku not in self._items:
            raise KeyError(f"SKU '{sku}' not in cart")
        
        existing_price, existing_qty = self._items[sku]
        
        if qty is None:
            # Remove entire line
            del self._items[sku]
        else:
            # Validate qty
            if not isinstance(qty, int) or qty < 1:
                raise ValueError("qty must be >= 1")
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
            raise ValueError(f"Invalid coupon code: '{code}'")
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
        
        # Calculate tax
        taxable = subtotal - discount
        tax = taxable * self._tax_rate
        tax = tax.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        # Calculate total
        total = subtotal - discount + tax
        total = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        # Round subtotal to cents
        subtotal = subtotal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        return {
            "subtotal": subtotal,
            "discount": discount,
            "tax": tax,
            "total": total,
        }
