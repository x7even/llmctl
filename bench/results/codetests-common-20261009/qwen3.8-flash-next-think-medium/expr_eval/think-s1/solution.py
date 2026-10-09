"""Arithmetic expression evaluator using a hand-written tokenizer and recursive-descent parser."""

from __future__ import annotations

from typing import Union

Token = tuple[str, Union[str, int, float]]


def _tokenize(expr: str) -> list[Token]:
    tokens: list[Token] = []
    i, n = 0, len(expr)

    while i < n:
        ch = expr[i]

        # Skip whitespace
        if ch in (' ', '\t'):
            i += 1
            continue

        # Numbers (int or float)
        if ch.isdigit() or ch == '.':
            start = i
            if ch == '.':
                i += 1
                if i >= n or not expr[i].isdigit():
                    raise ValueError("Invalid number: lone '.'")
                while i < n and expr[i].isdigit():
                    i += 1
                if i < n and expr[i] == '.':
                    raise ValueError("Invalid number")
            else:
                while i < n and expr[i].isdigit():
                    i += 1
                if i < n and expr[i] == '.':
                    i += 1
                    while i < n and expr[i].isdigit():
                        i += 1
                    if i < n and expr[i] == '.':
                        raise ValueError("Invalid number")

            num_str = expr[start:i]
            if '.' in num_str:
                tokens.append(('NUM', float(num_str)))
            else:
                tokens.append(('NUM', int(num_str)))
            continue

        # Two-character operators
        if ch == '*' and i + 1 < n and expr[i + 1] == '*':
            tokens.append(('OP', '**'))
            i += 2
            continue
        if ch == '/' and i + 1 < n and expr[i + 1] == '/':
            tokens.append(('OP', '//'))
            i += 2
            continue

        # Single-character operators / parens
        if ch in '+-*/%':
            tokens.append(('OP', ch))
            i += 1
            continue
        if ch == '(':
            tokens.append(('LPAREN', '('))
            i += 1
            continue
        if ch == ')':
            tokens.append(('RPAREN', ')'))
            i += 1
            continue

        raise ValueError(f"Invalid character: {ch!r}")

    return tokens


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self._tokens = tokens
        self._pos = 0

    def _peek(self) -> Token | None:
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return None

    def _consume(self) -> Token:
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _expect(self, kind: str, value: str) -> Token:
        tok = self._peek()
        if tok is None or tok != (kind, value):
            raise ValueError("Unexpected token or unbalanced parentheses")
        return self._consume()

    # ---- grammar ----

    def parse(self) -> Union[int, float]:
        if not self._tokens:
            raise ValueError("Empty expression")
        result = self._expr()
        if self._pos != len(self._tokens):
            raise ValueError("Unexpected token after expression")
        return result

    def _expr(self) -> Union[int, float]:
        """expr -> term (('+' | '-') term)*"""
        left = self._term()
        while True:
            tok = self._peek()
            if tok is not None and tok == ('OP', '+'):
                self._consume()
                left = left + self._term()
            elif tok is not None and tok == ('OP', '-'):
                self._consume()
                left = left - self._term()
            else:
                break
        return left

    def _term(self) -> Union[int, float]:
        """term -> unary (('*' | '/' | '//' | '%') unary)*"""
        left = self._unary()
        while True:
            tok = self._peek()
            if tok is not None and tok[0] == 'OP' and tok[1] in ('*', '/', '//', '%'):
                op = self._consume()[1]
                right = self._unary()
                if op == '*':
                    left = left * right
                elif op == '/':
                    left = left / right
                elif op == '//':
                    left = left // right
                else:
                    left = left % right
            else:
                break
        return left

    def _unary(self) -> Union[int, float]:
        """unary -> ('+' | '-') unary | power"""
        tok = self._peek()
        if tok is not None and tok == ('OP', '+'):
            self._consume()
            return +self._unary()
        if tok is not None and tok == ('OP', '-'):
            self._consume()
            return -self._unary()
        return self._power()

    def _power(self) -> Union[int, float]:
        """power -> atom ('**' unary)?"""
        base = self._atom()
        tok = self._peek()
        if tok is not None and tok == ('OP', '**'):
            self._consume()
            exp = self._unary()
            return base ** exp
        return base

    def _atom(self) -> Union[int, float]:
        """atom -> NUMBER | '(' expr ')'"""
        tok = self._peek()
        if tok is None:
            raise ValueError("Unexpected end of expression")
        if tok[0] == 'NUM':
            self._consume()
            return tok[1]
        if tok == ('LPAREN', '('):
            self._consume()
            # empty parens check: if next is ')', expr() will fail with a good message
            result = self._expr()
            self._expect('RPAREN', ')')
            return result
        raise ValueError(f"Unexpected token: {tok!r}")


def evaluate(expr: str) -> Union[int, float]:
    """Evaluate an arithmetic expression string and return the numeric result.

    Raises ValueError for malformed input, ZeroDivisionError for division/modulo
    by zero or 0 ** negative.
    """
    tokens = _tokenize(expr)
    parser = _Parser(tokens)
    return parser.parse()
