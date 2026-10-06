"""Arithmetic expression evaluator (no eval/exec/compile/ast)."""

from __future__ import annotations

# Token kinds
_NUM = "NUM"
_OP = "OP"
_LP = "LP"
_RP = "RP"
_EOF = "EOF"


class _Token:
    __slots__ = ("kind", "value", "pos")

    def __init__(self, kind: str, value, pos: int) -> None:
        self.kind = kind
        self.value = value
        self.pos = pos

    def __repr__(self) -> str:
        return f"Token({self.kind!r}, {self.value!r}, pos={self.pos})"


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
            tokens.append(_Token(_LP, "(", i))
            i += 1
            continue
        if ch == ")":
            tokens.append(_Token(_RP, ")", i))
            i += 1
            continue
        if ch.isdigit() or ch == ".":
            start = i
            seen_dot = False
            while i < n:
                c = expr[i]
                if c.isdigit():
                    i += 1
                elif c == "." and not seen_dot:
                    seen_dot = True
                    i += 1
                else:
                    break
            text = expr[start:i]
            # Validate number: must not be just "."
            if text == ".":
                raise ValueError(f"Invalid number at position {start}: '.'")
            # Must contain at least one digit
            if not any(c.isdigit() for c in text):
                raise ValueError(f"Invalid number at position {start}: {text!r}")
            # Determine int or float
            if seen_dot:
                value: int | float = float(text)
            else:
                value = int(text)
            tokens.append(_Token(_NUM, value, start))
            continue
        # Operators: check two-char first
        two = expr[i:i + 2]
        if two in ("**", "//"):
            tokens.append(_Token(_OP, two, i))
            i += 2
            continue
        if ch in "+-*/%":
            tokens.append(_Token(_OP, ch, i))
            i += 1
            continue
        raise ValueError(f"Invalid character {ch!r} at position {i}")
    tokens.append(_Token(_EOF, None, n))
    return tokens


class _Parser:
    def __init__(self, tokens: list[_Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    def _peek(self) -> _Token:
        return self.tokens[self.pos]

    def _advance(self) -> _Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def _expect(self, kind: str) -> _Token:
        tok = self._peek()
        if tok.kind != kind:
            raise ValueError(f"Expected {kind} but got {tok.kind!r} at position {tok.pos}")
        return self._advance()

    def parse(self) -> int | float:
        if self._peek().kind == _EOF:
            raise ValueError("Empty expression")
        result = self._parse_expression()
        if self._peek().kind != _EOF:
            tok = self._peek()
            raise ValueError(f"Unexpected token {tok.kind!r} at position {tok.pos}")
        return result

    def _parse_expression(self) -> int | float:
        # expression := term (('+' | '-') term)*
        left = self._parse_term()
        while True:
            tok = self._peek()
            if tok.kind == _OP and tok.value in ("+", "-"):
                self._advance()
                right = self._parse_term()
                if tok.value == "+":
                    left = left + right
                else:
                    left = left - right
            else:
                break
        return left

    def _parse_term(self) -> int | float:
        # term := power (('*' | '/' | '//' | '%') power)*
        left = self._parse_power()
        while True:
            tok = self._peek()
            if tok.kind == _OP and tok.value in ("*", "/", "//", "%"):
                self._advance()
                right = self._parse_power()
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

    def _parse_power(self) -> int | float:
        # power := unary ('**' power)?  (right-associative)
        # Note: ** binds tighter than unary on the left, but the right side
        # of ** can have unary signs. In Python, -2 ** 2 = -(2**2) = -4,
        # but 2 ** -2 = 2 ** (-2) = 0.25.
        # So the base of ** is a unary expression? No: in Python,
        # the left operand of ** is a "power" which does NOT include unary
        # minus. Unary minus has lower precedence than **.
        # So: power := unary (where unary is + or - applied to power)
        # Actually let's think carefully:
        # Python grammar:
        #   power: (await_expr | primary) ['**' u_expr]
        #   u_expr: power | '-' u_expr | '+' u_expr
        # So unary is ABOVE power in the grammar? No:
        #   u_expr is the operand of **, and power's base is primary/await.
        # Wait, let me re-read:
        #   power: (await_expr | primary) ['**' u_expr]
        #   u_expr: power | '-' u_expr | '+' u_expr
        #
        # So the left side of ** is a "power" (which is primary or await),
        # and the right side is a "u_expr" (unary expression).
        # This means:
        #   -2 ** 2: the '-' is a u_expr wrapping... wait no.
        #   -2 ** 2 is parsed as: u_expr -> '-' u_expr -> '-' power -> '-' (2 ** 2) = -4
        #   2 ** -2: power -> 2 ** u_expr -> 2 ** ('-' u_expr -> '-' power -> '-' 2) = 2 ** (-2)
        #
        # So in our parser:
        #   _parse_power should parse: base ('**' unary)*  where base is a primary (number or paren)
        #   and the right side of ** is a unary expression.
        #
        # But wait, what about 2 ** 3 ** 2? That's right-associative: 2 ** (3 ** 2) = 512.
        # In the grammar, power: primary ['**' u_expr], and u_expr can be power, so
        # 2 ** 3 ** 2 -> 2 ** (u_expr) where u_expr = power = 3 ** 2.
        #
        # So: _parse_power := _parse_primary ('**' _parse_unary)?
        # But _parse_unary can call _parse_power, which can call _parse_primary...
        # This creates the right recursion for **.

        base = self._parse_primary()
        tok = self._peek()
        if tok.kind == _OP and tok.value == "**":
            self._advance()
            # Right side is a unary expression
            exponent = self._parse_unary()
            return _pow(base, exponent)
        return base

    def _parse_unary(self) -> int | float:
        # u_expr := power | '+' u_expr | '-' u_expr
        tok = self._peek()
        if tok.kind == _OP and tok.value in ("+", "-"):
            self._advance()
            operand = self._parse_unary()
            if tok.value == "+":
                return +operand
            else:
                return -operand
        return self._parse_power()

    def _parse_primary(self) -> int | float:
        # primary := NUMBER | '(' expression ')'
        tok = self._peek()
        if tok.kind == _NUM:
            self._advance()
            return tok.value
        if tok.kind == _LP:
            self._advance()
            result = self._parse_expression()
            self._expect(_RP)
            return result
        raise ValueError(f"Unexpected token {tok.kind!r} at position {tok.pos}")


def _pow(base: int | float, exponent: int | float) -> int | float:
    # Python semantics for **
    if isinstance(base, int) and isinstance(exponent, int):
        if exponent < 0:
            if base == 0:
                raise ZeroDivisionError("0.0 cannot be raised to a negative power")
            return float(base) ** exponent
        return base ** exponent
    # If either is float, or exponent is negative int with non-zero base
    try:
        result = base ** exponent
    except ZeroDivisionError:
        raise
    return result


def evaluate(expr: str) -> int | float:
    if not isinstance(expr, str):
        raise ValueError("Expression must be a string")
    tokens = _tokenize(expr)
    parser = _Parser(tokens)
    return parser.parse()
