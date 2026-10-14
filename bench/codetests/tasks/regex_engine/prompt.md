Write a Python module that implements a **backtracking-priority regular-expression engine from scratch**. You must **not** use the `re` module, `regex`, `fnmatch`, `glob`, or any other regex/pattern library; write your own parser and matcher. Standard library only.

The matching semantics are **identical to Python's `re` module** (default flags, `str` patterns) for the dialect defined below. Where this document defines a rule precisely, follow this document.

## Public API

```python
def compile(pattern: str) -> "Pattern": ...

class Pattern:
    def fullmatch(self, s: str) -> "Match | None": ...
    def search(self, s: str) -> "Match | None": ...

class Match:
    def span(self, n: int = 0) -> tuple[int, int]: ...
    def start(self, n: int = 0) -> int: ...
    def end(self, n: int = 0) -> int: ...
    def group(self, n: int = 0) -> "str | None": ...
    def groups(self) -> tuple["str | None", ...]: ...
```

- `compile` parses the pattern and raises `ValueError` for any invalid pattern (listed below). It must raise at `compile` time, never later.
- `fullmatch(s)` returns a `Match` iff the pattern can match the **entire** string `s`; it must keep backtracking until some path ends exactly at `len(s)`.
- `search(s)` returns the match found at the **smallest start index** at which the pattern matches at all (trying starts `0, 1, ..., len(s)`, including `len(s)`), using the priority order below to choose among the matches at that start. The first complete match in priority order wins - it is **not** the longest one.
- Group `0` is the whole match; capturing groups are numbered `1, 2, ...` by the position of their opening parenthesis, left to right (nested groups included).
- `span(n)`, `start(n)`, `end(n)`, `group(n)`: for a group that did not participate in the match, `span` is `(-1, -1)`, `start` and `end` are `-1`, and `group` is `None`. For `n` that is not an integer in `0..number_of_groups` (including negative `n`), raise `IndexError`.
- `groups()` returns a tuple with one entry (`str` or `None`) per capturing group `1..N`; `()` if there are none.
- Inputs and patterns are ASCII. Matches are on exact characters (no case folding, no flags). `\d` is `[0-9]`, `\w` is `[A-Za-z0-9_]`, `\s` is exactly the six characters space, `\t`, `\n`, `\r`, `\f`, `\v`; `\D`, `\W`, `\S` are their complements. Match inputs may be several thousand characters long (up to about 5000), and **must not** hit `RecursionError`, exponential running time, or quadratic-or-worse blow-ups on patterns such as `(a|aa)+$` or `(x+x+)+y` against long non-matching strings.

## Pattern syntax

Any character not mentioned below is an ordinary literal, including `]`, `}`, `-`, `,`, space.

**Atoms**
- `.` matches any single character except `"\n"`.
- `^` matches only at index 0 of the string (there is no multiline mode, and in `search` it still only matches at index 0). `$` matches at the end of the string, and also at `len(s) - 1` when the last character of the string is `"\n"` (so `a$` matches in `"a\n"` with span `(0, 1)`; but `fullmatch` still has to consume the whole string). `^` and `$` are zero-width and may appear anywhere in a pattern. They may **not** be quantified.
- Escapes: `\d \D \w \W \s \S`; `\n` (newline); `\t` (tab); a backslash followed by any ASCII character that is neither a letter nor a digit means that character literally (`\.`, `\\`, `\(`, `\*`, `\[`, `\{`, `\-`, `\/`, `\_`, `\ ` ...). Every other escape (any other letter or digit after the backslash, e.g. `\b \r \A \1 \x41`, or a backslash at the very end of the pattern) raises `ValueError`.
- Character classes `[...]`: a leading `^` negates the class. A `]` that is the first character of the class (right after `[` or `[^`) is a literal `]`. Parse the class body left to right, one item at a time; an item is either a class escape (`\d \D \w \W \s \S`), or a single character (an ordinary character, `\n`, `\t`, or a backslash plus a non-alphanumeric ASCII character; other backslash escapes raise `ValueError`). If a single-character item is followed by `-` and the character after that `-` is **not** `]`, then the three form a range `x-y`: `y` must be a single-character item too and `x <= y` by code point, otherwise `ValueError` (so `[z-a]`, `[a-\d]` are errors). A class-escape item followed by `-` and then something other than `]` also raises `ValueError` (`[\d-z]`). Otherwise `-` is just a literal (e.g. `[-a]`, `[a-]`, `[\d-]`, and the `-` in `[a-c-e]` which comes right after a completed range). Everything else inside a class, including `.`, `*`, `[`, `(`, `^` (not first), is literal. A class that is never closed raises `ValueError`.
- Groups: `( ... )` captures; `(?: ... )` does not capture. Any other `(?...` form (lookahead, named group, flags, comments) raises `ValueError`. Unbalanced parentheses (an unclosed `(`, or a `)` with no matching `(`) raise `ValueError`.
- Alternation `|` has the lowest precedence; any branch may be empty (`a|`, `|a`, `a||b`, `()`, `(|a)`, `(?:)` and the empty pattern are all valid and match the empty string where applicable).

**Quantifiers** (apply to the single preceding atom: a literal, `.`, escape, class or group):
`*` (0..inf), `+` (1..inf), `?` (0..1), `{m}` (exactly m), `{m,}` (m..inf), `{m,n}` (m..n), where `m` and `n` are non-empty strings of decimal digits with no spaces. A quantifier may be followed by one `?` to make it **lazy** (`*?`, `+?`, `??`, `{m,n}?` ...); without it, it is **greedy**. Errors (all `ValueError`):
- a quantifier with nothing to repeat: at the start of the pattern, right after `(`, `(?:` or `|`, or right after `^` or `$`;
- a quantifier directly after another quantifier (including its lazy `?`): `a**`, `a+*`, `a*??`, `a{2}{3}`, and the "possessive" forms `a*+`, `a++`, `a?+`, `a{1,2}+` are all errors;
- `{m,n}` with `m > n`;
- an unescaped `{` that does not start a well-formed `{m}`, `{m,}` or `{m,n}` (e.g. `a{`, `a{x}`, `a{,3}`, `a{1,2`, `{`). An unescaped `}` elsewhere is an ordinary literal.
Counts in tests never exceed 100. `x{0}` and `x{0,0}` match the empty string without ever running `x` (any groups inside it do not participate).

## Matching semantics (this is what makes it identical to `re`)

**Priority order.** The matcher explores alternatives depth-first in this priority order, and the first complete match found wins: alternation branches left to right; a greedy quantifier prefers one more iteration over stopping; a lazy quantifier prefers stopping over one more iteration. If what follows fails, the matcher backtracks into earlier choices (and for `fullmatch`, a path that stops before `len(s)` counts as a failure).

**Quantifier loop rules, exactly.** Consider `X{lo,hi}` reached at some position. The loop keeps a count `c` of completed iterations (starting at 0) and a position `mark` (initially "none") which is the position at which the most recent *optional* iteration started. Then:
1. If `c < lo`: run one iteration of `X` (a *forced* iteration). Forced iterations never look at `mark` and never set it. When the iteration completes, `c += 1` and go to step 1/2 again (even if it matched the empty string).
2. Otherwise (`c >= lo`):
   - **greedy**: if (`hi` is unbounded or `c < hi`) **and** the current position is not equal to `mark`: set `mark` to the current position and run one more iteration (on completion `c += 1` and repeat this step); if that attempt, with all its internal choices, ultimately fails, continue with what follows the quantifier instead, at the current position. If `c == hi` or the current position equals `mark`, simply continue with what follows.
   - **lazy**: first try to continue with what follows the quantifier; only if that fails: if (`hi` is bounded and `c >= hi`) or the current position equals `mark`, this path fails; otherwise set `mark` to the current position and run one more iteration (on completion `c += 1` and repeat this step).

   Consequence: an optional iteration that matches the empty string is **accepted** (it counts, and any captures it made are kept), but no further optional iteration is attempted straight after it. So `(a*)*` on `"aa"` gives group 1 = `""` (the second optional iteration matched empty), `(a|)+` on `"aa"` gives group 1 = `""`, and `(a*)+` on `"b"` matches `""` with group 1 = `""`. A *forced* empty iteration is also accepted and followed by the next step normally. Each time the loop is entered afresh (e.g. an inner loop on the next iteration of an outer loop), `c` is 0 and `mark` is "none" again.

**Captures.**
- A group records the span of its most recent completion. A group inside a quantified part therefore reports its **last iteration** that reached it, e.g. `(a|b)+` on `"ab"` gives group 1 = `"b"`.
- Captures are **not** reset when a new iteration starts: if the last iteration took a branch that does not pass through a group, that group keeps the value from an earlier iteration (`(?:(a)|b)+` on `"ab"` gives group 1 = `"a"`). A group that no executed path passed through is `None`.
- Backtracking restores captures: when the matcher abandons a path and tries an alternative, groups have exactly the values they had at the choice point (nothing leaks from abandoned paths). The reported captures are the ones along the winning path.

## Examples (all verified against `re`)

```
fullmatch("(a|ab)(c|bcd)(d*)", "abcd").groups()   == ("a", "bcd", "")
fullmatch("a*?", "aaa").span()                   == (0, 3)      # laziness never prevents a full match
search("a*?", "aaa").span()                      == (0, 0)
search("(a+)(b+)?", "xaab").groups()             == ("aa", "b")
search("(a|b)*?c", "abc").groups()               == ("b",)
fullmatch("(a*)*", "aa").groups()                == ("",)
fullmatch("(?:(a)|b)+", "ab").groups()           == ("a",)
fullmatch("(a){0}b", "b").groups()               == (None,)
search("$", "ab\n").span()                       == (2, 2)
search("[]a]+", "x]a]").span()                   == (1, 4)
```

Output requirements: reply with **one** Python code block containing the complete module. No explanation outside the code block.
