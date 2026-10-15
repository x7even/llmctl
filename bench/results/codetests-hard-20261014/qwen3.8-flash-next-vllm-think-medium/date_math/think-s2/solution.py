"""Proleptic Gregorian calendar arithmetic for years 1..9999.

No datetime/calendar/time/dateutil/email.utils imports. Pure integer arithmetic.
"""

import re

# ─── Constants ────────────────────────────────────────────────────────────────

_MAX_ORDINAL = 3652059  # ordinal of (9999, 12, 31)

_MONTH_DAYS_COMMON = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

# Cumulative days *before* month m (index 0 = before Jan, index 12 = end of year)
_CUM_COMMON = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365)
_CUM_LEAP   = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366)

# ─── Internal helpers ─────────────────────────────────────────────────────────

def _is_int(x):
    return type(x) is int


def _check_ints(*args):
    for x in args:
        if type(x) is not int:
            raise TypeError(f"expected int, got {type(x).__name__}")


def _check_date_tuple(date):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError("date must be a tuple of 3 ints")
    for x in date:
        if type(x) is not int:
            raise TypeError("date elements must be int")


def _check_date_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError(f"year out of range: {y}")
    if m < 1 or m > 12:
        raise ValueError(f"month out of range: {m}")
    if d < 1 or d > _dim(y, m):
        raise ValueError(f"day out of range: {d}")


def _leap(y):
    """Leap check without range validation (caller must validate)."""
    return (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)


def _dim(y, m):
    """days_in_month without range validation."""
    if m == 2:
        return 29 if _leap(y) else 28
    return _MONTH_DAYS_COMMON[m - 1]


def _ord_raw(y, m, d):
    """to_ordinal without type/range checks."""
    y1 = y - 1
    days = 365 * y1 + y1 // 4 - y1 // 100 + y1 // 400
    days += _CUM_COMMON[m - 1]
    if m > 2 and _leap(y):
        days += 1
    return days + d


def _from_ord_raw(n):
    """from_ordinal without type/range checks. n is 1-based ordinal."""
    n -= 1  # 0-based
    n400, n = divmod(n, 146097)
    n100, n = divmod(n, 36524)
    n4, n = divmod(n, 1461)
    n1, n = divmod(n, 365)
    y = n400 * 400 + n100 * 100 + n4 * 4 + n1 + 1
    if n100 == 4 or n1 == 4:
        y -= 1
        n = 365
    cum = _CUM_LEAP if _leap(y) else _CUM_COMMON
    lo, hi = 1, 12
    while lo < hi:
        mid = (