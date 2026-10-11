"""Arithmetic expression evaluator (tokenizer + recursive-descent parser).

Public API:
    evaluate(expr: str) -> int | float
"""

from __future__ import annotations


# ─── Tokenizer ────────────────────────────────────────────────────────────────

def _tokenize(expr: str) -> list[tuple[str, object]]:
    tokens: list[tuple[str, object]] = []
    i, n = 0, len(expr)

    while i < n:
        ch = expr[i]

        # skip whitespace
        if ch in (' ', '\t'):
            i += 1
            continue

        # numbers
        if ch.isdigit() or ch == '.':
            start = i
            if ch == '.':
                i += 1
                if i >= n or not expr[i].isdigit():
                    raise ValueError("invalid number: lone '.'")
                while i < n and expr[i].isdigit():
                    i += 1
            else:
                while i < n and expr[i].isdigit():
                    i += 1
                if i < n and expr[i] == '.':
                    i += 1
                    while i < n and expr[i].isdigit():
                        i += 1
            # reject a second dot (e.g. 1..2, 1.2.3)
            if i < n and expr[i] == '.':
                raise ValueError("invalid number: multiple decimal points")
            text = expr[start:i]
            if '.' in text:
                tokens.append(('NUM', float(text)))
            else:
                tokens.append(('NUM', int(text)))
            continue

        # operators & punctuation
        if ch == '+':
            tokens.append(('OP', '+')); i += 1
        elif ch == '-':
            tokens.append(('OP', '-')); i += 1
        elif ch == '*':
            if i + 1 < n and expr[i + 1] == '*':
                tokens.append(('OP', '**')); i += 2
            else:
                tokens.append(('OP', '*')); i += 1
        elif ch == '/':
            if i + 1 < n and expr[i + 1] == '/':
                tokens.append(('OP', '//')); i += 2
            else:
                tokens.append(('OP', '/')); i += 1
        elif ch == '%':
            tokens.append(('OP', '%')); i += 1
        elif ch == '(':
            tokens.append(('LPAREN', '(')); i += 1
        elif ch == ')':
            tokens.append(('RPAREN', ')')); i += 1
        else:
            raise ValueError(f"invalid character: {ch!r}")

    return tokens


# ─── Parser (recursive descent) ──────────────────────────────────────────────

class _Parser:
    def __init__(self, tokens: list[tuple[str, object]]) -> None:
        self._tokens = tokens
        self._pos = 0

    # helpers ──────────────────────────────────────────────────────────────────

    def _peek(self):
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return None

    def _advance(self):
        tok = self._peek()
        if tok is None:
            raise ValueError("unexpected end of expression")
        self._pos += 1
        return tok

    def _expect(self, kind: str, value=None):
        tok = self._peek()
        if tok is None:
            raise ValueError("unexpected end of expression")
        if tok[0] != kind or (value is not None and tok[1] != value):
            raise ValueError(f"expected {kind}{' ' + repr(value) if value else ''}, got {tok}")
        self._pos += 1
        return tok

    # grammar ──────────────────────────────────────────────────────────────────

    def parse(self):
        result = self._expr()
        if self._pos != len(self._tokens):
            raise ValueError("unexpected token after expression")
        return result

    def _expr(self):
        """expr := term (('+' | '-') term)*"""
        result = self._term()
        while True:
            tok = self._peek()
            if tok and tok[0] == 'OP' and tok[1] in ('+', '-'):
                self._advance()
                right = self._term()
                if tok[1] == '+':
                    result = result + right
                else:
                    result = result - right
            else:
                break
        return result

    def _term(self):
        """term := unary (('*' | '/' | '//' | '%') unary)*"""
        result = self._unary()
        while True:
            tok = self._peek()
            if tok and tok[0] == 'OP' and tok[1] in ('*', '/', '//', '%'):
                self._advance()
                right = self._unary()
                if tok[1] == '*':
                    result = result * right
                elif tok[1] == '/':
                    if right == 0:
                        raise ZeroDivisionError("division by zero")
                    result = result / right
                elif tok[1] == '//':
                    if right == 0:
                        raise ZeroDivisionError("division by zero")
                    result = result // right
                else:  # '%'
                    if right == 0:
                        raise ZeroDivisionError("division by zero")
                    result = result % right
            else:
                break
        return result

    def _unary(self):
        """unary := ('+' | '-') unary | power"""
        tok = self._peek()
        if tok and tok[0] == 'OP' and tok[1] in ('+', '-'):
            self._advance()
            operand = self._unary()
            if tok[1] == '-':
                return -operand
            return operand
        return self._power()

    def _power(self):
        """power := atom ('**' unary)?   [right-associative via unary recursion]"""
        base = self._atom()
        tok = self._peek()
        if tok and tok[0] == 'OP' and tok[1] == '**':
            self._advance()
            exponent = self._unary()
            return base ** exponent
        return base

    def _atom(self):
        """atom := NUMBER | '(' expr ')'"""
        tok = self._peek()
        if tok is None:
            raise ValueError("unexpected end of expression")
        if tok[0] == 'NUM':
            self._advance()
            return tok[1]
        if tok[0] == 'LPAREN':
            self._advance()
            result = self._expr()
            self._expect('RPAREN', ')')
            return result
        raise ValueError(f"unexpected token: {tok}")


# ─── Public API ───────────────────────────────────────────────────────────────

def evaluate(expr: str) -> int | float:
    """Evaluate an arithmetic expression string and return the numeric result."""
    tokens = _tokenize(expr)
    if not tokens:
        raise ValueError("empty expression")
    parser = _Parser(tokens)
    return parser.parse()
