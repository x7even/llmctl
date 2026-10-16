"""Arithmetic expression evaluator – hand-written tokenizer + recursive-descent parser.

Public API:
    evaluate(expr: str) -> int | float

No eval / exec / compile / ast used.
"""

from __future__ import annotations

Number = int | float

# ─── Token kinds ────────────────────────────────────────────────────────────────
_TOK_NUM    = "NUM"
_TOK_OP     = "OP"
_TOK_LPAREN = "LPAREN"
_TOK_RPAREN = "RPAREN"
_TOK_EOF    = "EOF"


class _Token:
    __slots__ = ("kind", "value")

    def __init__(self, kind: str, value=None):
        self.kind = kind
        self.value = value

    def __repr__(self) -> str:
        return f"Token({self.kind}, {self.value!r})"


# ─── Tokenizer ──────────────────────────────────────────────────────────────────

def _tokenize(expr: str) -> list[_Token]:
    tokens: list[_Token] = []
    i = 0
    n = len(expr)

    while i < n:
        ch = expr[i]

        # skip whitespace
        if ch in (" ", "\t"):
            i += 1
            continue

        # ── number literal ──
        if ch.isdigit() or ch == ".":
            start = i
            has_dot = False
            has_digit = False
            while i < n and (expr[i].isdigit() or expr[i] == "."):
                if expr[i] == ".":
                    if has_dot:
                        raise ValueError("Malformed number (multiple decimal points)")
                    has_dot = True
                else:
                    has_digit = True
                i += 1
            if not has_digit:
                raise ValueError("Invalid number: lone '.'")
            num_str = expr[start:i]
            tokens.append(_Token(_TOK_NUM, float(num_str) if has_dot else int(num_str)))
            continue

        # ── two-character operators ──
        if ch == "*" and i + 1 < n and expr[i + 1] == "*":
            tokens.append(_Token(_TOK_OP, "**"))
            i += 2
            continue
        if ch == "/" and i + 1 < n and expr[i + 1] == "/":
            tokens.append(_Token(_TOK_OP, "//"))
            i += 2
            continue

        # ── single-character operators ──
        if ch in "+-*/%":
            tokens.append(_Token(_TOK_OP, ch))
            i += 1
            continue

        # ── parentheses ──
        if ch == "(":
            tokens.append(_Token(_TOK_LPAREN))
            i += 1
            continue
        if ch == ")":
            tokens.append(_Token(_TOK_RPAREN))
            i += 1
            continue

        raise ValueError(f"Invalid character: {ch!r}")

    tokens.append(_Token(_TOK_EOF))
    return tokens


# ─── Recursive-descent parser ───────────────────────────────────────────────────
#
# Grammar (mirrors CPython's arithmetic subset):
#
#   expr    : term (('+' | '-') term)*
#   term    : factor (('*' | '/' | '//' | '%') factor)*
#   factor  : ('+' | '-') factor | power
#   power   : primary ('**' factor)?
#   primary : NUMBER | '(' expr ')'
#
# This gives the correct Python precedence and associativity:
#   • ** is right-associative and binds tighter than unary +/- on its left
#   • unary +/- binds tighter than * / // %
#   • the right operand of ** is a *factor*, so 2**-1 and 2**-2**2 work correctly.

class _Parser:
    def __init__(self, tokens: list[_Token]):
        self._tokens = tokens
        self._pos = 0

    # ── helpers ──
    def _peek(self) -> _Token:
        return self._tokens[self._pos]

    def _advance(self) -> _Token:
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    # ── entry point ──
    def parse(self) -> Number:
        result = self._expr()
        if self._peek().kind != _TOK_EOF:
            raise ValueError("Unexpected token after expression (e.g. adjacent numbers)")
        return result

    # ── expr: + - (left-assoc) ──
    def _expr(self) -> Number:
        left = self._term()
        while True:
            tok = self._peek()
            if tok.kind == _TOK_OP and tok.value in ("+", "-"):
                self._advance()
                right = self._term()
                left = left + right if tok.value == "+" else left - right
            else:
                break
        return left

    # ── term: * / // % (left-assoc) ──
    def _term(self) -> Number:
        left = self._factor()
        while True:
            tok = self._peek()
            if tok.kind == _TOK_OP and tok.value in ("*", "/", "//", "%"):
                self._advance()
                right = self._factor()
                op = tok.value
                if op == "*":
                    left = left * right
                elif op == "/":
                    left = left / right
                elif op == "//":
                    left = left // right
                else:  # %
                    left = left % right
            else:
                break
        return left

    # ── factor: unary + - ──
    def _factor(self) -> Number:
        tok = self._peek()
        if tok.kind == _TOK_OP and tok.value in ("+", "-"):
            self._advance()
            operand = self._factor()
            return -operand if tok.value == "-" else operand
        return self._power()

    # ── power: ** (right-assoc, right operand is a factor) ──
    def _power(self) -> Number:
        base = self._primary()
        tok = self._peek()
        if tok.kind == _TOK_OP and tok.value == "**":
            self._advance()
            exp = self._factor()  # factor → allows unary sign on RHS, right-assoc
            return base ** exp
        return base

    # ── primary: number or parenthesised sub-expression ──
    def _primary(self) -> Number:
        tok = self._peek()
        if tok.kind == _TOK_NUM:
            self._advance()
            return tok.value
        if tok.kind == _TOK_LPAREN:
            self._advance()
            if self._peek().kind == _TOK_RPAREN:
                raise ValueError("Empty parentheses '()'")
            result = self._expr()
            if self._peek().kind != _TOK_RPAREN:
                raise ValueError("Unbalanced parentheses: missing ')'")
            self._advance()
            return result
        raise ValueError("Unexpected token in expression")


# ─── Public API ─────────────────────────────────────────────────────────────────

def evaluate(expr: str) -> int | float:
    """Evaluate an arithmetic expression string and return int or float.

    Raises ValueError for malformed input, ZeroDivisionError for division by zero.
    """
    if not expr or not expr.strip():
        raise ValueError("Empty expression")
    tokens = _tokenize(expr)
    parser = _Parser(tokens)
    return parser.parse()
