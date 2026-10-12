from decimal import Decimal, ROUND_HALF_UP


class Cart:
    def __init__(self, tax_rate: str | Decimal = "0") -> None:
        # Validate tax_rate
        if isinstance(tax_rate, str):
            try:
                tax_rate = Decimal(tax_rate)
            except Exception:
                raise ValueError("Invalid tax_rate")
        elif not isinstance(tax_rate, Decimal):
            raise ValueError("Invalid tax_rate")
        
        if tax_rate < 0 or tax_rate > 1:
            raise ValueError("tax_rate must be between 0 and 1 inclusive")
        
        self._tax_rate = tax_rate
        self._items: dict[str, tuple[Decimal, int]] = {}  # sku -> (price, qty)
        self._coupon: str | None = None

    def add_item(self, sku: str, price: str | Decimal, qty: int = 1) -> None:
        # Validate qty
        if not isinstance(qty, int) or qty < 1:
            raise ValueError("qty must be an int >= 1")
        
        # Validate price
        if isinstance(price, str):
            try:
                price = Decimal(price)
            except Exception:
                raise ValueError("Invalid price")
        elif not isinstance(price, Decimal):
            raise ValueError("Invalid price")
        
        if price < 0:
            raise ValueError("price must be >= 0")
        
        # Check if SKU already exists
        if sku in self._items:
            existing_price, existing_qty = self._items[sku]
            if existing_price != price:
                raise ValueError("Price mismatch for existing SKU")
            self._items[sku] = (existing_price, existing_qty + qty)
        else:
            self._items[sku] = (price, qty)

    def remove_item(self, sku: str, qty: int | None = None) -> None:
        if sku not in self._items:
            raise KeyError(f"SKU {sku} not in cart")
        
        existing_price, existing_qty = self._items[sku]
        
        if qty is None:
            # Remove the whole line
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
        if code == "SAVE10":
            self._coupon = code
        elif code == "FIVEOFF":
            self._coupon = code
        else:
            raise ValueError(f"Invalid coupon code: {code}")

    def item_count(self) -> int:
        return sum(qty for _, qty in self._items.values())

    def summary(self) -> dict[str, Decimal]:
        # Calculate subtotal
        subtotal = Decimal("0")
        for price, qty in self._items.values():
            subtotal += price * qty
        
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
