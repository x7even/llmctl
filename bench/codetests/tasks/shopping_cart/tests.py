"""Hidden tests for shopping_cart. Each test takes the loaded solution module `m`."""
from decimal import Decimal as D


def _raises(exc, fn):
    try:
        fn()
    except exc:
        return
    except Exception as e:
        raise AssertionError(f"raised {type(e).__name__}, expected {exc.__name__}")
    raise AssertionError(f"did not raise {exc.__name__}")


def test_empty_cart(m):
    s = m.Cart().summary()
    assert s == {"subtotal": D("0.00"), "discount": D("0.00"), "tax": D("0.00"), "total": D("0.00")}
    assert m.Cart().item_count() == 0


def test_add_and_subtotal(m):
    c = m.Cart()
    c.add_item("A", "2.50", 2)
    c.add_item("B", D("10"))
    s = c.summary()
    assert s["subtotal"] == D("15.00") and s["total"] == D("15.00")
    assert c.item_count() == 3


def test_add_same_sku_accumulates(m):
    c = m.Cart()
    c.add_item("A", "1.99", 2)
    c.add_item("A", "1.99", 3)
    assert c.item_count() == 5
    assert c.summary()["subtotal"] == D("9.95")


def test_add_validation(m):
    c = m.Cart()
    _raises(ValueError, lambda: c.add_item("A", "1.00", 0))
    _raises(ValueError, lambda: c.add_item("A", "1.00", -2))
    _raises(ValueError, lambda: c.add_item("A", "-1.00"))
    c.add_item("A", "1.00")
    _raises(ValueError, lambda: c.add_item("A", "2.00"))
    assert c.item_count() == 1


def test_remove_partial_and_full(m):
    c = m.Cart()
    c.add_item("A", "3.00", 4)
    c.remove_item("A", 1)
    assert c.item_count() == 3
    c.remove_item("A")
    assert c.item_count() == 0 and c.summary()["subtotal"] == D("0.00")
    _raises(KeyError, lambda: c.remove_item("A"))


def test_remove_validation(m):
    c = m.Cart()
    c.add_item("A", "3.00", 2)
    _raises(KeyError, lambda: c.remove_item("zzz"))
    _raises(ValueError, lambda: c.remove_item("A", 3))
    _raises(ValueError, lambda: c.remove_item("A", 0))
    assert c.item_count() == 2


def test_remove_exact_quantity_removes_line(m):
    c = m.Cart()
    c.add_item("A", "3.00", 2)
    c.remove_item("A", 2)
    assert c.item_count() == 0
    _raises(KeyError, lambda: c.remove_item("A", 1))


def test_coupon_save10(m):
    c = m.Cart()
    c.add_item("A", "40.00", 2)
    c.apply_coupon("SAVE10")
    s = c.summary()
    assert s["subtotal"] == D("80.00") and s["discount"] == D("8.00") and s["total"] == D("72.00")


def test_coupon_fiveoff_capped(m):
    c = m.Cart()
    c.add_item("A", "3.00")
    c.apply_coupon("FIVEOFF")
    s = c.summary()
    assert s["discount"] == D("3.00") and s["total"] == D("0.00")
    c.add_item("B", "20.00")
    s = c.summary()
    assert s["discount"] == D("5.00") and s["total"] == D("18.00")


def test_coupon_replaces_previous_and_validation(m):
    c = m.Cart()
    c.add_item("A", "100.00")
    c.apply_coupon("SAVE10")
    c.apply_coupon("FIVEOFF")
    assert c.summary()["discount"] == D("5.00")
    _raises(ValueError, lambda: c.apply_coupon("save10"))
    _raises(ValueError, lambda: c.apply_coupon("BOGUS"))
    assert c.summary()["discount"] == D("5.00")  # failed apply leaves the old coupon


def test_tax(m):
    c = m.Cart("0.08")
    c.add_item("A", "50.00")
    s = c.summary()
    assert s["tax"] == D("4.00") and s["total"] == D("54.00")


def test_tax_applied_after_discount_with_rounding(m):
    c = m.Cart("0.0825")
    c.add_item("A", "19.99", 3)  # subtotal 59.97
    c.apply_coupon("SAVE10")     # discount 5.997 -> 6.00
    s = c.summary()
    assert s["subtotal"] == D("59.97") and s["discount"] == D("6.00")
    assert s["tax"] == D("4.45")  # (59.97 - 6.00) * 0.0825 = 4.452525
    assert s["total"] == D("58.42")


def test_half_up_rounding(m):
    c = m.Cart("0.5")
    c.add_item("A", "0.01")
    s = c.summary()
    assert s["tax"] == D("0.01")  # 0.005 rounds half up


def test_tax_rate_validation(m):
    _raises(ValueError, lambda: m.Cart("-0.1"))
    _raises(ValueError, lambda: m.Cart("1.5"))
    m.Cart("0")
    m.Cart("1")


def test_summary_keys_and_types(m):
    c = m.Cart("0.1")
    c.add_item("A", "9.99")
    s = c.summary()
    assert set(s) == {"subtotal", "discount", "tax", "total"}
    assert all(isinstance(v, D) for v in s.values())
    assert all(v == v.quantize(D("0.01")) and v.as_tuple().exponent == -2 for v in s.values())


TESTS = [test_empty_cart, test_add_and_subtotal, test_add_same_sku_accumulates, test_add_validation,
         test_remove_partial_and_full, test_remove_validation, test_remove_exact_quantity_removes_line,
         test_coupon_save10, test_coupon_fiveoff_capped, test_coupon_replaces_previous_and_validation,
         test_tax, test_tax_applied_after_discount_with_rounding, test_half_up_rounding,
         test_tax_rate_validation, test_summary_keys_and_types]
