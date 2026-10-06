"""Arithmetic expression evaluator (no eval/exec/compile/ast)."""

from __future__ import annotations

import re
from typing import List, Tuple

# Token kinds
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
_EOF = "EOF"

# Tokenizer

_TOKEN_SPEC = [
    ("NUMBER", r"(?:\d+\.?\d*|\.\d+)"),
    ("FLOORDIV", r"//"),
    ("POW", r"\*\*"),
    ("MUL", r"\*"),
    ("DIV", r"/"),
    ("MOD", r"%"),
    ("PLUS", r"\+"),
    ("MINUS", r"-"),
    ("LPAREN", r"\("),
    ("RPAREN", r"\)"),
    ("SKIP", r"[ \t]+"),
    ("INVALID", r"."),
]

_MASTER_RE = re.compile("|".join(f"(?P<{name}>{pattern})" for name, pattern in _TOKEN_SPEC))


def _tokenize(expr: str) -> List[Tuple[str, str]]:
    tokens: List[Tuple[str, str]] = []
    pos = 0
    n = len(expr)
    while pos < n:
        m = _MASTER_RE.match(expr, pos)
        if not m:
            raise ValueError(f"Invalid character at position {pos}")
        kind = m.lastgroup
        value = m.group()
        pos = m.end()
        if kind == "SKIP":
            continue
        if kind == "INVALID":
            raise ValueError(f"Invalid character: {value!r}")
        if kind == "NUMBER":
            # Validate: ensure it's a proper number (the regex already handles this,
            # but let's be safe about things like "1..2" which won't match as a single NUMBER)
            tokens.append((_NUM, value))
        elif kind == "FLOORDIV":
            tokens.append((_FLOORDIV, value))
        elif kind == "POW":
            tokens.append((_POW, value))
        elif kind == "MUL":
            tokens.append((_MUL, value))
        elif kind == "DIV":
            tokens.append((_DIV, value))
        elif kind == "MOD":
            tokens.append((_MOD, value))
        elif kind == "PLUS":
            tokens.append((_PLUS, value))
        elif kind == "MINUS":
            tokens.append((_MINUS, value))
        elif kind == "LPAREN":
            tokens.append((_LPAREN, value))
        elif kind == "RPAREN":
            tokens.append((_RPAREN, value))
    tokens.append((_EOF, ""))
    return tokens


# Parser using recursive descent

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

    def _expect(self, kind: str) -> str:
        tok = self._advance()
        if tok[0] != kind:
            raise ValueError(f"Expected {kind}, got {tok[0]}")
        return tok[1]

    def parse(self) -> int | float:
        if self._peek()[0] == _EOF:
            raise ValueError("Empty expression")
        result = self._parse_expression()
        if self._peek()[0] != _EOF:
            raise ValueError(f"Unexpected token: {self._peek()}")
        return result

    def _parse_expression(self) -> int | float:
        # expression := additive
        return self._parse_additive()

    def _parse_additive(self) -> int | float:
        # additive := multiplicative (('+' | '-') multiplicative)*
        left = self._parse_multiplicative()
        while self._peek()[0] in (_PLUS, _MINUS):
            op = self._advance()[0]
            right = self._parse_multiplicative()
            if op == _PLUS:
                left = left + right
            else:
                left = left - right
        return left

    def _parse_multiplicative(self) -> int | float:
        # multiplicative := power (('*' | '/' | '//' | '%') power)*
        left = self._parse_power()
        while self._peek()[0] in (_MUL, _DIV, _FLOORDIV, _MOD):
            op = self._advance()[0]
            right = self._parse_power()
            if op == _MUL:
                left = left * right
            elif op == _DIV:
                if right == 0:
                    raise ZeroDivisionError("division by zero")
                left = left / right
            elif op == _FLOORDIV:
                if right == 0:
                    raise ZeroDivisionError("integer division by zero")
                left = left // right
            elif op == _MOD:
                if right == 0:
                    raise ZeroDivisionError("modulo by zero")
                left = left % right
        return left

    def _parse_power(self) -> int | float:
        # power := unary ('**' power)?   # right-associative
        base = self._parse_unary()
        if self._peek()[0] == _POW:
            self._advance()
            # Right-associative: the exponent is another power expression
            # But note: in Python, -2 ** 2 is -(2**2), and 2 ** -2 is 2 ** (-2)
            # The grammar here: power := unary ('**' power)?
            # This means the base is a unary expression, and the exponent is a full power expression
            # This correctly handles 2 ** -2 because -2 is parsed as unary in the exponent's power
            exponent = self._parse_power()
            return self._pow(base, exponent)
        return base

    def _pow(self, base: int | float, exponent: int | float) -> int | float:
        # Handle 0 ** negative
        if base == 0 and exponent < 0:
            raise ZeroDivisionError("0.0 cannot be raised to a negative power")
        # Check if result should be int
        if isinstance(base, int) and isinstance(exponent, int):
            if exponent >= 0:
                return base ** exponent
            else:
                # Negative exponent with int base gives float
                return float(base) ** float(exponent)
        # If either is float, result is float
        return float(base) ** float(exponent)

    def _parse_unary(self) -> int | float:
        # unary := ('+' | '-')* primary
        sign = 1
        while self._peek()[0] in (_PLUS, _MINUS):
            op = self._advance()[0]
            if op == _MINUS:
                sign = -sign
        value = self._parse_primary()
        return sign * value

    def _parse_primary(self) -> int | float:
        # primary := NUMBER | '(' expression ')'
        tok = self._peek()
        if tok[0] == _NUM:
            self._advance()
            num_str = tok[1]
            if "." in num_str:
                return float(num_str)
            return int(num_str)
        elif tok[0] == _LPAREN:
            self._advance()
            value = self._parse_expression()
            self._expect(_RPAREN)
            return value
        else:
            raise ValueError(f"Unexpected token: {tok}")


def evaluate(expr: str) -> int | float:
    """Evaluate an arithmetic expression string.

    Supports: integers, floats, +, -, *, /, //, %, **, unary +/-, parentheses.
    Raises ValueError for malformed input, ZeroDivisionError for division by zero.
    """
    if not expr or not expr.strip():
        raise ValueError("Empty expression")

    tokens = _tokenize(expr)
    parser = _Parser(tokens)
    return parser.parse()
