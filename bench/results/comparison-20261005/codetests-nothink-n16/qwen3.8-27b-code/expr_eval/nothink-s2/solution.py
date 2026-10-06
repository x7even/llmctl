"""Arithmetic expression evaluator (no eval/exec/compile/ast)."""

from __future__ import annotations

# Token kinds
TOK_NUM = "NUM"
TOK_PLUS = "PLUS"
TOK_MINUS = "MINUS"
TOK_STAR = "STAR"
TOK_SLASH = "SLASH"
TOK_FLOORDIV = "FLOORDIV"
TOK_MOD = "MOD"
TOK_POW = "POW"
TOK_LPAREN = "LPAREN"
TOK_RPAREN = "RPAREN"
TOK_EOF = "EOF"


class _Token:
    __slots__ = ("kind", "value")

    def __init__(self, kind: str, value=None):
        self.kind = kind
        self.value = value

    def __repr__(self):
        return f"Token({self.kind!r}, {self.value!r})"


def _tokenize(s: str) -> list[_Token]:
    tokens: list[_Token] = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c in " \t":
            i += 1
            continue
        if c == "+":
            tokens.append(_Token(TOK_PLUS))
            i += 1
        elif c == "-":
            tokens.append(_Token(TOK_MINUS))
            i += 1
        elif c == "*":
            if i + 1 < n and s[i + 1] == "*":
                tokens.append(_Token(TOK_POW))
                i += 2
            else:
                tokens.append(_Token(TOK_STAR))
                i += 1
        elif c == "/":
            tokens.append(_Token(TOK_SLASH))
            i += 1
        elif c == "%":
            tokens.append(_Token(TOK_MOD))
            i += 1
        elif c == "(":
            tokens.append(_Token(TOK_LPAREN))
            i += 1
        elif c == ")":
            tokens.append(_Token(TOK_RPAREN))
            i += 1
        elif c == ".":
            # Number starting with '.'
            j = i + 1
            while j < n and s[j].isdigit():
                j += 1
            if j == i + 1:
                # lone '.' with no digits after
                raise ValueError(f"invalid number at position {i}: lone '.'")
            # Check that next char is not another '.' or digit after a dot already handled
            # Actually we consumed digits. But we need to ensure no second dot.
            # The loop above only consumes digits, so if s[j] == '.' that's a problem.
            # But wait: ".5" -> i=0, c='.', j starts at 1, consumes '5', j=2. Good.
            # "1..2" is handled when we're at '1'. Let's handle numbers starting with digit below.
            # For a number starting with '.', we just take the digits after it.
            # But what about ".5."? j would stop at the second '.', and we'd have a dangling '.' later.
            # Actually the tokenizer would then see '.' again and try to parse another number.
            # Let's just parse the number: '.' followed by digits.
            num_str = s[i:j]
            tokens.append(_Token(TOK_NUM, float(num_str)))
            i = j
        elif c.isdigit():
            j = i
            while j < n and s[j].isdigit():
                j += 1
            is_float = False
            if j < n and s[j] == ".":
                is_float = True
                j += 1
                while j < n and s[j].isdigit():
                    j += 1
                # Check for another dot
                if j < n and s[j] == ".":
                    raise ValueError(f"malformed number at position {i}: multiple dots")
            elif j < n and s[j] == ".":
                # This case is already handled above
                pass
            # Check that next char is not a digit or dot (already consumed)
            # Also check that next char isn't another digit (shouldn't be)
            num_str = s[i:j]
            if is_float:
                tokens.append(_Token(TOK_NUM, float(num_str)))
            else:
                tokens.append(_Token(TOK_NUM, int(num_str)))
            i = j
        else:
            raise ValueError(f"invalid character {c!r} at position {i}")
    tokens.append(_Token(TOK_EOF))
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
            raise ValueError(f"expected {kind}, got {tok.kind}")
        return self._advance()

    def parse(self) -> int | float:
        result = self._expression()
        if self._peek().kind != TOK_EOF:
            raise ValueError(f"unexpected token {self._peek().kind} after expression")
        return result

    def _expression(self) -> int | float:
        # expression := term (('+' | '-') term)*
        left = self._term()
        while self._peek().kind in (TOK_PLUS, TOK_MINUS):
            op = self._advance().kind
            right = self._term()
            if op == TOK_PLUS:
                left = left + right
            else:
                left = left - right
        return left

    def _term(self) -> int | float:
        # term := factor (('*' | '/' | '//' | '%') factor)*
        left = self._factor()
        while self._peek().kind in (TOK_STAR, TOK_SLASH, TOK_FLOORDIV, TOK_MOD):
            op = self._advance().kind
            right = self._factor()
            if op == TOK_STAR:
                left = left * right
            elif op == TOK_SLASH:
                if right == 0:
                    raise ZeroDivisionError("division by zero")
                left = left / right
            elif op == TOK_FLOORDIV:
                if right == 0:
                    raise ZeroDivisionError("division by zero")
                left = left // right
            else:  # TOK_MOD
                if right == 0:
                    raise ZeroDivisionError("modulo by zero")
                left = left % right
        return left

    def _factor(self) -> int | float:
        # factor := power | ('+' | '-') factor
        # In Python, unary has higher precedence than *, /, //, % but lower than **
        # Actually: unary is between ** and multiplicative.
        # The grammar:
        # power := primary ('**' factor)?  -- right-associative, and right side is a factor (allows unary)
        # factor := ('+' | '-') factor | power
        # Let me restructure:
        # 
        # The precedence from highest to lowest:
        # 1. parentheses
        # 2. ** (right-associative)
        # 3. unary +/-
        # 4. * / // %
        # 5. + -
        #
        # So:
        # expression := term (('+' | '-') term)*
        # term := unary (('*' | '/' | '//' | '%') unary)*
        # unary := ('+' | '-') unary | power
        # power := primary ('**' unary)?   -- right-associative, right operand is unary (so 2**-1 works)
        # primary := NUMBER | '(' expression ')'

        tok = self._peek()
        if tok.kind == TOK_PLUS or tok.kind == TOK_MINUS:
            self._advance()
            operand = self._factor()
            if tok.kind == TOK_MINUS:
                return -operand
            else:
                return +operand
        else:
            return self._power()

    def _power(self) -> int | float:
        # power := primary ('**' factor)?  -- right-associative
        base = self._primary()
        if self._peek().kind == TOK_POW:
            self._advance()
            # Right side is a factor (allows unary signs)
            exponent = self._factor()
            # Python semantics for **
            if base == 0 and exponent < 0:
                raise ZeroDivisionError("0 ** negative number")
            return base ** exponent
        return base

    def _primary(self) -> int | float:
        tok = self._peek()
        if tok.kind == TOK_NUM:
            self._advance()
            return tok.value
        if tok.kind == TOK_LPAREN:
            self._advance()
            # Check for empty parentheses
            if self._peek().kind == TOK_RPAREN:
                raise ValueError("empty parentheses")
            result = self._expression()
            self._expect(TOK_RPAREN)
            return result
        raise ValueError(f"unexpected token {tok.kind}")


def evaluate(expr: str) -> int | float:
    if not expr or not expr.strip():
        raise ValueError("empty expression")
    tokens = _tokenize(expr)
    parser = _Parser(tokens)
    return parser.parse()
