"""Arithmetic expression evaluator without eval/exec/compile/ast."""

from __future__ import annotations

# Token types
T_NUM = "NUM"
T_PLUS = "PLUS"
T_MINUS = "MINUS"
T_STAR = "STAR"
T_SLASH = "SLASH"
T_DSTAR = "DSTAR"
T_DSLASH = "DSLASH"
T_PERCENT = "PERCENT"
T_LPAREN = "LPAREN"
T_RPAREN = "RPAREN"
T_EOF = "EOF"


class _Token:
    __slots__ = ("type", "value")

    def __init__(self, type_: str, value=None):
        self.type = type_
        self.value = value

    def __repr__(self):
        return f"Token({self.type!r}, {self.value!r})"


def _tokenize(expr: str) -> list[_Token]:
    tokens: list[_Token] = []
    i = 0
    n = len(expr)
    while i < n:
        ch = expr[i]
        if ch in " \t":
            i += 1
            continue
        if ch.isdigit():
            # Parse number: digits, optional decimal point, optional more digits
            start = i
            while i < n and expr[i].isdigit():
                i += 1
            if i < n and expr[i] == ".":
                # Check if it's a decimal point followed by digits, or just a dot
                # A lone '.' after digits is malformed (e.g., "1." is valid, "1.." is not)
                # Actually "2." is valid per spec. So if we see '.', we consume it.
                # But we need to make sure it's not "1..2"
                i += 1
                # After the dot, we can have more digits
                while i < n and expr[i].isdigit():
                    i += 1
                # Check for malformed: if next char is '.' that's bad, but that's handled by next iteration
                # Actually, if we have "1.2.3", after parsing "1.2", next token starts with "."
                # which will be caught as invalid char or malformed. Let's see.
            tokens.append(_Token(T_NUM, expr[start:i]))
            continue
        if ch == ".":
            # Could be a decimal like ".5"
            start = i
            i += 1
            while i < n and expr[i].isdigit():
                i += 1
            # If no digits after dot, it's a lone dot - invalid
            if i == start + 1:
                raise ValueError(f"Malformed number: lone '.' at position {start}")
            tokens.append(_Token(T_NUM, expr[start:i]))
            continue
        if ch == "+":
            tokens.append(_Token(T_PLUS))
            i += 1
            continue
        if ch == "-":
            tokens.append(_Token(T_MINUS))
            i += 1
            continue
        if ch == "*":
            if i + 1 < n and expr[i + 1] == "*":
                tokens.append(_Token(T_DSTAR))
                i += 2
            else:
                tokens.append(_Token(T_STAR))
                i += 1
            continue
        if ch == "/":
            if i + 1 < n and expr[i + 1] == "/":
                tokens.append(_Token(T_DSLASH))
                i += 2
            else:
                tokens.append(_Token(T_SLASH))
                i += 1
            continue
        if ch == "%":
            tokens.append(_Token(T_PERCENT))
            i += 1
            continue
        if ch == "(":
            tokens.append(_Token(T_LPAREN))
            i += 1
            continue
        if ch == ")":
            tokens.append(_Token(T_RPAREN))
            i += 1
            continue
        raise ValueError(f"Invalid character: {ch!r} at position {i}")

    tokens.append(_Token(T_EOF))
    return tokens


def _parse_number(token: _Token) -> int | float:
    s = token.value
    if "." in s:
        return float(s)
    return int(s)


def _is_number_token(t: _Token) -> bool:
    return t.type == T_NUM


def _is_unary_op(t: _Token) -> bool:
    return t.type in (T_PLUS, T_MINUS)


def _is_binary_op(t: _Token) -> bool:
    return t.type in (T_PLUS, T_MINUS, T_STAR, T_SLASH, T_DSTAR, T_DSLASH, T_PERCENT)


class _Parser:
    def __init__(self, tokens: list[_Token]):
        self.tokens = tokens
        self.pos = 0

    def _current(self) -> _Token:
        return self.tokens[self.pos]

    def _advance(self) -> _Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def _expect(self, type_: str) -> _Token:
        tok = self._current()
        if tok.type != type_:
            raise ValueError(f"Expected {type_}, got {tok.type}")
        return self._advance()

    def parse(self) -> int | float:
        result = self._expression()
        if self._current().type != T_EOF:
            raise ValueError(f"Unexpected token: {self._current()}")
        return result

    def _expression(self) -> int | float:
        """Parse + and - (left-associative)."""
        left = self._term()
        while self._current().type in (T_PLUS, T_MINUS):
            op = self._advance().type
            right = self._term()
            if op == T_PLUS:
                left = left + right
            else:
                left = left - right
        return left

    def _term(self) -> int | float:
        """Parse * / // % (left-associative)."""
        left = self._power()
        while self._current().type in (T_STAR, T_SLASH, T_DSLASH, T_PERCENT):
            op = self._advance().type
            right = self._power()
            if op == T_STAR:
                left = left * right
            elif op == T_SLASH:
                if right == 0:
                    raise ZeroDivisionError("division by zero")
                left = left / right
            elif op == T_DSLASH:
                if right == 0:
                    raise ZeroDivisionError("integer division or modulo by zero")
                left = left // right
            elif op == T_PERCENT:
                if right == 0:
                    raise ZeroDivisionError("integer modulo by zero")
                left = left % right
        return left

    def _power(self) -> int | float:
        """Parse ** (right-associative)."""
        base = self._unary()
        if self._current().type == T_DSTAR:
            self._advance()
            # Right operand can be a unary expression (which can include ** due to right-assoc)
            # In Python, -2 ** 2 is (-2) ** 2? No, it's -(2 ** 2).
            # The right side of ** can have unary signs, and ** is right-associative.
            # So we parse the right side as a _power() to handle right-associativity,
            # but also allow unary signs.
            # Actually, the grammar for the right side of ** should allow unary operators.
            # Let's parse it as _unary() but we need right-associativity for **.
            # In Python: 2 ** 3 ** 2 = 2 ** (3 ** 2) = 512
            # So the right side of ** should be parsed as _power() to get right-associativity.
            # But we also need to allow unary signs: 2 ** -1
            # So the right side is: unary operators followed by a power?
            # Actually, the right side of ** in Python can be a unary expression,
            # and ** is right-associative, so:
            # 2 ** -2 ** 2 = 2 ** (-(2 ** 2)) = 2 ** (-4) = 0.0625
            # So we need to parse the right side allowing unary signs, and then ** is right-associative.
            # The correct approach: the right operand of ** is a _unary() that can itself contain **.
            # Let me think about this more carefully.
            #
            # Python's grammar:
            # power: (await_expr | primary) ['**' u_expr]
            # u_expr: power | '-' u_expr | '+' u_expr
            #
            # So the right side of ** is a u_expr, which can be a power or unary u_expr.
            # This means: 2 ** -2 ** 2 is parsed as 2 ** (-(2 ** 2))
            #
            # So in our parser, the right side of ** should be _unary().
            exponent = self._unary()
            if base == 0 and exponent < 0:
                raise ZeroDivisionError("0.0 cannot be raised to a negative power")
            left = base ** exponent
            return left
        return base

    def _unary(self) -> int | float:
        """Parse unary + and - (can be stacked)."""
        if self._current().type in (T_PLUS, T_MINUS):
            op = self._advance().type
            operand = self._unary()
            if op == T_PLUS:
                return +operand
            else:
                return -operand
        return self._primary()

    def _primary(self) -> int | float:
        """Parse primary expressions: numbers and parenthesized expressions."""
        tok = self._current()
        if tok.type == T_NUM:
            self._advance()
            return _parse_number(tok)
        if tok.type == T_LPAREN:
            self._advance()
            if self._current().type == T_RPAREN:
                raise ValueError("Empty parentheses")
            result = self._expression()
            self._expect(T_RPAREN)
            return result
        raise ValueError(f"Unexpected token: {tok}")


def evaluate(expr: str) -> int | float:
    if not expr or not expr.strip():
        raise ValueError("Empty expression")
    tokens = _tokenize(expr)
    parser = _Parser(tokens)
    return parser.parse()
