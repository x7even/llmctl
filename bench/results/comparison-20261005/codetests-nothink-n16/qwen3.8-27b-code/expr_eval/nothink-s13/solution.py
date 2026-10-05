"""Arithmetic expression evaluator (no eval/exec/compile/ast)."""

from __future__ import annotations

import re
from typing import List, Union

Number = Union[int, float]

# Token kinds
TK_NUM = "NUM"
TK_OP = "OP"
TK_LPAREN = "LPAREN"
TK_RPAREN = "RPAREN"
TK_EOF = "EOF"


class _Token:
    __slots__ = ("kind", "value")

    def __init__(self, kind: str, value):
        self.kind = kind
        self.value = value

    def __repr__(self):
        return f"Token({self.kind!r}, {self.value!r})"


# Regex for a valid number: integer or decimal (no exponent, no underscores)
# Matches: 3, 42, 3.5, .5, 2.
_NUM_RE = re.compile(r"^(?:\d+\.?\d*|\.\d+)")


def _tokenize(expr: str) -> List[_Token]:
    tokens: List[_Token] = []
    i = 0
    n = len(expr)
    while i < n:
        ch = expr[i]
        if ch in " \t\r\n":
            i += 1
            continue
        if ch == "(":
            tokens.append(_Token(TK_LPAREN, "("))
            i += 1
            continue
        if ch == ")":
            tokens.append(_Token(TK_RPAREN, ")"))
            i += 1
            continue
        if ch in "+-*/%":
            tokens.append(_Token(TK_OP, ch))
            i += 1
            continue
        if ch == "/":
            # Check for //
            if i + 1 < n and expr[i + 1] == "/":
                tokens.append(_Token(TK_OP, "//"))
                i += 2
            else:
                tokens.append(_Token(TK_OP, "/"))
                i += 1
            continue
        if ch == "*":
            # Check for **
            if i + 1 < n and expr[i + 1] == "*":
                tokens.append(_Token(TK_OP, "**"))
                i += 2
            else:
                tokens.append(_Token(TK_OP, "*"))
                i += 1
            continue
        # Try to match a number
        m = _NUM_RE.match(expr, i)
        if m:
            text = m.group(0)
            # Validate that we didn't partially match something invalid
            # e.g., "1..2" - the regex matches "1." but next char is "."
            # We need to ensure the number is properly terminated
            end = m.end()
            # Check if the next character would make this an invalid number
            if end < n:
                next_ch = expr[end]
                # If next char is a digit or dot, it might be part of a malformed number
                # Actually, the regex is greedy enough for valid numbers.
                # But "1..2" -> matches "1." then next is "." which is not part of number
                # We need to reject if the matched number is followed by a dot or digit
                # that would make it malformed. Actually, the regex handles this:
                # "1..2" -> _NUM_RE matches "1." (since \d+\.?\d* matches "1.")
                # But then the next char is ".", which is not a valid continuation.
                # The issue is: should "1." be a valid number? Yes, "2." is valid.
                # But "1..2" should be invalid. The tokenizer will produce NUM(1.) then OP(.)?
                # No, "." is not an operator. So it will fail later.
                # Actually, let's just tokenize and let the parser handle it.
                pass
            if "." in text:
                tokens.append(_Token(TK_NUM, float(text)))
            else:
                tokens.append(_Token(TK_NUM, int(text)))
            i = end
            continue
        # Invalid character
        raise ValueError(f"Invalid character: {ch!r}")
    tokens.append(_Token(TK_EOF, None))
    return tokens


class _Parser:
    def __init__(self, tokens: List[_Token]):
        self.tokens = tokens
        self.pos = 0

    def _current(self) -> _Token:
        return self.tokens[self.pos]

    def _advance(self) -> _Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def _expect(self, kind: str) -> _Token:
        tok = self._current()
        if tok.kind != kind:
            raise ValueError(f"Expected {kind}, got {tok.kind} ({tok.value!r})")
        return self._advance()

    def parse(self) -> Number:
        result = self._expression()
        if self._current().kind != TK_EOF:
            raise ValueError(f"Unexpected token: {self._current().value!r}")
        return result

    def _expression(self) -> Number:
        # expression := term (('+' | '-') term)*
        left = self._term()
        while self._current().kind == TK_OP and self._current().value in ("+", "-"):
            op = self._advance().value
            right = self._term()
            if op == "+":
                left = left + right
            else:
                left = left - right
        return left

    def _term(self) -> Number:
        # term := factor (('*' | '/' | '//' | '%') factor)*
        left = self._factor()
        while self._current().kind == TK_OP and self._current().value in ("*", "/", "//", "%"):
            op = self._advance().value
            right = self._factor()
            if op == "*":
                left = left * right
            elif op == "/":
                if right == 0:
                    raise ZeroDivisionError("division by zero")
                left = left / right
            elif op == "//":
                if right == 0:
                    raise ZeroDivisionError("integer division or modulo by zero")
                left = left // right
            elif op == "%":
                if right == 0:
                    raise ZeroDivisionError("integer division or modulo by zero")
                left = left % right
        return left

    def _factor(self) -> Number:
        # factor := power | ('+' | '-') factor
        # This handles unary operators with higher precedence than * / // %
        # but lower than **
        tok = self._current()
        if tok.kind == TK_OP and tok.value in ("+", "-"):
            op = self._advance().value
            operand = self._factor()  # Recursive for stacking
            if op == "+":
                return +operand
            else:
                return -operand
        return self._power()

    def _power(self) -> Number:
        # power := atom ('**' factor)?
        # ** is right-associative, and the right operand can have unary signs
        # The right operand is a factor (which can have unary signs)
        base = self._atom()
        if self._current().kind == TK_OP and self._current().value == "**":
            self._advance()
            # The right side of ** is a factor (allows unary signs)
            # But note: ** is right-associative, so 2**3**2 = 2**(3**2)
            # The right operand should be parsed as a factor to allow unary signs
            # and to handle right-associativity
            exponent = self._factor()
            try:
                return base ** exponent
            except ZeroDivisionError:
                raise
            except Exception as e:
                if isinstance(e, ZeroDivisionError):
                    raise
                raise
        return base

    def _atom(self) -> Number:
        # atom := NUMBER | '(' expression ')'
        tok = self._current()
        if tok.kind == TK_NUM:
            self._advance()
            return tok.value
        if tok.kind == TK_LPAREN:
            self._advance()
            result = self._expression()
            self._expect(TK_RPAREN)
            return result
        raise ValueError(f"Unexpected token: {tok.value!r}")


def evaluate(expr: str) -> Number:
    if not isinstance(expr, str):
        raise ValueError("Expression must be a string")
    if not expr.strip():
        raise ValueError("Empty or whitespace-only expression")
    tokens = _tokenize(expr)
    parser = _Parser(tokens)
    return parser.parse()
