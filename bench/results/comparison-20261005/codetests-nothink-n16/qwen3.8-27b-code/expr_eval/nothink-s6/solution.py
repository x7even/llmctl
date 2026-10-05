"""Arithmetic expression evaluator (no eval/exec/compile/ast)."""

from __future__ import annotations

import math
import re
from typing import List, Tuple


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

# Token kinds
_NUM = "NUM"
_OP = "OP"
_LP = "LP"
_RP = "RP"
_EOF = "EOF"

# Number pattern: integer or decimal (no exponent, no underscores, no hex)
_NUM_RE = re.compile(r"^\d+\.?\d*|^\.\d+")

_OPERATORS = ("**", "//", "+", "-", "*", "/", "%")


def _tokenize(expr: str) -> List[Tuple[str, str]]:
    """Convert *expr* into a list of (kind, value) tokens.

    Raises ValueError on any invalid character or malformed number.
    """
    tokens: List[Tuple[str, str]] = []
    i = 0
    n = len(expr)

    while i < n:
        ch = expr[i]

        # Skip whitespace
        if ch in " \t":
            i += 1
            continue

        # Parentheses
        if ch == "(":
            tokens.append((_LP, "("))
            i += 1
            continue
        if ch == ")":
            tokens.append((_RP, ")"))
            i += 1
            continue

        # Numbers
        m = _NUM_RE.match(expr, i)
        if m:
            num_str = m.group(0)
            # Validate that the number is well-formed
            # The regex handles: \d+\.?\d*  or  \.\d+
            # But we must reject things like "1..2" or "1.2.3"
            # The regex is anchored at position i and matches greedily,
            # so "1..2" would match "1." and then the next char is "."
            # which would be caught as an invalid character.
            # However, "1.2.3" would match "1.2" then "." is invalid.
            # Let's also check that we don't have a trailing dot issue.
            # Actually the regex \d+\.?\d* matches "1." which is valid (2. is valid per spec).
            # And \.\d+ matches ".5".
            # But what about "1..2"? Regex matches "1." starting at i.
            # Then next iteration sees "." which is not a valid start.
            # So it will raise ValueError. Good.
            # What about a lone "."? Regex \.\d+ requires at least one digit after dot.
            # \d+\.?\d* requires at least one digit before. So lone "." won't match.
            tokens.append((_NUM, num_str))
            i += len(num_str)
            continue

        # Operators
        matched = False
        for op in _OPERATORS:
            if expr.startswith(op, i):
                tokens.append((_OP, op))
                i += len(op)
                matched = True
                break
        if matched:
            continue

        # Invalid character
        raise ValueError(f"Invalid character: {ch!r} at position {i}")

    tokens.append((_EOF, ""))
    return tokens


# ---------------------------------------------------------------------------
# Parser / Evaluator (recursive descent)
# ---------------------------------------------------------------------------
#
# Grammar (precedence from lowest to highest):
#
#   expr      := term (('+' | '-') term)*
#   term      := factor (('*' | '/' | '//' | '%') factor)*
#   factor    := ('+' | '-') factor | power
#   power     := atom ('**' factor)?     # right-associative, exponent can be a factor
#   atom      := NUM | '(' expr ')'
#
# Note on precedence:
#   ** binds tighter than unary on the left, but the right side of **
#   can include unary operators. So:
#     -2 ** 2  ->  -(2 ** 2)  = -4
#     2 ** -1  ->  2 ** (-1)  = 0.5
#     2 ** 3 ** 2  ->  2 ** (3 ** 2)  = 512
#
# The grammar above handles this:
#   factor := ('+'|'-') factor | power
#   power := atom ('**' factor)?
#
# So in "-2 ** 2":
#   factor sees '-', then parses factor recursively.
#   The recursive factor sees '2', then power: atom=2, then sees '**',
#   then parses factor for the exponent: factor -> power -> atom=2.
#   So it computes 2 ** 2 = 4, then unary minus gives -4. Correct.
#
# In "2 ** -1":
#   factor -> power: atom=2, sees '**', parses factor for exponent.
#   factor sees '-', then factor -> power -> atom=1. So exponent = -1.
#   2 ** -1 = 0.5. Correct.
#
# In "2 ** 3 ** 2":
#   factor -> power: atom=2, sees '**', parses factor for exponent.
#   factor -> power: atom=3, sees '**', parses factor for exponent.
#   factor -> power: atom=2, no '**'. So 3 ** 2 = 9.
#   Then 2 ** 9 = 512. Correct.


class _Parser:
    def __init__(self, tokens: List[Tuple[str, str]]):
        self.tokens = tokens
        self.pos = 0

    def _peek(self) -> Tuple[str, str]:
        return self.tokens[self.pos]

    def _advance(self) -> Tuple[str, str]:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def _expect(self, kind: str, value: str | None = None) -> Tuple[str, str]:
        tok = self._peek()
        if tok[0] != kind:
            raise ValueError(
                f"Expected {kind} but got {tok[0]} ({tok[1]!r})"
            )
        if value is not None and tok[1] != value:
            raise ValueError(
                f"Expected {value!r} but got {tok[1]!r}"
            )
        return self._advance()

    def parse(self) -> int | float:
        result = self._expr()
        if self._peek()[0] != _EOF:
            tok = self._peek()
            raise ValueError(f"Unexpected token {tok[1]!r}")
        return result

    def _expr(self) -> int | float:
        """expr := term (('+' | '-') term)*"""
        result = self._term()
        while True:
            tok = self._peek()
            if tok[0] == _OP and tok[1] in ("+", "-"):
                self._advance()
                right = self._term()
                if tok[1] == "+":
                    result = result + right
                else:
                    result = result - right
            else:
                break
        return result

    def _term(self) -> int | float:
        """term := factor (('*' | '/' | '//' | '%') factor)*"""
        result = self._factor()
        while True:
            tok = self._peek()
            if tok[0] == _OP and tok[1] in ("*", "/", "//", "%"):
                self._advance()
                right = self._factor()
                if tok[1] == "*":
                    result = result * right
                elif tok[1] == "/":
                    if right == 0:
                        raise ZeroDivisionError("division by zero")
                    result = result / right
                elif tok[1] == "//":
                    if right == 0:
                        raise ZeroDivisionError("integer division or modulo by zero")
                    result = result // right
                elif tok[1] == "%":
                    if right == 0:
                        raise ZeroDivisionError("integer division or modulo by zero")
                    result = result % right
            else:
                break
        return result

    def _factor(self) -> int | float:
        """factor := ('+' | '-') factor | power"""
        tok = self._peek()
        if tok[0] == _OP and tok[1] in ("+", "-"):
            self._advance()
            operand = self._factor()
            if tok[1] == "+":
                return +operand
            else:
                return -operand
        return self._power()

    def _power(self) -> int | float:
        """power := atom ('**' factor)?"""
        base = self._atom()
        tok = self._peek()
        if tok[0] == _OP and tok[1] == "**":
            self._advance()
            exponent = self._factor()
            return self._pow(base, exponent)
        return base

    def _pow(self, base: int | float, exponent: int | float) -> int | float:
        """Compute base ** exponent with Python semantics."""
        # Check for zero division: 0 ** negative number
        if base == 0 and exponent < 0:
            raise ZeroDivisionError("0.0 cannot be raised to a negative power")

        # If both are ints and exponent is non-negative int, result is int
        if isinstance(base, int) and isinstance(exponent, int) and exponent >= 0:
            return base ** exponent

        # Otherwise, use float semantics
        # Convert to float for computation
        base_f = float(base)
        exp_f = float(exponent)

        # Handle the case where result should be int
        # Python: int ** int (non-negative) -> int
        # int ** negative int -> float
        # float ** anything -> float

        # For negative exponents with int base, Python returns float
        # For positive exponents with int base and int exponent, Python returns int

        # Let's use Python's built-in pow which handles all these cases
        # But we need to be careful: 0 ** 0 is 1 in Python
        try:
            return base ** exponent
        except ZeroDivisionError:
            raise
        except Exception as e:
            raise ValueError(f"Error in exponentiation: {e}")

    def _atom(self) -> int | float:
        """atom := NUM | '(' expr ')'"""
        tok = self._peek()
        if tok[0] == _NUM:
            self._advance()
            return self._parse_number(tok[1])
        if tok[0] == _LP:
            self._advance()
            result = self._expr()
            self._expect(_RP, ")")
            return result
        raise ValueError(f"Unexpected token {tok[1]!r}")

    @staticmethod
    def _parse_number(s: str) -> int | float:
        """Parse a number string into int or float."""
        if "." in s:
            return float(s)
        return int(s)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate(expr: str) -> int | float:
    """Evaluate an arithmetic expression.

    Supports: integer and decimal literals, + - * / // % **, unary + and -,
    parentheses. Whitespace between tokens is ignored.

    Raises:
        ValueError: for malformed input.
        ZeroDivisionError: for division by zero or 0 ** negative.
    """
    if not isinstance(expr, str):
        raise ValueError("Input must be a string")

    if not expr.strip():
        raise ValueError("Empty expression")

    tokens = _tokenize(expr)
    parser = _Parser(tokens)
    return parser.parse()
