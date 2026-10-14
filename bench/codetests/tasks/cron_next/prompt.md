Write a Python module that computes the next firing time of a standard 5-field cron expression. Standard library only (the `datetime` module is allowed).

Public API:

```python
import datetime

def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime: ...
```

`expr` is always a `str`. `after` is always a **naive** `datetime.datetime` with `1900 <= year <= 3000`. The function must not modify its arguments.

## Result

`next_fire` returns the **earliest** naive `datetime.datetime` `t` such that all of the following hold:

1. `t.second == 0` and `t.microsecond == 0` (whole minutes only);
2. `t > after`, compared as full datetimes (strictly greater: if `after` is itself a firing minute with zero seconds, that minute is **not** returned; if `after` is `12:00:30`, then `12:00` is not returned either);
3. the minute, hour, day and month of `t` match `expr` (see "Day matching" for how days are matched);
4. `t.year <= after.year + 8` (the search horizon).

If no such `t` exists, raise `LookupError`. For example `0 0 30 2 *` (Feb 30) always raises `LookupError`. The horizon is purely a calendar-year bound: with `after = 2025-06-01 00:00` the latest acceptable result is `2033-12-31 23:59`.

## Expression syntax

`expr` consists of exactly **5 fields** separated by whitespace, in this order:

| # | field | allowed values | names |
|---|-------|----------------|-------|
| 1 | minute | 0-59 | none |
| 2 | hour | 0-23 | none |
| 3 | day-of-month | 1-31 | none |
| 4 | month | 1-12 | `JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC` = 1..12 |
| 5 | day-of-week | 0-7 | `SUN MON TUE WED THU FRI SAT` = 0..6 |

For day-of-week, **both 0 and 7 mean Sunday**; 1 = Monday ... 6 = Saturday. Names are exactly three letters, case-insensitive (`mon`, `Mon`, `MON` are all fine), and are allowed only in the month and day-of-week fields. A name behaves exactly like its number: for example `SUN` is 0 (not 7), so `FRI-SUN` is the range 5-0 and is reversed (invalid), whereas `FRI-7` is valid.

**Whitespace.** Fields are separated by one or more space (`' '`) or tab (`'\t'`) characters. Leading and trailing spaces/tabs around the whole expression are allowed. No other character is whitespace: a newline, carriage return, form feed, non-breaking space, etc. is simply an invalid character inside a field. Fewer or more than 5 fields (including the empty string, or a macro such as `@daily`) is invalid.

**Field grammar.** A field is a comma-separated list of one or more *items*. An item is one of:

| item | meaning |
|------|---------|
| `*` | every value from the field's minimum to its maximum |
| `a` | the single value `a` |
| `a-b` | every value from `a` to `b` inclusive (`a <= b`; `a == b` is fine) |
| `*/n` | every n-th value starting at the field's minimum, up to the field's maximum |
| `a-b/n` | every n-th value starting at `a`, up to `b` inclusive |
| `a/n` | shorthand for `a-MAX/n`, where MAX is the field's maximum: 59, 23, 31, 12 and **7** for the five fields respectively |

`a` and `b` are either a decimal number or (month and day-of-week fields only) a name; a range may mix them (`1-fri`, `MON-5`). The step `n` is a plain decimal number and **must be >= 1**; names are not allowed as steps. A step larger than the range is fine (`*/100` in the minute field is just `{0}`). Examples: `*/15` in the minute field = 0,15,30,45; `10-20/4` = 10,14,18; `5/20` = 5,25,45; `1/2` in the day-of-week field = 1,3,5,7 (Mon, Wed, Fri, Sun, because MAX is 7); `*/2` in the day-of-week field = 0,2,4,6 (Sun, Tue, Thu, Sat); `jan-dec/3` = months 1,4,7,10. The value set of a field is the union of its items; duplicates and overlaps are harmless.

Number tokens are non-empty strings of ASCII digits `0`-`9` only (leading zeros are fine: `05` is 5, `007` is 7). Signs, underscores, decimal points, exponents, hex, and non-ASCII digits (such as Arabic-Indic or full-width digits) are all invalid. Name tokens consist of ASCII letters only. There is no whitespace inside a field.

**Invalid expressions raise `ValueError`.** All five fields are validated before any searching, so an invalid expression raises `ValueError` even if the rest of it would have raised `LookupError`. Invalid means: wrong number of fields; empty field; empty list element (`1,,2`, `1,`, `,1`); any value outside the field's allowed range (numbers are range-checked after name conversion, for range endpoints and single values alike, so `0-60` in the minute field and `8` in the day-of-week field are invalid); a reversed range (`a > b`); a zero step; a malformed step (`*/`, `*/-1`, `*/+2`, `*/1.5`, `*/mon`, `1/2/3`); a malformed range or item (`1-2-3`, `-5`, `5-`, `*-5`, `5-*`, `*5`, `/5`, `**`); names in a field that does not allow them, unknown names, or names that are not exactly three letters (`monday`, `mo`); and any other character (`?`, `L`, `#`, `W`, ...).

## Day matching (Vixie-cron rule)

A day-of-month field or a day-of-week field is **restricted** if its text, exactly as written in the expression (after splitting on whitespace), does **not** start with the character `*`; otherwise it is **unrestricted**. This is a purely textual test: `*`, `*/2` and `*/1` are unrestricted; `1-31`, `0-6`, `1,*` and `mon-sat` are all restricted even though they may match every day.

A calendar day matches when its **month** is in the month field's value set **and**:

- if **both** the day-of-month field and the day-of-week field are restricted: the day-of-month is in the day-of-month field's set **or** the day-of-week is in the day-of-week field's set;
- otherwise (at least one of them is unrestricted): the day-of-month is in the day-of-month field's set **and** the day-of-week is in the day-of-week field's set.

The day of week of a calendar date is Sunday=0 ... Saturday=6, and a day-of-week set containing 7 means Sunday (so a date that is a Sunday is in the set if 0 or 7 is in it). A day-of-month value that a month does not have (for example 31 in April, or 30 in February) simply never matches in that month. Use the real (proleptic) Gregorian calendar: a year is a leap year if divisible by 4, except years divisible by 100 that are not divisible by 400 (so 2100 is not a leap year, 2000 is).

A firing minute is any minute of a matching day whose hour is in the hour field's set and whose minute is in the minute field's set.

## Examples

- `next_fire("*/15 * * * *", datetime(2024,1,1,12,0,0))` -> `2024-01-01 12:15`
- `next_fire("0 0 * * *", datetime(2024,12,31,23,59,59))` -> `2025-01-01 00:00`
- `next_fire("0 0 29 2 *", datetime(2096,3,1))` -> `2104-02-29 00:00` (2100 is not a leap year)
- `next_fire("0 12 13 * fri", datetime(2024,1,1))` -> `2024-01-05 12:00` (both fields restricted: the 13th **or** any Friday; 2024-01-05 is a Friday)
- `next_fire("0 12 */2 * sat", datetime(2024,1,1))` -> `2024-01-13 12:00` (day-of-month is unrestricted, so AND: an odd day that is also a Saturday; Jan 6 is a Saturday but an even day)

Performance: `next_fire` will be called with sparse expressions whose next firing is years away (up to the 8-year horizon), including expressions that end in `LookupError`, so it must not iterate minute by minute over the horizon.

Output requirements: reply with **one** Python code block containing the complete module. No explanation outside the code block.
