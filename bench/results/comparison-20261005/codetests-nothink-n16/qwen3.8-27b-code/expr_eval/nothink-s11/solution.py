"""Arithmetic expression evaluator (tokenizer + parser, no eval/exec/compile/ast)."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Token kinds
# ---------------------------------------------------------------------------

_NUM = "NUM"
_PLUS = "+"
_MINUS = "-"
_MUL = "*"
_DIV = "/"
_FLOORDIV = "//"
_MOD = "%"
_POW = "**"
_LPAREN = "("
_RPAREN = ")"


class _Token:
    __slots__ = ("kind", "value")

    def __init__(self, kind: str, value: object) -> None:
        self.kind = kind
        self.value = value

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Token({self.kind!r}, {self.value!r})"


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[_Token]:
    tokens: list[_Token] = []
    i = 0
    n = len(text)

    while i < n:
        ch = text[i]

        # Whitespace (spaces and tabs only, per spec)
        if ch in (" ", "\t"):
            i += 1
            continue

        # Numbers: integer or decimal literals.  No exponent, no underscores,
        # no hex.  Allowed forms: digits, digits '.', digits '.', '.', digits
        # We must reject: lone '.', '1..2', '1.2.3', etc.
        if ch.isdigit():
            start = i
            i += 1
            while i < n and text[i].isdigit():
                i += 1
            # Optional fractional part
            if i < n and text[i] == ".":
                # Ensure the character after '.' is a digit (not another '.')
                if i + 1 < n and text[i + 1].isdigit():
                    i += 1  # consume '.'
                    while i < n and text[i].isdigit():
                        i += 1
                else:
                    # '.' not followed by digit -> malformed (e.g. "1." is
                    # actually valid per spec: "2." is allowed).  Wait, spec
                    # says decimal literals include "2." so "2." IS valid.
                    # Let me re-read: "decimal literals (3.5, .5, 2.)"
                    # So "2." is valid.  But "1.." is not.  And "1.2.3" is not.
                    # So if we see '.' after digits, we consume it and then
                    # expect digits or end-of-number.  If next is '.' again,
                    # that's malformed.
                    # Actually "2." means: digits, then '.', then end (or
                    # non-digit).  So we consume the '.' and then stop if
                    # next char is not a digit.
                    i += 1  # consume the '.'
                    # Now if next is a digit, consume digits; if next is '.'
                    # that's malformed (handled by later check or by the
                    # fact that we'll see another '.' and fail).
                    while i < n and text[i].isdigit():
                        i += 1
                    # After consuming optional digits, check if next is '.'
                    # which would make it malformed like "1.2.3"
                    # Actually no: "1.2.3" -> we'd parse "1.2" then see ".3"
                    # as a separate token? No, the tokenizer sees "1.2.3" and
                    # needs to reject it.  Let's handle: after the first
                    # fractional part, if we encounter another '.', it's bad.
                    # But the loop above already consumed digits after the
                    # first '.'.  If text[i] is now '.', that means we have
                    # something like "1.2.3" -> after "1.2", i points to '.',
                    # which is not a digit, so the while loop stops.  Then we
                    # check: is text[i] == '.'? That would be the second '.'.
                    # We need to reject this.
                    if i < n and text[i] == ".":
                        raise ValueError(
                            f"Malformed number at position {start}: {text[start:i+1]!r}"
                        )
            num_str = text[start:i]
            tokens.append(_Token(_NUM, _parse_number(num_str)))
            continue

        if ch == ".":
            # Must be followed by a digit (e.g. ".5").  Lone "." is invalid.
            if i + 1 >= n or not text[i + 1].isdigit():
                raise ValueError(f"Invalid character '.' at position {i}")
            start = i
            i += 1  # consume '.'
            while i < n and text[i].isdigit():
                i += 1
            # Check for malformed like ".5.3"
            if i < n and text[i] == ".":
                raise ValueError(
                    f"Malformed number at position {start}: {text[start:i+1]!r}"
                )
            num_str = text[start:i]
            tokens.append(_Token(_NUM, _parse_number(num_str)))
            continue

        # Operators
        if ch == "+":
            tokens.append(_Token(_PLUS, "+"))
            i += 1
            continue
        if ch == "-":
            tokens.append(_Token(_MINUS, "-"))
            i += 1
            continue
        if ch == "*":
            if i + 1 < n and text[i + 1] == "*":
                tokens.append(_Token(_POW, "**"))
                i += 2
            else:
                tokens.append(_Token(_MUL, "*"))
                i += 1
            continue
        if ch == "/":
            if i + 1 < n and text[i + 1] == "/":
                tokens.append(_Token(_FLOORDIV, "//"))
                i += 2
            else:
                tokens.append(_Token(_DIV, "/"))
                i += 1
            continue
        if ch == "%":
            tokens.append(_Token(_MOD, "%"))
            i += 1
            continue
        if ch == "(":
            tokens.append(_Token(_LPAREN, "("))
            i += 1
            continue
        if ch == ")":
            tokens.append(_Token(_RPAREN, ")"))
            i += 1
            continue

        raise ValueError(f"Invalid character {ch!r} at position {i}")

    return tokens


def _parse_number(s: str) -> int | float:
    """Parse a numeric literal string into int or float."""
    if "." in s:
        return float(s)
    return int(s)


# ---------------------------------------------------------------------------
# Parser (recursive descent)
#
# Grammar (matching Python precedence):
#
#   expression  := term (('+' | '-') term)*
#   term        := factor (('*' | '/' | '//' | '%') factor)*
#   factor      := ('+' | '-') factor | power
#   power       := atom ('**' factor)?     # right-associative, and the
#                                           # exponent can be a factor
#   atom        := NUMBER | '(' expression ')'
#
# Note: In Python, `**` is right-associative and the right operand of `**`
# can include unary signs.  Also, `-2 ** 2` is parsed as `-(2 ** 2)` because
# unary minus has lower precedence than `**`.  Our grammar handles this:
# `factor` handles unary, and `power` calls `factor` for its exponent, so
# `2 ** -1` works.  But `-2 ** 2`: the top-level expression sees `-` as a
# unary in `factor`, which then calls `power`, which parses `2 ** 2`, and
# the unary minus applies to the whole result.  This matches Python.
# ---------------------------------------------------------------------------

class _Parser:
    def __init__(self, tokens: list[_Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> _Token | None:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def advance(self) -> _Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def expect(self, kind: str) -> _Token:
        tok = self.peek()
        if tok is None or tok.kind != kind:
            expected = kind
            found = tok.kind if tok else "end of input"
            raise ValueError(f"Expected {expected!r}, got {found!r}")
        return self.advance()

    def parse(self) -> int | float:
        if not self.tokens:
            raise ValueError("Empty expression")
        result = self.expression()
        if self.pos != len(self.tokens):
            tok = self.tokens[self.pos]
            raise ValueError(f"Unexpected token {tok.kind!r} at position {self.pos}")
        return result

    def expression(self) -> int | float:
        """expression := term (('+' | '-') term)*"""
        left = self.term()
        while True:
            tok = self.peek()
            if tok is None:
                break
            if tok.kind == _PLUS:
                self.advance()
                right = self.term()
                left = left + right
            elif tok.kind == _MINUS:
                self.advance()
                right = self.term()
                left = left - right
            else:
                break
        return left

    def term(self) -> int | float:
        """term := factor (('*' | '/' | '//' | '%') factor)*"""
        left = self.factor()
        while True:
            tok = self.peek()
            if tok is None:
                break
            if tok.kind == _MUL:
                self.advance()
                right = self.factor()
                left = left * right
            elif tok.kind == _DIV:
                self.advance()
                right = self.factor()
                if right == 0:
                    raise ZeroDivisionError("division by zero")
                left = left / right
            elif tok.kind == _FLOORDIV:
                self.advance()
                right = self.factor()
                if right == 0:
                    raise ZeroDivisionError("integer division or modulo by zero")
                left = left // right
            elif tok.kind == _MOD:
                self.advance()
                right = self.factor()
                if right == 0:
                    raise ZeroDivisionError("integer modulo by zero")
                left = left % right
            else:
                break
        return left

    def factor(self) -> int | float:
        """factor := ('+' | '-') factor | power"""
        tok = self.peek()
        if tok is not None and tok.kind == _PLUS:
            self.advance()
            return +self.factor()
        if tok is not None and tok.kind == _MINUS:
            self.advance()
            return -self.factor()
        return self.power()

    def power(self) -> int | float:
        """power := atom ('**' factor)?   (right-associative)"""
        base = self.atom()
        tok = self.peek()
        if tok is not None and tok.kind == _POW:
            self.advance()
            # The exponent is a factor, which allows unary signs and
            # further ** (right-associative).
            exponent = self.factor()
            return _pow(base, exponent)
        return base

    def atom(self) -> int | float:
        """atom := NUMBER | '(' expression ')'"""
        tok = self.peek()
        if tok is None:
            raise ValueError("Unexpected end of input")
        if tok.kind == _NUM:
            self.advance()
            return tok.value  # type: ignore[return-value]
        if tok.kind == _LPAREN:
            self.advance()
            result = self.expression()
            self.expect(_RPAREN)
            return result
        # Dangling operator or unexpected token
        raise ValueError(f"Unexpected token {tok.kind!r}")


def _pow(base: int | float, exponent: int | float) -> int | float:
    """Compute base ** exponent with Python semantics."""
    # Check for 0 ** negative
    if base == 0 and isinstance(exponent, (int, float)) and exponent < 0:
        raise ZeroDivisionError("0.0 cannot be raised to a negative power")
    # If both are int and exponent is non-negative int, result is int.
    # If exponent is negative int, result is float.
    # If either is float, result is float.
    if isinstance(base, int) and isinstance(exponent, int):
        if exponent >= 0:
            return base ** exponent
        else:
            # Negative exponent with int base -> float
            return base ** exponent  # Python returns float for this
    # Otherwise, use ** which handles floats correctly
    return base ** exponent


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate(expr: str) -> int | float:
    """Evaluate an arithmetic expression and return the result.

    Supports: integer and decimal literals, binary operators + - * / // % **,
    unary + and -, parentheses.  Semantics match Python for this subset.
    """
    if not isinstance(expr, str):
        raise ValueError("Expression must be a string")
    stripped = expr.strip()
    if not stripped:
        raise ValueError("Empty expression")
    tokens = _tokenize(expr)
    if not tokens:
        raise ValueError("Empty expression")
    parser = _Parser(tokens)
    return parser.parse()
