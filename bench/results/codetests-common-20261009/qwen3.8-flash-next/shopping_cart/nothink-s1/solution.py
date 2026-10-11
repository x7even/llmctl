from decimal import Decimal, ROUND_HALF_UP

class Cart:
    def __init__(self, tax_rate: str | Decimal = "0") -> None:
        # Convert tax_rate to Decimal if it's a string
        if isinstance(tax_rate, str):
            tax_rate = Decimal(tax_rate)
        elif not isinstance(tax_rate, Decimal):
            raise ValueError("tax_rate must be a string or Decimal")
        
        # Validate tax_rate is between 0 and 1 inclusive
        if tax_rate < Decimal("0") or tax_rate > Decimal("1"):
            raise ValueError("tax_rate must be between 0 and 1 inclusive")
        
        self._tax_rate = tax_rate
        self._items: dict[str, tuple[Decimal, int]] = {}  # sku -> (price, qty)
        self._coupon: str | None = None
    
    def add_item(self, sku: str, price: str | Decimal, qty: int = 1) -> None:
        # Validate qty
        if not isinstance(qty, int) or qty < 1:
            raise ValueError("qty must be an integer >= 1")
        
        # Convert price to Decimal if it's a string
        if isinstance(price, str):
            price = Decimal(price)
        elif not isinstance(price, Decimal):
            raise ValueError("price must be a string or Decimal")
        
        # Validate price
        if price < Decimal("0"):
            raise ValueError("price must be >= 0")
        
        # Check if SKU already exists
        if sku in self._items:
            existing_price, existing_qty = self._items[sku]
            # If price differs, raise ValueError
            if existing_price != price:
                raise ValueError("Price for SKU already in cart differs from provided price")
            # Increase quantity
            self._items[sku] = (existing_price, existing_qty + qty)
        else:
            self._items[sku] = (price, qty)
    
    def remove_item(self, sku: str, qty: int | None = None) -> None:
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
                raise ValueError("qty must be an integer >= 1")
            if qty > existing_qty:
                raise ValueError("qty is more than the quantity in the cart")
            
            new_qty = existing_qty - qty
            if new_qty == 0:
                del self._items[sku]
            else:
                self._items[sku] = (existing_price, new_qty)
    
    def apply_coupon(self, code: str) -> None:
        if code == "SAVE10":
            self._coupon = "SAVE10"
        elif code == "FIVEOFF":
            self._coupon = "FIVEOFF"
        else:
            raise ValueError(f"Invalid coupon code: {code}")
    
    def item_count(self) -> int:
        total = 0
        for sku, (price, qty) in self._items.items():
            total += qty
        return total
    
    def summary(self) -> dict[str, Decimal]:
        zero = Decimal("0.00")
        
        # Calculate subtotal
        subtotal = Decimal("0")
        for sku, (price, qty) in self._items.items():
            subtotal += price * qty
        
        # Calculate discount
        discount = Decimal("0")
        if self._coupon == "SAVE10":
            discount = subtotal * Decimal("0.10")
        elif self._coupon == "FIVEOFF":
            discount = Decimal("5.00")
            if discount > subtotal:
                discount = subtotal
        
        # Round discount to cents
        discount = discount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        # Calculate taxable amount
        taxable = subtotal - discount
        if taxable < Decimal("0"):
            taxable = Decimal("0")
        
        # Calculate tax
        tax = taxable * self._tax_rate
        tax = tax.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        # Calculate total
        total = subtotal - discount + tax
        
        # Round all values to cents
        subtotal = subtotal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        return {
            "subtotal": subtotal,
            "discount": discount,
            "tax": tax,
            "total": total,
        }
