Write a Python module implementing a `Cart` class for a simple online shop. Standard library only; use `decimal.Decimal` for all money.

```python
class Cart:
    def __init__(self, tax_rate: str | Decimal = "0") -> None: ...
    def add_item(self, sku: str, price: str | Decimal, qty: int = 1) -> None: ...
    def remove_item(self, sku: str, qty: int | None = None) -> None: ...
    def apply_coupon(self, code: str) -> None: ...
    def item_count(self) -> int: ...
    def summary(self) -> dict[str, Decimal]: ...
```

Behaviour:

1. `tax_rate` is a fraction (`"0.08"` means 8%). It must be between 0 and 1 inclusive, otherwise `ValueError`.
2. `add_item` adds `qty` units of `sku` at unit `price` (a string or `Decimal`; convert strings with `Decimal(price)`). `qty` must be an int >= 1 and `price` must be >= 0, otherwise `ValueError`. Adding a SKU that is already in the cart increases its quantity; if the new `price` differs from the price already in the cart for that SKU, raise `ValueError`.
3. `remove_item(sku, qty=None)` removes `qty` units, or the whole line when `qty` is `None`. Raise `KeyError` if the SKU is not in the cart, and `ValueError` if `qty` is less than 1 or more than the quantity in the cart. A line whose quantity reaches zero disappears from the cart.
4. `item_count()` returns the total number of units across all lines.
5. Coupons: `"SAVE10"` takes 10% off the subtotal; `"FIVEOFF"` takes 5.00 off the subtotal but never more than the subtotal. Any other code raises `ValueError`. Only one coupon is active at a time: applying a new valid coupon replaces the previous one. Coupon codes are case-sensitive.
6. `summary()` returns a dict with exactly the keys `"subtotal"`, `"discount"`, `"tax"`, `"total"`, all `Decimal` values rounded to cents (2 decimal places):
   - `subtotal` = sum of price * quantity over all lines.
   - `discount` = the coupon discount (0.00 with no coupon), rounded to cents with ROUND_HALF_UP.
   - `tax` = (subtotal - discount) * tax_rate, rounded to cents with ROUND_HALF_UP.
   - `total` = subtotal - discount + tax.
   An empty cart gives all zeros.

Output requirements: reply with **one** Python code block containing the complete module. No explanation outside the code block.
