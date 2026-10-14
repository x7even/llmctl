Write a Python module that implements proleptic-Gregorian calendar arithmetic for the years 1 through 9999. The module must **not import `datetime`, `calendar`, `time`, `dateutil` or `email.utils`** (nor load them dynamically); everything is plain integer arithmetic. Other standard-library modules (for example `re`) are fine.

A *date* is always passed and returned as a plain `tuple` of three `int`s `(year, month, day)`. The range of valid dates is `(1, 1, 1)` through `(9999, 12, 31)`.

## Public API

```python
def is_leap(y) -> bool: ...
def days_in_month(y, m) -> int: ...
def to_ordinal(y, m, d) -> int: ...
def from_ordinal(n) -> tuple: ...
def weekday(y, m, d) -> int: ...
def add_days(date, n) -> tuple: ...
def add_months(date, n) -> tuple: ...
def iso_weeks_in_year(iso_year) -> int: ...
def iso_week(y, m, d) -> tuple: ...
def from_iso_week(iso_year, week, weekday) -> tuple: ...
def parse(s) -> tuple: ...
def format_date(date, form) -> str: ...
def diff(a, b) -> tuple: ...
```

## Argument checking (applies to every function)

1. **Types first.** An "int" means a value whose type is exactly `int`; `bool`, `float`, `str`, `None` and int subclasses are **not** ints. Every function first checks the types of all its arguments, and a wrong type raises `TypeError`. This covers each of `y`, `m`, `d`, `n`, `iso_year`, `week`, `weekday`; `s` must be a `str`; a `date` argument (`date`, `a`, `b`) must be a `tuple` of exactly 3 ints (a list, a 2-tuple, a tuple containing a float, ... all raise `TypeError`). The type check of *all* arguments happens before any range check, so `to_ordinal(2024.5, 13, 40)` raises `TypeError`, not `ValueError`.
2. **Then ranges.** After the types are fine, an invalid calendar date (year outside 1..9999, month outside 1..12, day outside `1..days_in_month(y, m)`, e.g. Feb 30, or Feb 29 in 1900 or 2100) raises `ValueError`. This holds for every function that takes a date: `to_ordinal`, `weekday`, `add_days`, `add_months`, `iso_week`, `format_date`, and both arguments of `diff`. `is_leap(y)` raises `ValueError` for a year outside 1..9999; `days_in_month(y, m)` for a year outside 1..9999 or a month outside 1..12. `iso_weeks_in_year(iso_year)` raises `ValueError` outside 1..9999.
3. `ValueError` and `OverflowError` are different: a *valid* date plus a request whose *result* leaves the supported range raises `OverflowError` where stated below (`add_days`, `add_months`, `from_iso_week`).

All functions must be efficient: arithmetic or O(log n), never a loop over the years or days of the input. (The tests make on the order of 10^5 calls and also pass huge `n` such as `10**15` and expect a fast `OverflowError`.)

## Functions

* `is_leap(y)` - Gregorian rule (divisible by 4, except centuries not divisible by 400). `days_in_month(y, m)` - 28..31.
* `to_ordinal(y, m, d)` - day number where `(1, 1, 1)` is day 1 (same convention as `datetime.date.toordinal`; `(9999, 12, 31)` is 3652059).
* `from_ordinal(n)` - inverse; `n` outside `1..3652059` raises `ValueError`.
* `weekday(y, m, d)` - Monday = 0 ... Sunday = 6. (`(1, 1, 1)` is a Monday.)
* `add_days(date, n)` - the date `n` days later (`n` may be negative or zero). If the result is before `(1,1,1)` or after `(9999,12,31)` raise `OverflowError`.
* `add_months(date, n)` - shift by `n` calendar months (`n` any int, may be negative). Keep the day-of-month of the *input* date; if the target month is shorter, clamp the day to that month's last day. The clamp is applied **once, at the end**, to the original day: `add_months((2024,1,31), 1) == (2024,2,29)`, `add_months((2024,1,31), 2) == (2024,3,31)`, `add_months((2023,1,31), 13) == (2024,2,29)`, `add_months((2024,3,31), -1) == (2024,2,29)`. If the target year is outside 1..9999 raise `OverflowError` (e.g. `add_months((9999,12,1), 1)`, `add_months((1,1,31), -1)`, `add_months((2000,1,1), 10**12)`); a target inside the range is fine even when the input day had to be clamped.
* `iso_weeks_in_year(iso_year)` - 52 or 53, the number of ISO 8601 weeks in that ISO year. A year has 53 weeks exactly when 1 January is a Thursday, or when it is a leap year and 1 January is a Wednesday (equivalently: its 28 December falls in week 53).
* `iso_week(y, m, d)` - ISO 8601 week date as `(iso_year, iso_week, iso_weekday)`, `iso_weekday` Monday = 1 ... Sunday = 7. Week 1 is the week containing the year's first Thursday (equivalently the week containing 4 January); weeks start on Monday. Early-January days can belong to week 52/53 of the previous ISO year and late-December days to week 1 of the next (for example `iso_week(2024,12,30) == (2025,1,1)`, `iso_week(2021,1,3) == (2020,53,7)`). Same results as `datetime.date.isocalendar()`.
* `from_iso_week(iso_year, week, weekday)` - inverse of `iso_week`; returns `(y, m, d)`. `iso_year` outside 1..9999, `week` outside `1..iso_weeks_in_year(iso_year)` (so week 53 is only valid in 53-week years), or `weekday` outside 1..7 raise `ValueError`. If the named day falls outside `(1,1,1)..(9999,12,31)` raise `OverflowError` (this happens for `from_iso_week(9999, 52, 6)` and `(9999, 52, 7)`, which lie in January of year 10000).
* `parse(s)` - parse an ISO 8601 date string into `(y, m, d)`. **Exactly these six forms are accepted** (`Y`, `M`, `D`, `w` stand for ASCII digits `0-9`; `W` is the uppercase letter, `-` the ASCII hyphen):

  | form | extended | basic |
  |---|---|---|
  | calendar | `YYYY-MM-DD` | `YYYYMMDD` |
  | ordinal (day of year) | `YYYY-DDD` | `YYYYDDD` |
  | week | `YYYY-Www-D` | `YYYYWwwD` |

  In the week forms `YYYY` is the **ISO** year, `ww` the week (01-53) and `D` the ISO weekday (1-7); in the ordinal forms `DDD` is the day of the year (001-365, or 001-366 in leap years). Everything else raises `ValueError`, in particular: lowercase `w`; missing leading zeros (`2024-1-1`, `2024-01-1`); any leading or trailing whitespace including a trailing newline; a year that is not 4 digits or is `0000`; day 366 in a non-leap year or day `000`; month 00 or 13, day 00 or a day beyond the month's length; week `00`, `54`, or week 53 in a year with only 52 ISO weeks; weekday `0`, `8` or `9`; mixing basic and extended notation (`2024-0101`, `202401-01`, `2024W10-1`, `2024-W101`); week dates without the weekday (`2024-W10`); time parts, signs, extra characters, the empty string; digits that are not ASCII `0-9` (e.g. full-width or Arabic-Indic digits). A week date whose day lies beyond `9999-12-31` (e.g. `9999-W52-6`) is also a `ValueError` in `parse` (not `OverflowError`). The ordinal form `YYYY-DDD` and the basic calendar form `YYYYMMDD` are both 8 characters long; they are told apart by the hyphen. Examples: `parse("2024-366") == (2024,12,31)`, `parse("2024060") == (2024,2,29)`, `parse("2026-W53-5") == (2027,1,1)`, `parse("20201228") == (2020,12,28)`, `parse("2025W011") == (2024,12,30)`.
* `format_date(date, form)` - `form` is exactly one of the strings `'calendar'`, `'ordinal'`, `'week'` (anything else, including other case, `None` or non-strings, raises `ValueError`; the date is type- and range-checked first, the form check comes after the date checks). Output is in **extended** notation with zero padding: `'YYYY-MM-DD'`, `'YYYY-DDD'`, `'YYYY-Www-D'`, where in the week form `YYYY` is the ISO year. Years are padded to 4 digits (`format_date((1,1,1),'calendar') == '0001-01-01'`). `parse(format_date(x, f)) == x` for every date and form. Example: `format_date((2024,12,30), 'week') == '2025-W01-1'`.
* `diff(a, b)` - calendar difference, returned as `(years, months, days)`, defined by the following rule (there is no standard-library equivalent, so read it carefully).

  **Rule for `a <= b`.** Let `shift(a, k)` be `add_months(a, k)` (clamp applied once to `a`'s original day, as above). Because `shift(a, k)` never decreases as `k` grows, there is a unique largest integer `K >= 0` with `shift(a, K) <= b`. Then `years, months = divmod(K, 12)` and `days = to_ordinal(b) - to_ordinal(shift(a, K))` (a non-negative number of plain days). So whole months are taken first (the month step clamps like `add_months`), and the remainder is counted in days. The result is unique, `0 <= months <= 11`, `days >= 0`, and it satisfies the identity `add_days(add_months(a, 12*years + months), days) == b`.

  **Clamp behaviour.** The month step is always measured from `a`'s *original* day, never from a previously clamped day: `diff((2023,1,31),(2023,2,28)) == (0,1,0)` (Jan 31 + 1 month clamps to Feb 28, which is not after Feb 28); `diff((2023,1,31),(2023,3,1)) == (0,1,1)` (Feb 28, plus 1 day; Mar 31 would overshoot); `diff((2023,1,31),(2023,3,30)) == (0,1,30)`; `diff((2023,1,31),(2023,3,31)) == (0,2,0)`; `diff((2024,1,31),(2024,3,1)) == (0,1,1)` (leap year: Feb 29, plus 1 day); `diff((2024,2,29),(2025,2,28)) == (1,0,0)` and `diff((2024,2,29),(2025,3,1)) == (1,0,1)`; `diff((2000,1,1),(2000,1,1)) == (0,0,0)`.

  **Rule for `a > b`.** `diff(a, b)` is the component-wise negation of `diff(b, a)`, for example `diff((2023,3,1),(2023,1,31)) == (0,-1,-1)`. (The months are measured from the *earlier* date, here `b`; there is no separate "borrow from the later date" rule.)

  `diff` returns a tuple of plain ints; both dates are checked as in "Argument checking".

Output requirements: reply with **one** Python code block containing the complete module. No explanation outside the code block.
