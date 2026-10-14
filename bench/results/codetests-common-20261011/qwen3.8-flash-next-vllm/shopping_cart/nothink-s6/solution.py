from decimal import Decimal, ROUND_HALF_UP


class Cart:
    def __init__(self, tax_rate: str | Decimal = "0") -> None:
        # Convert tax_rate to Decimal if it's a string
        if isinstance(tax_rate, str):
            tax_rate = Decimal(tax_rate)
        # Validate tax_rate is between 0 and 1 inclusive
        if tax_rate < 0 or tax_rate > 1:
            raise ValueError("tax_rate must be between 0 and 1 inclusive")
        self._tax_rate = tax_rate
        self._items = {}  # sku -> {"price": Decimal, "qty": int}
        self._coupon = None  # None or coupon code string

    def add_item(self, sku: str, price: str | Decimal, qty: int = 1) -> None:
        # Validate qty
        if not isinstance(qty, int) or qty < 1:
            raise ValueError("qty must be an int >= 1")
        # Convert price to Decimal if it's a string
        if isinstance(price, str):
            price = Decimal(price)
        # Validate price
        if price < 0:
            raise ValueError("price must be >= 0")
        
        if sku in self._items:
            existing_price = self._items[sku]["price"]
            if existing_price != price:
                raise ValueError("price differs from existing price for this SKU")
            self._items[sku]["qty"] += qty
        else:
            self._items[sku] = {"price": price, "qty": qty}

    def remove_item(self, sku: str, qty: int | None = None) -> None:
        if sku not in self._items:
            raise KeyError(f"SKU {sku} not in cart")
        
        if qty is None:
            # Remove the whole line
            del self._items[sku]
        else:
            # Validate qty
            if not isinstance(qty, int) or qty < 1:
                raise ValueError("qty must be >= 1")
            current_qty = self._items[sku]["qty"]
            if qty > current_qty:
                raise ValueError("qty exceeds quantity in cart")
            self._items[sku]["qty"] -= qty
            if self._items[sku]["qty"] == 0:
                del self._items[sku]

    def apply_coupon(self, code: str) -> None:
        valid_coupons = {"SAVE10", "FIVEOFF"}
        if code not in valid_coupons:
            raise ValueError(f"Invalid coupon code: {code}")
        self._coupon = code

    def item_count(self) -> int:
        total = 0
        for item in self._items.values():
            total += item["qty"]
        return total

    def summary(self) -> dict[str, Decimal]:
        # Calculate subtotal
        subtotal = Decimal("0")
        for item in self._items.values():
            subtotal += item["price"] * item["qty"]
        
        # Calculate discount
        discount = Decimal("0")
        if self._coupon == "SAVE10":
            discount = subtotal * Decimal("0.10")
            discount = discount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        elif self._coupon == "FIVEOFF":
            discount = Decimal("5.00")
            # Never more than subtotal
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
        
        # Round subtotal to 2 decimal places
        subtotal = subtotal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        return {
            "subtotal": subtotal,
            "discount": discount,
            "tax": tax,
            "total": total,
        }
