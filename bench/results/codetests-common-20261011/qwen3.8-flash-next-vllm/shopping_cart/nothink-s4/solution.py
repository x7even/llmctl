from decimal import Decimal, ROUND_HALF_UP, InvalidOperation


class Cart:
    def __init__(self, tax_rate: str | Decimal = "0") -> None:
        # Convert tax_rate to Decimal
        if isinstance(tax_rate, str):
            try:
                rate = Decimal(tax_rate)
            except InvalidOperation:
                raise ValueError("Invalid tax rate")
        elif isinstance(tax_rate, Decimal):
            rate = tax_rate
        else:
            raise ValueError("Invalid tax rate")

        # Check bounds: 0 <= rate <= 1
        if rate < 0 or rate > 1:
            raise ValueError("Tax rate must be between 0 and 1 inclusive")

        self._tax_rate = rate
        self._items: dict[str, tuple[Decimal, int]] = {}  # sku -> (price, qty)
        self._coupon: str | None = None

    def add_item(self, sku: str, price: str | Decimal, qty: int = 1) -> None:
        # Validate qty
        if not isinstance(qty, int) or qty < 1:
            raise ValueError("Quantity must be an integer >= 1")

        # Convert price to Decimal
        if isinstance(price, str):
            try:
                unit_price = Decimal(price)
            except InvalidOperation:
                raise ValueError("Invalid price")
        elif isinstance(price, Decimal):
            unit_price = price
        else:
            raise ValueError("Invalid price")

        # Validate price
        if unit_price < 0:
            raise ValueError("Price must be >= 0")

        # Check if SKU already exists
        if sku in self._items:
            existing_price, existing_qty = self._items[sku]
            if existing_price != unit_price:
                raise ValueError("Price mismatch for existing SKU")
            # Increase quantity
            self._items[sku] = (existing_price, existing_qty + qty)
        else:
            # Add new item
            self._items[sku] = (unit_price, qty)

    def remove_item(self, sku: str, qty: int | None = None) -> None:
        if sku not in self._items:
            raise KeyError(f"SKU {sku} not in cart")

        existing_price, existing_qty = self._items[sku]

        if qty is None:
            # Remove entire line
            del self._items[sku]
        else:
            # Validate qty
            if not isinstance(qty, int) or qty < 1:
                raise ValueError("Quantity must be an integer >= 1")
            if qty > existing_qty:
                raise ValueError("Quantity to remove exceeds quantity in cart")

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
