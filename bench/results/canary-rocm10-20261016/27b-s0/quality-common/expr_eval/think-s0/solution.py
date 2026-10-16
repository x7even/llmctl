"""Arithmetic expression evaluator (tokenizer + recursive-descent parser)."""

from __future__ import annotations


def _tokenize(expr: str) -> list[tuple[str, object]]:
    """Convert *expr* into a list of (kind, value) tokens."""
    tokens: list[tuple[str, object]] = []
    i = 0
    n = len(expr)

    while i < n:
        c = expr[i]

        # --- whitespace ---
        if c in (' ', '\t'):
            i += 1
            continue

        # --- numbers ---
        if c.isdigit() or c == '.':
            start = i
            has_dot = False
            while i < n and (expr[i].isdigit() or expr[i] == '.'):
                if expr[i] == '.':
                    if has_dot:
                        raise ValueError(
                            f"Malformed number (multiple dots) at position {i}"
                        )
                    has_dot = True
                i += 1
            text = expr[start:i]
            if not any(ch.isdigit() for ch in text):
                raise ValueError("Lone '.' is not a valid number")
            if has_dot:
                tokens.append(('NUMBER', float(text)))
            else:
                tokens.append(('NUMBER', int(text)))
            continue

        # --- operators ---
        if c == '+':
            tokens.append(('OP', '+'))
            i += 1
        elif c == '-':
            tokens.append(('OP', '-'))
            i += 1
        elif c == '*':
            if i + 1 < n and expr[i + 1] == '*':
                tokens.append(('OP', '**'))
                i += 2
            else:
                tokens.append(('OP', '*'))
                i += 1
        elif c == '/':
            if i + 1 < n and expr[i + 1] == '/':
                tokens.append(('OP', '//'))
                i += 2
            else:
                tokens.append(('OP', '/'))
                i += 1
        elif c == '%':
            tokens.append(('OP', '%'))
            i += 1
        elif c == '(':
            tokens.append(('LPAREN', '('))
            i += 1
        elif c == ')':
            tokens.append(('RPAREN', ')'))
            i += 1
        else:
            raise ValueError(f"Invalid character {c!r} at position {i}")

    return tokens


def evaluate(expr: str) -> int | float:
    """Evaluate an arithmetic expression and return the result.

    Supports: integer/decimal literals, +, -, *, /, //, %, ** (right-assoc),
    unary + and -, parentheses.  Semantics match Python's own arithmetic.
    Raises ValueError for malformed input, ZeroDivisionError for div-by-zero.
    """
    tokens = _tokenize(expr)
    if not tokens:
        raise ValueError("Empty expression")

    pos = 0  # current token index (mutated via nonlocal)

    def peek() -> tuple[str, object] | None:
        if pos < len(tokens):
            return tokens[pos]
        return None

    def advance() -> tuple[str, object]:
        nonlocal pos
        tok = peek()
        if tok is None:
            raise ValueError("Unexpected end of expression")
        pos += 1
        return tok

    # expression := term (('+' | '-') term)*
    def parse_expression() -> int | float:
        left = parse_term()
        while True:
            tok = peek()
            if tok is not None and tok[0] == 'OP' and tok[1] in ('+', '-'):
                advance()
                right = parse_term()
                if tok[1] == '+':
                    left = left + right
                else:
                    left = left - right
            else:
                break
        return left

    # term := factor (('*' | '/' | '//' | '%') factor)*
    def parse_term() -> int | float:
        left = parse_factor()
        while True:
            tok = peek()
            if tok is not None and tok[0] == 'OP' and tok[1] in ('*', '/', '//', '%'):
                advance()
                right = parse_factor()
                op = tok[1]
                if op == '*':
                    left = left * right
                elif op == '/':
                    left = left / right
                elif op == '//':
                    left = left // right
                else:  # '%'
                    left = left % right
            else:
                break
        return left

    # factor := ('+' | '-') factor | power
    def parse_factor() -> int | float:
        tok = peek()
        if tok is not None and tok[0] == 'OP' and tok[1] in ('+', '-'):
            advance()
            operand = parse_factor()
            if tok[1] == '+':
                return +operand
            return -operand
        return parse_power()

    # power := atom ('**' factor)?
    def parse_power() -> int | float:
        base = parse_atom()
        tok = peek()
        if tok is not None and tok[0] == 'OP' and tok[1] == '**':
            advance()
            exponent = parse_factor()  # right-associative; allows unary
            return base ** exponent
        return base

    # atom := NUMBER | '(' expression ')'
    def parse_atom() -> int | float:
        tok = peek()
        if tok is None:
            raise ValueError("Unexpected end of expression")
        if tok[0] == 'NUMBER':
            advance()
            return tok[1]  # type: ignore[return-value]
        if tok[0] == 'LPAREN':
            advance()
            val = parse_expression()
            closing = peek()
            if closing is None or closing[0] != 'RPAREN':
                raise ValueError("Expected closing parenthesis")
            advance()
            return val
        raise ValueError(f"Unexpected token {tok[1]!r}")

    result = parse_expression()

    if pos < len(tokens):
        raise ValueError(f"Unexpected token {tokens[pos][1]!r}")

    return result
