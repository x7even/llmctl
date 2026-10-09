"""Arithmetic expression evaluator using a hand-written tokenizer and recursive-descent parser.

Public API:
    evaluate(expr: str) -> int | float
"""

from enum import Enum, auto
from dataclasses import dataclass
from typing import List


class _TT(Enum):
    NUMBER = auto()
    OP = auto()
    LPAREN = auto()
    RPAREN = auto()


@dataclass
class _Token:
    kind: _TT
    value: str
    pos: int


# ─── Tokenizer ───────────────────────────────────────────────────────────────

def _tokenize(expr: str) -> List[_Token]:
    tokens: List[_Token] = []
    i = 0
    n = len(expr)
    while i < n:
        c = expr[i]
        # skip whitespace (spaces and tabs only)
        if c in (' ', '\t'):
            i += 1
            continue
        # parentheses
        if c == '(':
            tokens.append(_Token(_TT.LPAREN, '(', i))
            i += 1
        elif c == ')':
            tokens.append(_Token(_TT.RPAREN, ')', i))
            i += 1
        # operators
        elif c in '+-*/%':
            if c == '*' and i + 1 < n and expr[i + 1] == '*':
                tokens.append(_Token(_TT.OP, '**', i))
                i += 2
            elif c == '/' and i + 1 < n and expr[i + 1] == '/':
                tokens.append(_Token(_TT.OP, '//', i))
                i += 2
            else:
                tokens.append(_Token(_TT.OP, c, i))
                i += 1
        # numbers
        elif c.isdigit() or c == '.':
            start = i
            has_dot = False
            has_digit = False
            while i < n and (expr[i].isdigit() or expr[i] == '.'):
                if expr[i] == '.':
                    if has_dot:
                        raise ValueError(
                            f"Malformed number at position {start}"
                        )
                    has_dot = True
                else:
                    has_digit = True
                i += 1
            if not has_digit:
                raise ValueError(
                    f"Malformed number at position {start}"
                )
            tokens.append(_Token(_TT.NUMBER, expr[start:i], start))
        else:
            raise ValueError(
                f"Invalid character '{c}' at position {i}"
            )
    return tokens


# ─── Parser (recursive descent) ─────────────────────────────────────────────

class _Parser:
    """
    Grammar (precedence lowest→highest):
        expr    = term (('+' | '-') term)*
        term    = factor (('*' | '/' | '//' | '%') factor)*
        factor  = ('+' | '-') factor | power
        power   = primary ('**' factor)?          # right-assoc; RHS may carry unary
        primary = NUMBER | '(' expr ')'
    """

    def __init__(self, tokens: List[_Token]) -> None:
        self._tokens = tokens
        self._pos = 0

    # helpers ---------------------------------------------------------------

    def _peek(self):
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return None

    def _consume(self) -> _Token:
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    # entry point -----------------------------------------------------------

    def parse(self) -> int | float:
        if not self._tokens:
            raise ValueError("Empty expression")
        result = self._expr()
        if self._pos < len(self._tokens):
            raise ValueError(
                f"Unexpected token '{self._tokens[self._pos].value}' "
                f"at position {self._tokens[self._pos].pos}"
            )
        return result

    # grammar rules ---------------------------------------------------------

    def _expr(self) -> int | float:
        result = self._term()
        while True:
            tok = self._peek()
            if tok and tok.kind == _TT.OP and tok.value in ('+', '-'):
                op = self._consume().value
                right = self._term()
                result = _apply(op, result, right)
            else:
                break
        return result

    def _term(self) -> int | float:
        result = self._factor()
        while True:
            tok = self._peek()
            if tok and tok.kind == _TT.OP and tok.value in ('*', '/', '//', '%'):
                op = self._consume().value
                right = self._factor()
                result = _apply(op, result, right)
            else:
                break
        return result

    def _factor(self) -> int | float:
        tok = self._peek()
        if tok and tok.kind == _TT.OP and tok.value in ('+', '-'):
            self._consume()
            operand = self._factor()  # recursive → stacked unary
            return -operand if tok.value == '-' else operand
        return self._power()

    def _power(self) -> int | float:
        base = self._primary()
        tok = self._peek()
        if tok and tok.kind == _TT.OP and tok.value == '**':
            self._consume()
            # right side is _factor so it can carry unary sign → right-assoc
            exponent = self._factor()
            return _apply('**', base, exponent)
        return base

    def _primary(self) -> int | float:
        tok = self._peek()
        if tok is None:
            raise ValueError("Unexpected end of expression")
        if tok.kind == _TT.NUMBER:
            self._consume()
            return _make_number(tok.value)
        if tok.kind == _TT.LPAREN:
            self._consume()
            result = self._expr()
            closing = self._peek()
            if closing is None or closing.kind != _TT.RPAREN:
                raise ValueError("Unbalanced parentheses: missing ')'")
            self._consume()
            return result
        raise ValueError(
            f"Unexpected token '{tok.value}' at position {tok.pos}"
        )


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_number(s: str) -> int | float:
    if '.' in s:
        return float(s)
    return int(s)


def _apply(op: str, left, right):
    if op == '+':
        return left + right
    if op == '-':
        return left - right
    if op == '*':
        return left * right
    if op == '/':
        return left / right
    if op == '//':
        return left // right
    if op == '%':
        return left % right
    if op == '**':
        return left ** right
    raise ValueError(f"Unknown operator '{op}'")  # pragma: no cover


# ─── Public API ──────────────────────────────────────────────────────────────

def evaluate(expr: str) -> int | float:
    """Evaluate an arithmetic expression string and return an int or float.

    Raises ValueError for malformed input, ZeroDivisionError for division by zero.
    """
    tokens = _tokenize(expr)
    if not tokens:
        raise ValueError("Empty expression")
    parser = _Parser(tokens)
    return parser.parse()
