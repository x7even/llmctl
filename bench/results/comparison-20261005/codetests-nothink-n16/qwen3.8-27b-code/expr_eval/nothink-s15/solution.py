"""Arithmetic expression evaluator with a real tokenizer + parser."""

from __future__ import annotations

import math
from typing import Union

Number = Union[int, float]


class _Token:
    __slots__ = ("kind", "value", "pos")

    def __init__(self, kind: str, value: object, pos: int):
        self.kind = kind  # 'num', 'op', 'lparen', 'rparen', 'end'
        self.value = value
        self.pos = pos

    def __repr__(self) -> str:
        return f"_Token({self.kind!r}, {self.value!r}, {self.pos})"


def _tokenize(expr: str) -> list[_Token]:
    tokens: list[_Token] = []
    i = 0
    n = len(expr)
    while i < n:
        c = expr[i]
        if c in " \t\r\n":
            i += 1
            continue
        if c == "(":
            tokens.append(_Token("lparen", c, i))
            i += 1
        elif c == ")":
            tokens.append(_Token("rparen", c, i))
            i += 1
        elif c in "+-*/%":
            # check for //
            if c == "/" and i + 1 < n and expr[i + 1] == "/":
                tokens.append(_Token("op", "//", i))
                i += 2
            else:
                tokens.append(_Token("op", c, i))
                i += 1
        elif c == "*":
            # check for **
            if i + 1 < n and expr[i + 1] == "*":
                tokens.append(_Token("op", "**", i))
                i += 2
            else:
                tokens.append(_Token("op", "*", i))
                i += 1
        elif c.isdigit() or c == ".":
            # parse a number
            start = i
            seen_dot = False
            seen_digit = False
            while i < n:
                ch = expr[i]
                if ch.isdigit():
                    seen_digit = True
                    i += 1
                elif ch == "." and not seen_dot:
                    seen_dot = True
                    i += 1
                else:
                    break
            if not seen_digit:
                raise ValueError(f"Invalid number at position {start}: '{expr[start:i]}'")
            text = expr[start:i]
            if seen_dot:
                value: Number = float(text)
            else:
                value = int(text)
            tokens.append(_Token("num", value, start))
        else:
            raise ValueError(f"Invalid character at position {i}: {c!r}")
    tokens.append(_Token("end", None, n))
    return tokens


class _Parser:
    def __init__(self, tokens: list[_Token]):
        self.tokens = tokens
        self.pos = 0

    def _peek(self) -> _Token:
        return self.tokens[self.pos]

    def _advance(self) -> _Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def _expect(self, kind: str, value: object = None) -> _Token:
        tok = self._peek()
        if tok.kind != kind or (value is not None and tok.value != value):
            raise ValueError(f"Expected {kind} {value!r} but got {tok.kind} {tok.value!r} at position {tok.pos}")
        return self._advance()

    def parse(self) -> Number:
        result = self._expression()
        tok = self._peek()
        if tok.kind != "end":
            raise ValueError(f"Unexpected token {tok.kind} {tok.value!r} at position {tok.pos}")
        return result

    def _expression(self) -> Number:
        # expression := term (('+' | '-') term)*
        left = self._term()
        while True:
            tok = self._peek()
            if tok.kind == "op" and tok.value in ("+", "-"):
                self._advance()
                right = self._term()
                if tok.value == "+":
                    left = left + right
                else:
                    left = left - right
            else:
                break
        return left

    def _term(self) -> Number:
        # term := factor (('*' | '/' | '//' | '%') factor)*
        left = self._factor()
        while True:
            tok = self._peek()
            if tok.kind == "op" and tok.value in ("*", "/", "//", "%"):
                self._advance()
                right = self._factor()
                if tok.value == "*":
                    left = left * right
                elif tok.value == "/":
                    if right == 0:
                        raise ZeroDivisionError("division by zero")
                    left = left / right
                elif tok.value == "//":
                    if right == 0:
                        raise ZeroDivisionError("integer division or modulo by zero")
                    left = left // right
                elif tok.value == "%":
                    if right == 0:
                        raise ZeroDivisionError("integer division or modulo by zero")
                    left = left % right
            else:
                break
        return left

    def _factor(self) -> Number:
        # factor := ('+' | '-')* power
        # Handle unary operators: they bind tighter than * / // % but looser than **
        # In Python, -2 ** 2 == -4, so unary minus applies to the result of 2 ** 2
        # But 2 ** -2 == 0.25, so the exponent can have a unary minus
        # The grammar: factor := power | ('+' | '-') factor
        # Wait, that's not quite right. Let me think again.
        # Python's grammar:
        # power := primary ['**' u_expr]
        # u_expr := power | '-' u_expr | '+' u_expr
        # So unary minus/plus is at the u_expr level, which is below power in the precedence
        # Actually, in Python:
        # -2 ** 2 = -(2**2) = -4
        # 2 ** -2 = 2 ** (-2) = 0.25
        # So the right operand of ** can be a u_expr (which allows unary)
        # But the left operand of ** is a power, which is a primary
        # And unary applies to the whole power expression
        # 
        # Let me restructure:
        # factor := u_expr
        # u_expr := ('+' | '-') u_expr | power
        # power := primary ['**' u_expr]
        # primary := number | '(' expression ')'

        # Actually, let me check the precedence more carefully:
        # -2 ** 2: unary minus has lower precedence than **, so it's -(2**2)
        # But 2 ** -2: the -2 is the exponent, and unary minus applies to the 2
        # So the right side of ** accepts unary expressions
        # The left side of ** is a primary (no unary)
        # And unary can wrap a power expression
        #
        # So:
        # u_expr := ('+' | '-') u_expr | power
        # power := primary ['**' u_expr]
        #
        # Let me verify: -2 ** 2
        # u_expr: sees '-', so it's - u_expr
        # u_expr: power
        # power: primary=2, then ** u_expr
        # u_expr: power: primary=2, no **
        # So power = 2 ** 2 = 4
        # u_expr = -4
        # Correct!
        #
        # 2 ** -2:
        # u_expr: power
        # power: primary=2, then ** u_expr
        # u_expr: sees '-', so - u_expr
        # u_expr: power: primary=2
        # So u_expr = -2
        # power = 2 ** (-2) = 0.25
        # Correct!
        #
        # 2 ** 3 ** 2:
        # u_expr: power
        # power: primary=2, then ** u_expr
        # u_expr: power
        # power: primary=3, then ** u_expr
        # u_expr: power: primary=2
        # So inner power = 3 ** 2 = 9
        # outer power = 2 ** 9 = 512
        # Correct! (right-associative)
        #
        # 2 ** -2 ** 2:
        # u_expr: power
        # power: primary=2, then ** u_expr
        # u_expr: sees '-', so - u_expr
        # u_expr: power
        # power: primary=2, then ** u_expr
        # u_expr: power: primary=2
        # So inner power = 2 ** 2 = 4
        # u_expr = -4
        # outer power = 2 ** (-4) = 0.0625
        # Correct!

        return self._u_expr()

    def _u_expr(self) -> Number:
        # u_expr := ('+' | '-') u_expr | power
        tok = self._peek()
        if tok.kind == "op" and tok.value in ("+", "-"):
            self._advance()
            operand = self._u_expr()
            if tok.value == "-":
                return -operand
            else:
                return operand
        return self._power()

    def _power(self) -> Number:
        # power := primary ['**' u_expr]
        left = self._primary()
        tok = self._peek()
        if tok.kind == "op" and tok.value == "**":
            self._advance()
            right = self._u_expr()
            if isinstance(left, int) and isinstance(right, int) and right < 0:
                if left == 0:
                    raise ZeroDivisionError("0.0 cannot be raised to a negative power")
                # int ** negative int -> float
                return float(left) ** right
            else:
                if left == 0 and right < 0:
                    raise ZeroDivisionError("0.0 cannot be raised to a negative power")
                return left ** right
        return left

    def _primary(self) -> Number:
        # primary := number | '(' expression ')'
        tok = self._peek()
        if tok.kind == "num":
            self._advance()
            return tok.value
        if tok.kind == "lparen":
            self._advance()
            result = self._expression()
            self._expect("rparen")
            return result
        raise ValueError(f"Unexpected token {tok.kind} {tok.value!r} at position {tok.pos}")


def evaluate(expr: str) -> int | float:
    if not expr or not expr.strip():
        raise ValueError("Empty expression")
    tokens = _tokenize(expr)
    # Check for empty parentheses or other issues via parsing
    parser = _Parser(tokens)
    return parser.parse()
