"""Arithmetic expression evaluator (tokenizer + recursive-descent parser)."""

from __future__ import annotations


def evaluate(expr: str) -> int | float:
    """Evaluate an arithmetic expression and return an int or float.

    Supports: integer/decimal literals, +, -, *, /, //, %, ** (right-assoc),
    unary +/-, parentheses.  Raises ValueError for malformed input and
    ZeroDivisionError for division (or modulo/floor-division) by zero.
    """
    if not expr or not expr.strip():
        raise ValueError("empty expression")
    tokens = _tokenize(expr)
    if not tokens:
        raise ValueError("empty expression")
    result, pos = _parse_expr(tokens, 0)
    if pos != len(tokens):
        raise ValueError(f"unexpected token {tokens[pos]!r}")
    return result


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

def _tokenize(expr: str) -> list:
    """Convert *expr* into a list of tokens (int, float, or operator strings)."""
    tokens: list = []
    i = 0
    n = len(expr)
    while i < n:
        c = expr[i]
        # whitespace
        if c in (' ', '\t'):
            i += 1
            continue
        # integer or decimal literal
        if c.isdigit():
            j = i
            while j < n and expr[j].isdigit():
                j += 1
            if j < n and expr[j] == '.':
                # decimal: digits '.' [digits]
                k = j + 1
                while k < n and expr[k].isdigit():
                    k += 1
                tokens.append(float(expr[i:k]))
                i = k
            else:
                tokens.append(int(expr[i:j]))
                i = j
            continue
        # decimal starting with '.'
        if c == '.':
            if i + 1 >= n or not expr[i + 1].isdigit():
                raise ValueError(f"invalid number at position {i}")
            j = i + 1
            while j < n and expr[j].isdigit():
                j += 1
            tokens.append(float(expr[i:j]))
            i = j
            continue
        # two-character operators
        if c == '*' and i + 1 < n and expr[i + 1] == '*':
            tokens.append('**')
            i += 2
            continue
        if c == '/' and i + 1 < n and expr[i + 1] == '/':
            tokens.append('//')
            i += 2
            continue
        # single-character operators / parens
        if c in ('+', '-', '*', '/', '%', '(', ')'):
            tokens.append(c)
            i += 1
            continue
        raise ValueError(f"invalid character {c!r} at position {i}")
    return tokens


# ---------------------------------------------------------------------------
# Recursive-descent parser
#
# Grammar (mirrors Python's own precedence):
#   expr    : term (('+' | '-') term)*
#   term    : factor (('*' | '/' | '//' | '%') factor)*
#   factor  : ('+' | '-')* power
#   power   : primary ('**' factor)?
#   primary : NUMBER | '(' expr ')'
# ---------------------------------------------------------------------------

def _parse_expr(tokens: list, pos: int) -> tuple[int | float, int]:
    left, pos = _parse_term(tokens, pos)
    while pos < len(tokens) and tokens[pos] in ('+', '-'):
        op = tokens[pos]
        right, pos = _parse_term(tokens, pos + 1)
        left = left + right if op == '+' else left - right
    return left, pos


def _parse_term(tokens: list, pos: int) -> tuple[int | float, int]:
    left, pos = _parse_factor(tokens, pos)
    while pos < len(tokens) and tokens[pos] in ('*', '/', '//', '%'):
        op = tokens[pos]
        right, pos = _parse_factor(tokens, pos + 1)
        if op == '*':
            left = left * right
        elif op == '/':
            left = left / right
        elif op == '//':
            left = left // right
        else:  # '%'
            left = left % right
    return left, pos


def _parse_factor(tokens: list, pos: int) -> tuple[int | float, int]:
    sign = 1
    while pos < len(tokens) and tokens[pos] in ('+', '-'):
        if tokens[pos] == '-':
            sign = -sign
        pos += 1
    value, pos = _parse_power(tokens, pos)
    return sign * value, pos


def _parse_power(tokens: list, pos: int) -> tuple[int | float, int]:
    base, pos = _parse_primary(tokens, pos)
    if pos < len(tokens) and tokens[pos] == '**':
        exponent, pos = _parse_factor(tokens, pos + 1)
        base = base ** exponent  # Python handles 0**neg → ZeroDivisionError, int**neg→float
    return base, pos


def _parse_primary(tokens: list, pos: int) -> tuple[int | float, int]:
    if pos >= len(tokens):
        raise ValueError("unexpected end of expression")
    tok = tokens[pos]
    if isinstance(tok, (int, float)):
        return tok, pos + 1
    if tok == '(':
        value, pos = _parse_expr(tokens, pos + 1)
        if pos >= len(tokens) or tokens[pos] != ')':
            raise ValueError("unbalanced parentheses")
        return value, pos + 1
    raise ValueError(f"unexpected token {tok!r}")
