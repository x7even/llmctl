"""Arithmetic expression evaluator (tokenizer + recursive descent parser)."""

from __future__ import annotations

import math

__all__ = ["evaluate"]


class _Token:
    __slots__ = ("kind", "value")

    def __init__(self, kind: str, value: object):
        self.kind = kind  # 'NUM', 'OP', 'LPAREN', 'RPAREN', 'EOF'
        self.value = value

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"Token({self.kind!r}, {self.value!r})"


def _tokenize(expr: str) -> list[_Token]:
    tokens: list[_Token] = []
    i = 0
    n = len(expr)
    while i < n:
        ch = expr[i]
        if ch in " \t":
            i += 1
            continue
        if ch == "(":
            tokens.append(_Token("LPAREN", "("))
            i += 1
            continue
        if ch == ")":
            tokens.append(_Token("RPAREN", ")"))
            i += 1
            continue
        if ch in "+-*/%":
            # check for **
            if ch == "*" and i + 1 < n and expr[i + 1] == "*":
                tokens.append(_Token("OP", "**"))
                i += 2
            else:
                tokens.append(_Token("OP", ch))
                i += 1
            continue
        if ch.isdigit() or ch == ".":
            # parse number
            start = i
            seen_dot = False
            if ch == ".":
                seen_dot = True
                i += 1
                while i < n and expr[i].isdigit():
                    i += 1
                # lone '.' is malformed; but we'll validate later
                if i == start + 1:
                    # only '.' with no digits
                    pass
            else:
                while i < n and expr[i].isdigit():
                    i += 1
                if i < n and expr[i] == ".":
                    seen_dot = True
                    i += 1
                    while i < n and expr[i].isdigit():
                        i += 1
            # check for invalid trailing chars like '1..2' or '1.2.3'
            if i < n and (expr[i].isdigit() or expr[i] == "."):
                raise ValueError(f"Malformed number at position {start}")
            num_str = expr[start:i]
            # Validate: must not be empty, must not be just '.'
            if num_str == ".":
                raise ValueError("Lone '.' is not a valid number")
            # Must have at least one digit
            if not any(c.isdigit() for c in num_str):
                raise ValueError(f"Malformed number: {num_str!r}")
            tokens.append(_Token("NUM", num_str))
            continue
        raise ValueError(f"Invalid character {ch!r} at position {i}")
    tokens.append(_Token("EOF", None))
    return tokens


def _parse_number(tok: _Token) -> int | float:
    s = tok.value  # type: ignore[arg-type]
    if "." in s:
        return float(s)
    return int(s)


class _Parser:
    def __init__(self, tokens: list[_Token]):
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> _Token:
        return self.tokens[self.pos]

    def advance(self) -> _Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def expect(self, kind: str) -> _Token:
        tok = self.peek()
        if tok.kind != kind:
            raise ValueError(f"Expected {kind}, got {tok.kind} ({tok.value!r})")
        return self.advance()

    def parse(self) -> int | float:
        if self.peek().kind == "EOF":
            raise ValueError("Empty expression")
        result = self.parse_expr()
        if self.peek().kind != "EOF":
            raise ValueError(f"Unexpected token after expression: {self.peek().value!r}")
        return result

    def parse_expr(self) -> int | float:
        """expr := term (('+' | '-') term)*"""
        left = self.parse_term()
        while self.peek().kind == "OP" and self.peek().value in ("+", "-"):
            op = self.advance().value
            right = self.parse_term()
            if op == "+":
                left = left + right
            else:
                left = left - right
        return left

    def parse_term(self) -> int | float:
        """term := factor (('*' | '/' | '//' | '%') factor)*"""
        left = self.parse_factor()
        while self.peek().kind == "OP" and self.peek().value in ("*", "/", "//", "%"):
            op = self.advance().value
            right = self.parse_factor()
            if op == "*":
                left = left * right
            elif op == "/":
                if right == 0:
                    raise ZeroDivisionError("division by zero")
                left = left / right
            elif op == "//":
                if right == 0:
                    raise ZeroDivisionError("integer division by zero")
                left = math.floor(left / right)
            elif op == "%":
                if right == 0:
                    raise ZeroDivisionError("modulo by zero")
                # Python's % semantics: result has sign of divisor
                left = left - math.floor(left / right) * right
        return left

    def parse_factor(self) -> int | float:
        """factor := power | ('+' | '-') factor"""
        tok = self.peek()
        if tok.kind == "OP" and tok.value in ("+", "-"):
            op = self.advance().value
            operand = self.parse_factor()
            if op == "-":
                return -operand
            return +operand
        return self.parse_power()

    def parse_power(self) -> int | float:
        """power := atom ('**' factor)?   # right-associative, exponent can be unary"""
        base = self.parse_atom()
        if self.peek().kind == "OP" and self.peek().value == "**":
            self.advance()
            # exponent is a factor (can include unary signs)
            exp = self.parse_factor()
            return self._pow(base, exp)
        return base

    def parse_atom(self) -> int | float:
        """atom := NUM | '(' expr ')'"""
        tok = self.peek()
        if tok.kind == "NUM":
            self.advance()
            return _parse_number(tok)
        if tok.kind == "LPAREN":
            self.advance()
            result = self.parse_expr()
            self.expect("RPAREN")
            return result
        raise ValueError(f"Unexpected token: {tok.value!r}")

    @staticmethod
    def _pow(base: int | float, exp: int | float) -> int | float:
        # Handle 0 ** negative -> ZeroDivisionError
        if base == 0 and isinstance(exp, (int, float)) and exp < 0:
            raise ZeroDivisionError("0.0 cannot be raised to a negative power")
        # If both int and exp is non-negative int, result is int
        if isinstance(base, int) and isinstance(exp, int) and exp >= 0:
            return base ** exp
        # Otherwise, use float pow
        return float(base) ** float(exp)


def evaluate(expr: str) -> int | float:
    if not isinstance(expr, str):
        raise ValueError("Expression must be a string")
    tokens = _tokenize(expr)
    parser = _Parser(tokens)
    return parser.parse()
