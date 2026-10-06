"""Arithmetic expression evaluator (tokenizer + recursive-descent parser).

Implements Python's arithmetic semantics for the supported subset without
using eval/exec/compile/ast.
"""

from __future__ import annotations

import math
import re
from typing import List, Tuple, Union

Number = Union[int, float]


class _Tokenizer:
    """Tokenizes an arithmetic expression string."""

    _TOKEN_RE = re.compile(
        r"""
        (?P<ws>[ \t]+)
      | (?P<number>\d+\.\d+|\d+\.|\.\d+|\d+)
      | (?P<op>\*\*|//|\+|-|\*|/|%)
      | (?P<lparen>\()
      | (?P<rparen>\))
        """,
        re.VERBOSE,
    )

    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0
        self.tokens: List[Tuple[str, str]] = []
        self._tokenize()

    def _tokenize(self) -> None:
        text = self.text
        n = len(text)
        i = 0
        while i < n:
            m = self._TOKEN_RE.match(text, i)
            if m is None:
                # Check if it's whitespace we can skip
                if text[i] in " \t":
                    i += 1
                    continue
                raise ValueError(f"Invalid character {text[i]!r} at position {i}")
            kind = m.lastgroup
            value = m.group()
            if kind == "ws":
                i = m.end()
                continue
            self.tokens.append((kind, value))
            i = m.end()
        # Add end marker
        self.tokens.append(("end", ""))

    def peek(self) -> Tuple[str, str]:
        return self.tokens[self.pos]

    def advance(self) -> Tuple[str, str]:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok


def _parse_number(text: str) -> Number:
    """Parse a numeric literal string into int or float."""
    if "." in text:
        return float(text)
    return int(text)


def _make_evaluator(tokens: List[Tuple[str, str]]):
    """Create a recursive-descent parser/evaluator over the token list."""

    pos = [0]

    def peek() -> Tuple[str, str]:
        return tokens[pos[0]]

    def advance() -> Tuple[str, str]:
        tok = tokens[pos[0]]
        pos[0] += 1
        return tok

    def parse_expression() -> Number:
        """expression := additive"""
        return parse_additive()

    def parse_additive() -> Number:
        """additive := multiplicative (('+' | '-') multiplicative)*"""
        left = parse_multiplicative()
        while True:
            kind, value = peek()
            if kind == "op" and value in ("+", "-"):
                advance()
                right = parse_multiplicative()
                if value == "+":
                    left = left + right
                else:
                    left = left - right
            else:
                break
        return left

    def parse_multiplicative() -> Number:
        """multiplicative := power (('*' | '/' | '//' | '%') power)*"""
        left = parse_power()
        while True:
            kind, value = peek()
            if kind == "op" and value in ("*", "/", "//", "%"):
                advance()
                right = parse_power()
                if value == "*":
                    left = left * right
                elif value == "/":
                    if right == 0:
                        raise ZeroDivisionError("division by zero")
                    left = left / right
                elif value == "//":
                    if right == 0:
                        raise ZeroDivisionError("integer division or modulo by zero")
                    left = left // right
                elif value == "%":
                    if right == 0:
                        raise ZeroDivisionError("integer division or modulo by zero")
                    left = left % right
            else:
                break
        return left

    def parse_power() -> Number:
        """power := unary ('**' power)?   # right-associative"""
        base = parse_unary()
        kind, value = peek()
        if kind == "op" and value == "**":
            advance()
            # Right-associative: parse the exponent as a power (not unary)
            # In Python, -2 ** 2 is -(2**2), so the base of ** is unary,
            # but the exponent is power (which includes unary on the right).
            # Actually in Python grammar: power := primary ['**' u_expr]
            # where u_expr := ('+'|'-')* power
            # So the right side of ** is a unary expression that can be a power.
            # Let me re-check: -2 ** 2 = -(2**2) = -4
            # 2 ** -2 = 0.25
            # 2 ** 3 ** 2 = 2 ** (3 ** 2) = 512
            # So the right operand of ** is parsed as a "power" which itself
            # can have unary operators. In Python's grammar:
            # power: (await_expr | primary) ['**' u_expr]
            # u_expr: ('+' | '-' | '~') u_expr | power
            # So the right side of ** is a u_expr, which is unary operators
            # followed by a power.
            exponent = parse_unary()
            # Handle ** with negative exponent producing float
            if isinstance(base, int) and isinstance(exponent, int) and exponent < 0:
                if base == 0:
                    raise ZeroDivisionError("0.0 cannot be raised to a negative power")
                left = float(base) ** float(exponent)
            else:
                try:
                    left = base ** exponent
                except ZeroDivisionError:
                    raise ZeroDivisionError("0.0 cannot be raised to a negative power")
        return left

    def parse_unary() -> Number:
        """unary := ('+' | '-')* power"""
        while True:
            kind, value = peek()
            if kind == "op" and value in ("+", "-"):
                advance()
                operand = parse_unary()
                if value == "-":
                    operand = -operand
                # '+' is a no-op
            else:
                break
        # Now parse the base (which is a power, but since we're in unary,
        # the base is a primary/parenthesized expression)
        return parse_primary()

    def parse_primary() -> Number:
        """primary := NUMBER | '(' expression ')'"""
        kind, value = peek()
        if kind == "number":
            advance()
            return _parse_number(value)
        if kind == "lparen":
            advance()
            result = parse_expression()
            kind2, value2 = peek()
            if kind2 != "rparen":
                raise ValueError("Expected ')' but found " + repr(value2) if value2 else "end of input")
            advance()
            return result
        raise ValueError(f"Unexpected token {value!r}" if value else "Unexpected end of input")

    def evaluate() -> Number:
        result = parse_expression()
        kind, value = peek()
        if kind != "end":
            raise ValueError(f"Unexpected token {value!r}" if value else "Unexpected end of input")
        return result

    return evaluate


def evaluate(expr: str) -> Number:
    """Evaluate an arithmetic expression string and return int or float.

    Raises ValueError for malformed input and ZeroDivisionError for division
    by zero.
    """
    if not expr or not expr.strip():
        raise ValueError("Empty expression")

    tokenizer = _Tokenizer(expr)
    if not tokenizer.tokens or tokenizer.tokens[0] == ("end", ""):
        raise ValueError("Empty expression")

    # Check for empty parentheses
    i = 0
    while i < len(tokenizer.tokens):
        kind, value = tokenizer.tokens[i]
        if kind == "lparen":
            if i + 1 < len(tokenizer.tokens) and tokenizer.tokens[i + 1][0] == "rparen":
                raise ValueError("Empty parentheses")
        i += 1

    evaluator = _make_evaluator(tokenizer.tokens)
    return evaluator()
