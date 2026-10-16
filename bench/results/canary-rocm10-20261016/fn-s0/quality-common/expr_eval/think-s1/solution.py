"""Arithmetic expression evaluator – tokenizer + recursive-descent parser.

Supports: int/float literals, + - * / // % **, unary +/-, parentheses.
No eval / exec / compile / ast.
"""

from __future__ import annotations

# ─── Token types ──────────────────────────────────────────────────────────────

_TOK_NUM = 0
_TOK_OP = 1
_TOK_LP = 2
_TOK_RP = 3


# ─── Tokenizer ────────────────────────────────────────────────────────────────

def _tokenize(expr: str) -> list[tuple[int, object]]:
    tokens: list[tuple[int, object]] = []
    i = 0
    n = len(expr)

    while i < n:
        ch = expr[i]

        # skip whitespace
        if ch in (' ', '\t'):
            i += 1
            continue

        # number literal
        if ch.isdigit() or ch == '.':
            start = i
            has_dot = False
            has_digit = False
            while i < n and (expr[i].isdigit() or expr[i] == '.'):
                if expr[i] == '.':
                    if has_dot:
                        raise ValueError("malformed number")
                    has_dot = True
                else:
                    has_digit = True
                i += 1
            if not has_digit:
                raise ValueError("malformed number")
            text = expr[start:i]
            tokens.append((_TOK_NUM, float(text) if has_dot else int(text)))

        # two-character operators
        elif ch == '*':
            if i + 1 < n and expr[i + 1] == '*':
                tokens.append((_TOK_OP, '**'))
                i += 2
            else:
                tokens.append((_TOK_OP, '*'))
                i += 1
        elif ch == '/':
            if i + 1 < n and expr[i + 1] == '/':
                tokens.append((_TOK_OP, '//'))
                i += 2
            else:
                tokens.append((_TOK_OP, '/'))
                i += 1

        # single-character operators
        elif ch in '+-%':
            tokens.append((_TOK_OP, ch))
            i += 1

        # parentheses
        elif ch == '(':
            tokens.append((_TOK_LP, ch))
            i += 1
        elif ch == ')':
            tokens.append((_TOK_RP, ch))
            i += 1

        else:
            raise ValueError(f"invalid character: {ch!r}")

    return tokens


# ─── Recursive-descent parser ─────────────────────────────────────────────────
#
# Grammar (lowest → highest precedence):
#   expr   = term  (('+' | '-') term)*
#   term   = unary (('*' | '/' | '//' | '%') unary)*
#   unary  = ('+' | '-') unary | power
#   power  = atom ('**' unary)?          ← right-assoc; right side may be unary
#   atom   = NUMBER | '(' expr ')'


class _Parser:
    __slots__ = ('_toks', '_pos')

    def __init__(self, tokens: list[tuple[int, object]]) -> None:
        self._toks = tokens
        self._pos = 0

    # helpers ──────────────────────────────────────────────────────────────────

    def _peek(self):
        if self._pos < len(self._toks):
            return self._toks[self._pos]
        return None

    def _advance(self):
        tok = self._toks[self._pos]
        self._pos += 1
        return tok

    # entry point ──────────────────────────────────────────────────────────────

    def parse(self):
        if not self._toks:
            raise ValueError("empty expression")
        result = self._expr()
        if self._pos != len(self._toks):
            raise ValueError("unexpected token")
        return result

    # grammar rules ────────────────────────────────────────────────────────────

    def _expr(self):
        left = self._term()
        while True:
            tok = self._peek()
            if tok is not None and tok[0] == _TOK_OP and tok[1] in ('+', '-'):
                op = self._advance()[1]
                right = self._term()
                left = left + right if op == '+' else left - right
            else:
                break
        return left

    def _term(self):
        left = self._unary()
        while True:
            tok = self._peek()
            if tok is not None and tok[0] == _TOK_OP and tok[1] in ('*', '/', '//', '%'):
                op = self._advance()[1]
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

    def _unary(self):
        tok = self._peek()
        if tok is not None and tok[0] == _TOK_OP and tok[1] in ('+', '-'):
            op = self._advance()[1]
            operand = self._unary()
            return -operand if op == '-' else operand
        return self._power()

    def _power(self):
        base = self._atom()
        tok = self._peek()
        if tok is not None and tok[0] == _TOK_OP and tok[1] == '**':
            self._advance()
            exp = self._unary()  # right operand may carry a unary sign
            return base ** exp
        return base

    def _atom(self):
        tok = self._peek()
        if tok is None:
            raise ValueError("unexpected end of expression")
        if tok[0] == _TOK_NUM:
            self._advance()
            return tok[1]
        if tok[0] == _TOK_LP:
            self._advance()
            result = self._expr()
            closing = self._peek()
            if closing is None or closing[0] != _TOK_RP:
                raise ValueError("unbalanced parentheses")
            self._advance()
            return result
        raise ValueError("unexpected token")


# ─── Public API ───────────────────────────────────────────────────────────────

def evaluate(expr: str) -> int | float:
    """Evaluate an arithmetic expression string and return int or float."""
    tokens = _tokenize(expr)
    return _Parser(tokens).parse()
