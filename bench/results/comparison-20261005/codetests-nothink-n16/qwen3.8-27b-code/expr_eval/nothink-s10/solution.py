"""Arithmetic expression evaluator (tokenizer + recursive-descent parser)."""

from __future__ import annotations

# Token kinds
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
    __slots__ = ("kind", "value", "pos")

    def __init__(self, kind: str, value, pos: int):
        self.kind = kind
        self.value = value
        self.pos = pos

    def __repr__(self):
        return f"Token({self.kind!r}, {self.value!r}, pos={self.pos})"


def _tokenize(expr: str) -> list[_Token]:
    tokens: list[_Token] = []
    i = 0
    n = len(expr)
    while i < n:
        c = expr[i]
        if c in " \t":
            i += 1
            continue
        # Numbers: integer or decimal
        if c.isdigit() or c == ".":
            start = i
            # If it's a digit, consume digits
            if c.isdigit():
                while i < n and expr[i].isdigit():
                    i += 1
                # Check for decimal point
                if i < n and expr[i] == ".":
                    i += 1
                    # Consume fractional digits (optional)
                    while i < n and expr[i].isdigit():
                        i += 1
                    # After a dot, next char must not be a digit or dot (to catch 1..2, 1.2.3)
                    # Actually we just consumed; if next is dot, it's malformed
                    if i < n and expr[i] == ".":
                        raise ValueError(f"Malformed number at position {start}")
                    # Also if next is a digit we already consumed; but what about "1.2.3"?
                    # We consumed "1.2", then see "." again -> error
                    # But wait, the while loop above only consumes digits after the first dot.
                    # Let me re-check: for "1.2.3": i starts at 0, consume "1", see ".", i=2,
                    # consume "2", i=3, see ".", raise error. Good.
                    # But what about "1..2"? consume "1", see ".", i=2, then expr[2]=".",
                    # the while for fractional digits doesn't run (expr[2] is not digit),
                    # then we check if expr[i]=="." -> yes, raise. Good.
                    pass
                else:
                    # No dot, just integer
                    pass
            else:
                # c == "."
                i += 1
                # Must have at least one digit after the dot
                if i >= n or not expr[i].isdigit():
                    raise ValueError(f"Malformed number at position {start}")
                while i < n and expr[i].isdigit():
                    i += 1
                # After consuming digits, next char must not be a dot
                if i < n and expr[i] == ".":
                    raise ValueError(f"Malformed number at position {start}")
            text = expr[start:i]
            if "." in text:
                value: int | float = float(text)
            else:
                value = int(text)
            tokens.append(_Token(T_NUM, value, start))
            continue
        # Operators and parens
        if c == "+":
            tokens.append(_Token(T_PLUS, "+", i))
            i += 1
        elif c == "-":
            tokens.append(_Token(T_MINUS, "-", i))
            i += 1
        elif c == "*":
            if i + 1 < n and expr[i + 1] == "*":
                tokens.append(_Token(T_DSTAR, "**", i))
                i += 2
            else:
                tokens.append(_Token(T_STAR, "*", i))
                i += 1
        elif c == "/":
            if i + 1 < n and expr[i + 1] == "/":
                tokens.append(_Token(T_DSLASH, "//", i))
                i += 2
            else:
                tokens.append(_Token(T_SLASH, "/", i))
                i += 1
        elif c == "%":
            tokens.append(_Token(T_PERCENT, "%", i))
            i += 1
        elif c == "(":
            tokens.append(_Token(T_LPAREN, "(", i))
            i += 1
        elif c == ")":
            tokens.append(_Token(T_RPAREN, ")", i))
            i += 1
        else:
            raise ValueError(f"Invalid character {c!r} at position {i}")
    tokens.append(_Token(T_EOF, None, n))
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

    def _expect(self, kind: str) -> _Token:
        tok = self._peek()
        if tok.kind != kind:
            raise ValueError(f"Expected {kind}, got {tok.kind} at position {tok.pos}")
        return self._advance()

    def parse(self) -> int | float:
        if self._peek().kind == T_EOF:
            raise ValueError("Empty expression")
        result = self._expr()
        if self._peek().kind != T_EOF:
            tok = self._peek()
            raise ValueError(f"Unexpected token {tok.kind} at position {tok.pos}")
        return result

    def _expr(self) -> int | float:
        """expr := term (('+' | '-') term)*"""
        left = self._term()
        while self._peek().kind in (T_PLUS, T_MINUS):
            op = self._advance().kind
            right = self._term()
            if op == T_PLUS:
                left = left + right
            else:
                left = left - right
        return left

    def _term(self) -> int | float:
        """term := factor (('*' | '/' | '//' | '%') factor)*"""
        left = self._factor()
        while self._peek().kind in (T_STAR, T_SLASH, T_DSLASH, T_PERCENT):
            op = self._advance().kind
            right = self._factor()
            if op == T_STAR:
                left = left * right
            elif op == T_SLASH:
                if right == 0:
                    raise ZeroDivisionError("division by zero")
                left = left / right
            elif op == T_DSLASH:
                if right == 0:
                    raise ZeroDivisionError("integer division by zero")
                left = left // right
            else:  # T_PERCENT
                if right == 0:
                    raise ZeroDivisionError("modulo by zero")
                left = left % right
        return left

    def _factor(self) -> int | float:
        """factor := ('+' | '-')* power
        power := atom ('**' factor)?  -- note: right side of ** can have unary signs
        """
        # Handle unary +/- (stackable)
        sign = 1
        while self._peek().kind in (T_PLUS, T_MINUS):
            tok = self._advance()
            if tok.kind == T_MINUS:
                sign = -sign
        # Now parse the power expression
        base = self._atom()
        if self._peek().kind == T_DSTAR:
            self._advance()
            # Right side of ** can have unary signs, so we parse a factor
            exponent = self._factor()
            if isinstance(base, int) and isinstance(exponent, int) and exponent < 0:
                # Check for zero base with negative exponent
                if base == 0:
                    raise ZeroDivisionError("0 ** -1")
                # Python: int ** negative int -> float
                result = base ** exponent
                # In Python, this gives a float
                return sign * result
            else:
                result = base ** exponent
                return sign * result
        return sign * base

    def _atom(self) -> int | float:
        """atom := NUMBER | '(' expr ')'"""
        tok = self._peek()
        if tok.kind == T_NUM:
            self._advance()
            return tok.value
        if tok.kind == T_LPAREN:
            self._advance()
            result = self._expr()
            self._expect(T_RPAREN)
            return result
        raise ValueError(f"Unexpected token {tok.kind} at position {tok.pos}")


def evaluate(expr: str) -> int | float:
    """Evaluate an arithmetic expression string and return the result.

    Supports:
      - Integer and decimal literals (e.g., 3, 42, 3.5, .5, 2.)
      - Binary operators: + - * / // % **
      - Unary operators: + - (stackable)
      - Parentheses for grouping
      - Whitespace (spaces, tabs) is ignored

    Raises:
      ValueError: for malformed input
      ZeroDivisionError: for division/modulo/floor-division by zero, or 0 ** negative
    """
    tokens = _tokenize(expr)
    parser = _Parser(tokens)
    return parser.parse()
