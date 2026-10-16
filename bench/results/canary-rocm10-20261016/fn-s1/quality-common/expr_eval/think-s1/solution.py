"""Arithmetic expression evaluator using a hand-written tokenizer and recursive-descent parser.

Public API:
    evaluate(expr: str) -> int | float
"""

from __future__ import annotations

from enum import Enum, auto
from dataclasses import dataclass
from typing import Any


# ---------------------------------------------------------------------------
# Token definitions
# ---------------------------------------------------------------------------

class TokenType(Enum):
    NUMBER = auto()
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    DOUBLE_SLASH = auto()
    PERCENT = auto()
    DOUBLE_STAR = auto()
    LPAREN = auto()
    RPAREN = auto()
    EOF = auto()


@dataclass(frozen=True, slots=True)
class Token:
    type: TokenType
    value: Any = None  # numeric value for NUMBER tokens


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

def _tokenize(source: str) -> list[Token]:
    tokens: list[Token] = []
    i = 0
    n = len(source)

    while i < n:
        ch = source[i]

        # Skip whitespace (spaces and tabs only)
        if ch in (' ', '\t'):
            i += 1
            continue

        # --- Numbers ---
        if ch.isdigit() or ch == '.':
            start = i
            has_dot = False

            if ch == '.':
                # Must be followed by at least one digit
                i += 1
                if i >= n or not source[i].isdigit():
                    raise ValueError("Invalid number: lone '.'")
                while i < n and source[i].isdigit():
                    i += 1
            else:
                # Integer part
                while i < n and source[i].isdigit():
                    i += 1
                # Optional fractional part
                if i < n and source[i] == '.':
                    has_dot = True
                    i += 1
                    while i < n and source[i].isdigit():
                        i += 1

            # Reject a second dot (e.g. "1..2", "1.2.3")
            if i < n and source[i] == '.':
                raise ValueError("Invalid number: multiple decimal points")

            text = source[start:i]
            if has_dot:
                tokens.append(Token(TokenType.NUMBER, float(text)))
            else:
                tokens.append(Token(TokenType.NUMBER, int(text)))
            continue

        # --- Two-character operators (check before single-char) ---
        if ch == '*' and i + 1 < n and source[i + 1] == '*':
            tokens.append(Token(TokenType.DOUBLE_STAR))
            i += 2
            continue

        if ch == '/' and i + 1 < n and source[i + 1] == '/':
            tokens.append(Token(TokenType.DOUBLE_SLASH))
            i += 2
            continue

        # --- Single-character tokens ---
        if ch == '+':
            tokens.append(Token(TokenType.PLUS))
        elif ch == '-':
            tokens.append(Token(TokenType.MINUS))
        elif ch == '*':
            tokens.append(Token(TokenType.STAR))
        elif ch == '/':
            tokens.append(Token(TokenType.SLASH))
        elif ch == '%':
            tokens.append(Token(TokenType.PERCENT))
        elif ch == '(':
            tokens.append(Token(TokenType.LPAREN))
        elif ch == ')':
            tokens.append(Token(TokenType.RPAREN))
        else:
            raise ValueError(f"Invalid character: {ch!r}")

        i += 1

    tokens.append(Token(TokenType.EOF))
    return tokens


# ---------------------------------------------------------------------------
# Recursive-descent parser / evaluator
#
# Grammar (lowest to highest precedence):
#   expr   : term (('+' | '-') term)*
#   term   : unary (('*' | '/' | '//' | '%') unary)*
#   unary  : ('+' | '-') unary | power
#   power  : atom ('**' unary)?          # right-assoc via recursion into unary
#   atom   : NUMBER | '(' expr ')'
# ---------------------------------------------------------------------------

class _Parser:
    __slots__ = ('_tokens', '_pos')

    def __init__(self, tokens: list[Token]) -> None:
        self._tokens = tokens
        self._pos = 0

    # -- helpers ----------------------------------------------------------

    def _current(self) -> Token:
        return self._tokens[self._pos]

    def _advance(self) -> Token:
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    # -- grammar rules ----------------------------------------------------

    def parse(self) -> int | float:
        result = self._expr()
        if self._current().type != TokenType.EOF:
            raise ValueError("Unexpected token after end of expression")
        return result

    def _expr(self) -> int | float:
        """expr : term (('+' | '-') term)*"""
        result = self._term()
        while self._current().type in (TokenType.PLUS, TokenType.MINUS):
            op = self._advance().type
            right = self._term()
            if op is TokenType.PLUS:
                result = result + right
            else:
                result = result - right
        return result

    def _term(self) -> int | float:
        """term : unary (('*' | '/' | '//' | '%') unary)*"""
        result = self._unary()
        while self._current().type in (
            TokenType.STAR, TokenType.SLASH, TokenType.DOUBLE_SLASH, TokenType.PERCENT
        ):
            op = self._advance().type
            right = self._unary()
            if op is TokenType.STAR:
                result = result * right
            elif op is TokenType.SLASH:
                result = result / right
            elif op is TokenType.DOUBLE_SLASH:
                result = result // right
            else:  # PERCENT
                result = result % right
        return result

    def _unary(self) -> int | float:
        """unary : ('+' | '-') unary | power"""
        if self._current().type is TokenType.PLUS:
            self._advance()
            return +self._unary()
        if self._current().type is TokenType.MINUS:
            self._advance()
            return -self._unary()
        return self._power()

    def _power(self) -> int | float:
        """power : atom ('**' unary)?"""
        base = self._atom()
        if self._current().type is TokenType.DOUBLE_STAR:
            self._advance()
            exponent = self._unary()  # allows unary sign on right operand
            return base ** exponent
        return base

    def _atom(self) -> int | float:
        """atom : NUMBER | '(' expr ')'"""
        tok = self._current()
        if tok.type is TokenType.NUMBER:
            self._advance()
            return tok.value
        if tok.type is TokenType.LPAREN:
            self._advance()
            if self._current().type is TokenType.RPAREN:
                raise ValueError("Empty parentheses '()'")
            result = self._expr()
            if self._current().type is not TokenType.RPAREN:
                raise ValueError("Unbalanced parentheses")
            self._advance()
            return result
        # Anything else (EOF, operator, RPAREN) is an error
        raise ValueError(f"Unexpected token: {tok.type.name}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate(expr: str) -> int | float:
    """Evaluate an arithmetic expression string and return the numeric result.

    Raises:
        ValueError  – on malformed input.
        ZeroDivisionError – on division/modulo by zero or 0 ** negative.
    """
    if not expr or not expr.strip():
        raise ValueError("Empty expression")

    tokens = _tokenize(expr)
    parser = _Parser(tokens)
    return parser.parse()
