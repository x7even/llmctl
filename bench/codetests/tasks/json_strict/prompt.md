Write a Python module implementing a strict RFC 8259 JSON parser. Standard library only, but you must **not** import or use `json`, `simplejson`, `ast`, or `eval`/`exec`/`compile` — the parser has to be written by hand (the `re` module is allowed).

```python
class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None: ...

def loads(s: str): ...
```

`loads` behaves exactly like `json.loads(s)` from the standard library (same Python types, same accept/reject decisions) **except** for the deviations and precisions listed below. Everything not listed here follows `json.loads`.

## Result types

object -> `dict`, array -> `list`, string -> `str`, `true`/`false`/`null` -> `True`/`False`/`None`, integer -> `int`, number with a fraction or an exponent -> `float`. Any JSON value is allowed at top level (`loads("3")`, `loads('"x"')`, `loads("null")` all work).

## Grammar (strict)

* Whitespace is only space, `\t`, `\n`, `\r` (U+0020, U+0009, U+000A, U+000D), allowed before and after any token. Any other character, including `\x0b`, `\x0c`, U+00A0, U+2003, U+2028 and U+FEFF (BOM), is **not** whitespace. A leading BOM is rejected.
* Empty input, or input consisting only of whitespace, is rejected. Anything other than whitespace after the top-level value (trailing garbage) is rejected.
* Literals are exactly `true`, `false`, `null` (lowercase). `NaN`, `Infinity`, `-Infinity` (and every variant of them) are **rejected**.
* Numbers follow the JSON grammar exactly: `-? (0 | [1-9][0-9]*) (. [0-9]+)? ([eE] [+-]? [0-9]+)?`, with ASCII digits only. So no leading zeros (`01`, `-01`), no `+` sign, no `.5`, no `1.`, no `1.e5`, no `0x10`, no digit separators (`1_0`), no non-ASCII digits (such as Arabic-Indic U+0660..U+0669).
* Integers (no fraction and no exponent) are exact arbitrary-precision `int`s (inputs in the tests have at most 4000 digits). `-0` is the `int` `0`. Numbers with a fraction or exponent are the `float` that Python's `float()` gives for that text (`1e5` and `1E-2` are floats; `-0.0` is the float negative zero; `1e400` is `inf` and `-1e400` is `-inf`; `1e-400` is `0.0`; no error is raised for overflow).
* Strings are delimited by `"`. A raw (unescaped) character below U+0020 inside a string is rejected; every other raw character (including U+007F, U+2028, non-BMP characters, and lone surrogate code points that happen to be present in the Python `str`) is kept as is. Valid escapes: `\"` `\\` `\/` `\b` `\f` `\n` `\r` `\t` and `\uXXXX` where `XXXX` is exactly four ASCII hex digits (either case). Any other escape (`\a`, `\'`, `\x41`, `\U0041`, `\0`, ...) is rejected. Be careful that `int(text, 16)` is *more* lenient than this (it accepts signs, spaces, underscores, a `0x` prefix, non-ASCII digits).
* Surrogates: a `\uXXXX` escape denoting a high surrogate (D800-DBFF) that is *immediately* followed by another `\uXXXX` escape denoting a low surrogate (DC00-DFFF) combines with it into the single code point `0x10000 + ((hi - 0xD800) << 10) + (lo - 0xDC00)`. Any other surrogate escape (an unpaired high, an unpaired low, a high followed by something else, a low followed by a high) is kept as a lone surrogate code point, no error. Only two *escapes* combine; a raw surrogate character in the input never combines with anything. `"\ud83d😀"` is a lone high surrogate followed by U+1F600. `"\u0000"` is the NUL character.
* Objects: keys must be strings. A trailing comma in an object or array is rejected, as is a missing comma/colon, `{,}`, `[,]` and `[1,,2]`. If a key occurs more than once, the result is exactly what sequentially executing `d[key] = value` in textual order on a fresh `dict` gives: the **last** value wins, and the key keeps the dict position of its **first** occurrence. Keys are compared after unescaping (`"a"` and `"a"` are the same key).
* Nesting depth: the depth of a document is the maximum number of simultaneously open arrays/objects (`[]` has depth 1, `[[]]` depth 2, `{"a":[{}]}` depth 3, `1` depth 0). Depth up to and including **500** is accepted; a document that nests arrays/objects deeper than 500 levels is rejected with `JSONError` (this is a deviation from `json.loads`). Your parser must not raise `RecursionError` for any input: not for depth <= 500 (the tests run with Python's default recursion limit of 1000 and do not change it; do not call `sys.setrecursionlimit`) and not for the over-limit case (e.g. 200000 consecutive `[`), which must raise `JSONError` promptly.
* Performance: parsing must be linear in the input size (documents of several hundred KB, a 1 MB string, arrays of 100000 elements are parsed in the tests).

## Errors

* If `s` is not a `str` (e.g. `bytes`, `bytearray`, `None`, `int`), raise `TypeError`. (Deviation: `json.loads` accepts bytes.)
* Every rejection of a `str` input raises `JSONError`, which is a subclass of `ValueError`. `JSONError(message, pos)` stores `pos` (an `int`) as the attribute `.pos`; `str(e)` should be a human-readable message (not checked).
* `.pos` is defined **precisely** and identically for every rejection (syntax error, bad escape, control character, trailing garbage, NaN, depth limit, truncated input, ...) as follows. Call a string `p` a *viable prefix* if some valid document (one that `loads` accepts) starts with `p`; the empty string is a viable prefix. For an invalid input `s`:
  * if `s` itself is a viable prefix (the input was cut short, "unexpected end of input"), then `pos == len(s)`;
  * otherwise `pos` is the 0-based index `i` of the first character such that `s[:i+1]` is not a viable prefix (the first character that cannot continue any valid document). `s[:i]` is then a viable prefix.

  Examples: `""` -> 0; `"   "` -> 3; `"[1, 2"` -> 5; `"[1,]"` -> 3; `"[,"` -> 1; `'{"a":1,}'` -> 7; `'{"a" 1}'` -> 5; `"01"` -> 1; `"[01]"` -> 2; `"-"` -> 1; `"-x"` -> 1; `"1."` -> 2; `"1.x"` -> 2; `"1.5e+"` -> 5; `"1e5.5"` -> 3; `"+1"` -> 0; `".5"` -> 0; `"NaN"` -> 0; `"-Infinity"` -> 1; `"nul"` -> 3; `"nan"` -> 1; `"true1"` -> 4; `"[truex]"` -> 5; `"1 2"` -> 2; `'"abc'` -> 4; `'"a\'` (quote, `a`, backslash) -> 3; `'"\u12'` (quote, backslash, `u`, `1`, `2`) -> 5; `'"\u12G4"'` -> 5; `'"\x"'` -> 2; a string literal containing a raw newline character, `'"a<LF>b"'` -> 2; `"﻿1"` -> 0; `"[ 1 ] x"` -> 6. Over the depth limit: `"[" * 501` -> 500 (`"[" * 500` itself is a viable prefix, the 501st opener is the first character that cannot continue a valid document); `"[" * 500 + ","` -> 500; `"[" * 500 + "x"` -> 500.

Output requirements: reply with **one** Python code block containing the complete module. No explanation outside the code block.
