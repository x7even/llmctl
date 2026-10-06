"""Arithmetic expression evaluator (no eval/exec/compile/ast)."""

from __future__ import annotations

# Token kinds
_NUM = "NUM"
_OP = "OP"
_LP = "LP"
_RP = "RP"
_EOF = "EOF"


class _Token:
    __slots__ = ("kind", "value")

    def __init__(self, kind: str, value: object) -> None:
        self.kind = kind
        self.value = value

    def __repr__(self) -> str:
        return f"Token({self.kind!r}, {self.value!r})"


def _tokenize(s: str) -> list[_Token]:
    tokens: list[_Token] = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch in " \t\n\r":
            i += 1
            continue
        if ch == "(":
            tokens.append(_Token(_LP, "("))
            i += 1
        elif ch == ")":
            tokens.append(_Token(_RP, ")"))
            i += 1
        elif ch == "+":
            tokens.append(_Token(_OP, "+"))
            i += 1
        elif ch == "-":
            tokens.append(_Token(_OP, "-"))
            i += 1
        elif ch == "*":
            if i + 1 < n and s[i + 1] == "*":
                tokens.append(_Token(_OP, "**"))
                i += 2
            else:
                tokens.append(_Token(_OP, "*"))
                i += 1
        elif ch == "/":
            if i + 1 < n and s[i + 1] == "/":
                tokens.append(_Token(_OP, "//"))
                i += 2
            else:
                tokens.append(_Token(_OP, "/"))
                i += 1
        elif ch == "%":
            tokens.append(_Token(_OP, "%"))
            i += 1
        elif ch == ".":
            # Could be start of a decimal number like .5
            if i + 1 < n and s[i + 1].isdigit():
                # parse decimal starting with .
                j = i + 1
                while j < n and s[j].isdigit():
                    j += 1
                # check for trailing dot after digits? e.g. .5. is invalid
                if j < n and s[j] == ".":
                    raise ValueError(f"Malformed number at position {i}")
                tokens.append(_Token(_NUM, float(s[i:j])))
                i = j
            else:
                raise ValueError(f"Invalid character '.' at position {i}")
        elif ch.isdigit():
            j = i
            while j < n and s[j].isdigit():
                j += 1
            if j < n and s[j] == ".":
                # decimal number
                j += 1
                while j < n and s[j].isdigit():
                    j += 1
                # check for malformed like 1..2
                if j < n and s[j] == ".":
                    raise ValueError(f"Malformed number at position {i}")
                tokens.append(_Token(_NUM, float(s[i:j])))
            else:
                # check for malformed like 1.2.3 handled above; also 1. followed by non-digit is fine (2.)
                tokens.append(_Token(_NUM, int(s[i:j])))
            i = j
        else:
            raise ValueError(f"Invalid character {ch!r} at position {i}")
    tokens.append(_Token(_EOF, None))
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

    def _expect(self, kind: str, value: object | None = None) -> _Token:
        tok = self._peek()
        if tok.kind != kind:
            raise ValueError(f"Expected {kind!r} but got {tok.kind!r} ({tok.value!r})")
        if value is not None and tok.value != value:
            raise ValueError(f"Expected {value!r} but got {tok.value!r}")
        return self._advance()

    def parse(self) -> int | float:
        result = self._expression()
        if self._peek().kind != _EOF:
            raise ValueError(f"Unexpected token {self._peek().value!r}")
        return result

    def _expression(self) -> int | float:
        """expr := term (('+' | '-') term)*"""
        left = self._term()
        while self._peek().kind == _OP and self._peek().value in ("+", "-"):
            op = self._advance().value
            right = self._term()
            if op == "+":
                left = left + right
            else:
                left = left - right
        return left

    def _term(self) -> int | float:
        """term := unary (('*' | '/' | '//' | '%') unary)*"""
        left = self._unary()
        while self._peek().kind == _OP and self._peek().value in ("*", "/", "//", "%"):
            op = self._advance().value
            right = self._unary()
            if op == "*":
                left = left * right
            elif op == "/":
                if right == 0:
                    raise ZeroDivisionError("division by zero")
                left = left / right
            elif op == "//":
                if right == 0:
                    raise ZeroDivisionError("integer division by zero")
                left = left // right
            else:  # %
                if right == 0:
                    raise ZeroDivisionError("modulo by zero")
                left = left % right
        return left

    def _unary(self) -> int | float:
        """unary := ('+' | '-')* power"""
        while self._peek().kind == _OP and self._peek().value in ("+", "-"):
            op = self._advance().value
            operand = self._unary()
            if op == "-":
                operand = -operand
            # '+' is a no-op
        return operand

    def _power(self) -> int | float:
        """power := atom ('**' unary)?  (right-associative, exponent is unary)"""
        base = self._atom()
        if self._peek().kind == _OP and self._peek().value == "**":
            self._advance()
            exponent = self._unary()
            if base == 0 and exponent < 0:
                raise ZeroDivisionError("0 ** negative number")
            # Python semantics: int ** negative int -> float
            if isinstance(base, int) and isinstance(exponent, int) and exponent < 0:
                return float(base) ** float(exponent)
            return base ** exponent
        return base

    def _atom(self) -> int | float:
        """atom := NUMBER | '(' expression ')'"""
        tok = self._peek()
        if tok.kind == _NUM:
            self._advance()
            return tok.value
        if tok.kind == _LP:
            self._advance()
            if self._peek().kind == _RP:
                raise ValueError("Empty parentheses")
            result = self._expression()
            self._expect(_RP, ")")
            return result
        raise ValueError(f"Unexpected token {tok.value!r}")


def evaluate(expr: str) -> int | float:
    if not isinstance(expr, str):
        raise ValueError("Expression must be a string")
    if not expr.strip():
        raise ValueError("Empty expression")
    tokens = _tokenize(expr)
    parser = _Parser(tokens)
    return parser.parse()
