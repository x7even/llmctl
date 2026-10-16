"""Arithmetic expression evaluator using a hand-written tokenizer and recursive-descent parser."""


def evaluate(expr: str) -> int | float:
    """Evaluate an arithmetic expression string and return int or float."""
    tokens = _tokenize(expr)
    if not tokens:
        raise ValueError("empty expression")
    parser = _Parser(tokens)
    result = parser.parse()
    return result


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

def _tokenize(expr: str) -> list[tuple[str, object]]:
    tokens: list[tuple[str, object]] = []
    i = 0
    n = len(expr)

    while i < n:
        ch = expr[i]

        # skip whitespace (spaces and tabs only)
        if ch in ' \t':
            i += 1
            continue

        # numbers
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
                raise ValueError("malformed number: lone '.'")
            # reject things like 1e3, 2abc
            if i < n and expr[i].isalpha():
                raise ValueError("invalid character in number")
            num_str = expr[start:i]
            if has_dot:
                tokens.append(('NUMBER', float(num_str)))
            else:
                tokens.append(('NUMBER', int(num_str)))
            continue

        # two-character operators
        if ch == '*' and i + 1 < n and expr[i + 1] == '*':
            tokens.append(('OP', '**'))
            i += 2
            continue
        if ch == '/' and i + 1 < n and expr[i + 1] == '/':
            tokens.append(('OP', '//'))
            i += 2
            continue

        # single-character operators / parens
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

        raise ValueError(f"invalid character: {ch!r}")

    return tokens


# ---------------------------------------------------------------------------
# Recursive-descent parser
# ---------------------------------------------------------------------------

class _Parser:
    """
    Grammar (precedence low→high):
        expr   → term (('+' | '-') term)*
        term   → unary (('*' | '/' | '//' | '%') unary)*
        unary  → ('+' | '-') unary | power
        power  → atom ('**' unary)?
        atom   → NUMBER | '(' expr ')'
    """

    def __init__(self, tokens: list[tuple[str, object]]):
        self._tokens = tokens
        self._pos = 0

    # -- helpers -------------------------------------------------------------

    def _peek(self):
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return None

    def _consume(self):
        tok = self._peek()
        if tok is None:
            raise ValueError("unexpected end of expression")
        self._pos += 1
        return tok

    # -- entry point ---------------------------------------------------------

    def parse(self) -> int | float:
        result = self._expr()
        if self._pos != len(self._tokens):
            raise ValueError("unexpected token after complete expression")
        return result

    # -- productions ---------------------------------------------------------

    def _expr(self) -> int | float:
        left = self._term()
        while True:
            tok = self._peek()
            if tok is not None and tok[0] == 'OP' and tok[1] in ('+', '-'):
                op = self._consume()[1]
                right = self._term()
                if op == '+':
                    left = left + right
                else:
                    left = left - right
            else:
                break
        return left

    def _term(self) -> int | float:
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
                else:  # '%'
                    left = left % right
            else:
                break
        return left

    def _unary(self) -> int | float:
        tok = self._peek()
        if tok is not None and tok[0] == 'OP' and tok[1] in ('+', '-'):
            op = self._consume()[1]
            operand = self._unary()
            if op == '-':
                return -operand
            return +operand
        return self._power()

    def _power(self) -> int | float:
        base = self._atom()
        tok = self._peek()
        if tok is not None and tok[0] == 'OP' and tok[1] == '**':
            self._consume()
            # right-hand side of ** may carry a unary sign
            exponent = self._unary()
            return base ** exponent
        return base

    def _atom(self) -> int | float:
        tok = self._peek()
        if tok is None:
            raise ValueError("unexpected end of expression")
        if tok[0] == 'NUMBER':
            self._consume()
            return tok[1]  # type: ignore[return-value]
        if tok[0] == 'LPAREN':
            self._consume()
            result = self._expr()
            closing = self._peek()
            if closing is None or closing[0] != 'RPAREN':
                raise ValueError("unbalanced parentheses")
            self._consume()
            return result
        raise ValueError(f"unexpected token: {tok}")
