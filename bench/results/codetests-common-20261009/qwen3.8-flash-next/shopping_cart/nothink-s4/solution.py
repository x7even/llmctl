from decimal import Decimal, ROUND_HALF_UP
from typing import Optional


class Cart:
    def __init__(self, tax_rate: str | Decimal = "0") -> None:
        # Convert tax_rate to Decimal
        if isinstance(tax_rate, str):
            rate = Decimal(tax_rate)
        else:
            rate = Decimal(tax_rate)
        
        # Check that tax_rate is between 0 and 1 inclusive
        if rate < 0 or rate > 1:
            raise ValueError("tax_rate must be between 0 and 1 inclusive")
        
        self._tax_rate = rate
        self._items: dict[str, dict[str, Decimal | int]] = {}
        self._coupon: Optional[str] = None

    def add_item(self, sku: str, price: str | Decimal, qty: int = 1) -> None:
        # Validate qty
        if not isinstance(qty, int) or qty < 1:
            raise ValueError("qty must be an integer >= 1")
        
        # Convert price to Decimal
        if isinstance(price, str):
            price_dec = Decimal(price)
        else:
            price_dec = Decimal(price)
        
        # Validate price
        if price_dec < 0:
            raise ValueError("price must be >= 0")
        
        # Check if SKU already exists
        if sku in self._items:
            existing_price = self._items[sku]["price"]
            if existing_price != price_dec:
                raise ValueError("Price mismatch for existing SKU")
            # Increase quantity
            self._items[sku]["qty"] += qty
        else:
            # Add new item
            self._items[sku] = {"price": price_dec, "qty": qty}

    def remove_item(self, sku: str, qty: int | None = None) -> None:
        # Check if SKU exists
        if sku not in self._items:
            raise KeyError(f"SKU '{sku}' not in cart")
        
        current_qty = self._items[sku]["qty"]
        
        if qty is None:
            # Remove entire line
            del self._items[sku]
        else:
            # Validate qty
            if not isinstance(qty, int) or qty < 1:
                raise ValueError("qty must be an integer >= 1")
            if qty > current_qty:
                raise ValueError("qty exceeds quantity in cart")
            
            new_qty = current_qty - qty
            if new_qty == 0:
                del self._items[sku]
            else:
                self._items[sku]["qty"] = new_qty

    def apply_coupon(self, code: str) -> None:
        if code not in ("SAVE10", "FIVEOFF"):
            raise ValueError(f"Invalid coupon code: {code}")
        self._coupon = code

    def item_count(self) -> int:
        return sum(item["qty"] for item in self._items.values())

    def summary(self) -> dict[str, Decimal]:
        # Calculate subtotal
        subtotal = Decimal("0")
        for item in self._items.values():
            line_total = item["price"] * item["qty"]
            subtotal += line_total
        
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
        
        # Round subtotal and total to cents
        subtotal = subtotal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        return {
            "subtotal": subtotal,
            "discount": discount,
            "tax": tax,
            "total": total,
        }
