Write a Python module that implements an arithmetic expression evaluator **without using `eval`, `exec`, `compile`, or the `ast` module** (write a real tokenizer + parser). Standard library only.

Public API:

```python
def evaluate(expr: str) -> int | float: ...
```

Semantics are **identical to Python's own arithmetic expression semantics** for this subset:

- Numbers: integer literals (`3`, `42`) and decimal literals (`3.5`, `.5`, `2.`). No exponent notation (`1e3` is invalid), no underscores, no hex.
- Binary operators: `+  -  *  /  //  %  **`
- Unary operators: `+` and `-` (they may be stacked, e.g. `--3`, `+-+2`)
- Parentheses for grouping. Whitespace (spaces, tabs) between tokens is ignored.
- Precedence, highest to lowest: parentheses; `**` (right-associative); unary `+`/`-`; `*  /  //  %` (left-associative); `+  -` (left-associative).
- As in Python, the operand to the right of `**` may itself carry a unary sign, and `**` binds tighter than a unary operator on its left. So `-2 ** 2 == -4`, `2 ** -1 == 0.5`, `2 ** 3 ** 2 == 512`, `2 ** -2 ** 2 == 0.0625`.
- Result types follow Python: `+ - * // % **` on two ints give an int (except `**` with a negative exponent, which gives a float), `/` always gives a float, and any float operand gives a float. `//` and `%` use Python's floor semantics, including for negative operands and floats.
- Division by zero (`/`, `//`, `%` with a zero right operand) raises `ZeroDivisionError`. `0 ** -1` also raises `ZeroDivisionError`.
- Any malformed input raises `ValueError`: empty or whitespace-only string, unbalanced parentheses, empty parentheses `()`, a dangling operator (`1 +`, `* 2`), two adjacent numbers (`1 2`), an invalid character, a malformed number such as `1..2` or `1.2.3`, a lone `.`.

Output requirements: reply with **one** Python code block containing the complete module (`evaluate` plus any helpers). No explanation outside the code block.
