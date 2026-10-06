"""Arithmetic expression evaluator (no eval/exec/compile/ast)."""

from __future__ import annotations

# ---------- Tokenizer ----------

class _Token:
    __slots__ = ("kind", "value")

    def __init__(self, kind: str, value):
        self.kind = kind
        self.value = value

    def __repr__(self) -> str:
        return f"Token({self.kind!r}, {self.value!r})"


def _tokenize(expr: str) -> list[_Token]:
    tokens: list[_Token] = []
    i = 0
    n = len(expr)
    while i < n:
        ch = expr[i]
        if ch in " \t\r\n":
            i += 1
            continue
        # Numbers
        if ch.isdigit() or ch == ".":
            start = i
            seen_dot = False
            seen_digit = False
            # Consume digits and at most one dot
            while i < n:
                c = expr[i]
                if c.isdigit():
                    seen_digit = True
                    i += 1
                elif c == "." and not seen_dot:
                    seen_dot = True
                    i += 1
                else:
                    break
            text = expr[start:i]
            # Validate: must have at least one digit, and if dot present,
            # must not be just "."
            if not seen_digit:
                raise ValueError(f"Invalid number literal: {text!r}")
            # Check next char: if it's a digit or dot, that means something
            # like "1.2.3" or "1..2" -- but our loop already stops at second dot.
            # Actually, the loop stops when it hits a non-digit, non-dot (or second dot).
            # If text is "1." or ".5" or "3.5" that's fine.
            # But we need to ensure we didn't have something like "1..2":
            # The loop would consume "1." then stop at the second "." because seen_dot is True.
            # Then text = "1." and the next char is "." which would be tokenized separately.
            # We need to detect that case: if the next char is a digit or dot, it's malformed.
            if i < n and (expr[i].isdigit() or expr[i] == "."):
                raise ValueError(f"Malformed number literal near position {start}")
            if seen_dot:
                # Must have digits on at least one side
                # ".5" -> seen_digit True, ok. "2." -> seen_digit True, ok.
                # But "." alone -> seen_digit False, already caught.
                pass
            tokens.append(_Token("NUMBER", text))
            continue
        # Operators
        if ch == "+":
            tokens.append(_Token("PLUS", "+"))
            i += 1
            continue
        if ch == "-":
            tokens.append(_Token("MINUS", "-"))
            i += 1
            continue
        if ch == "*":
            if i + 1 < n and expr[i + 1] == "*":
                tokens.append(_Token("POW", "**"))
                i += 2
            else:
                tokens.append(_Token("MUL", "*"))
                i += 1
            continue
        if ch == "/":
            if i + 1 < n and expr[i + 1] == "/":
                tokens.append(_Token("FLOORDIV", "//"))
                i += 2
            else:
                tokens.append(_Token("DIV", "/"))
                i += 1
            continue
        if ch == "%":
            tokens.append(_Token("MOD", "%"))
            i += 1
            continue
        if ch == "(":
            tokens.append(_Token("LPAREN", "("))
            i += 1
            continue
        if ch == ")":
            tokens.append(_Token("RPAREN", ")"))
            i += 1
            continue
        raise ValueError(f"Invalid character: {ch!r}")
    return tokens


# ---------- Parser (recursive descent) ----------
#
# Grammar (matching Python precedence):
#   expr       -> term (('+' | '-') term)*
#   term       -> factor (('*' | '/' | '//' | '%') factor)*
#   factor     -> ('+' | '-') factor | power
#   power      -> atom ('**' factor)?    # right-associative, exponent can have unary
#   atom       -> NUMBER | '(' expr ')'
#
# Note: In Python, unary operators bind tighter than ** on the left,
# but the right side of ** can include unary operators.
# So: -2 ** 2 = -(2**2) = -4
#     2 ** -1 = 2 ** (-1) = 0.5
#
# The standard way to handle this in a parser:
#   unary_expr -> ('+'|'-') unary_expr | power_expr
#   power_expr -> primary ('**' unary_expr)?   # right-assoc, right side is unary_expr
#   primary    -> NUMBER | '(' expr ')'
#
# Wait, let me reconsider. Python's grammar:
#   u_expr: power | "-" u_expr | "+" u_expr
#   power: primary ["**" u_expr]
#
# So the right operand of ** is a u_expr (which can have unary signs),
# and the left operand is a primary (no unary signs on the left of **).
# This means:
#   -2 ** 2: the "-" applies to the result of (2 ** 2) because the left of ** is primary "2",
#            and the unary minus is outside. So it's -(2**2) = -4.
#   2 ** -1: right side is u_expr which can be "-1". So 2 ** (-1) = 0.5.
#   2 ** 3 ** 2: right-assoc, so 2 ** (3 ** 2) = 2 ** 9 = 512.
#   2 ** -2 ** 2: right side is u_expr = "-2 ** 2". The u_expr for "-2 ** 2" is:
#                 "-" u_expr, where u_expr is "2 ** 2" = 4. So "-4". Then 2 ** (-4) = 0.0625.
#
# So the grammar is:
#   expr       -> term (('+' | '-') term)*
#   term       -> unary (('*' | '/' | '//' | '%') unary)*
#   unary      -> ('+' | '-') unary | power
#   power      -> primary ('**' unary)?
#   primary    -> NUMBER | '(' expr ')'

class _Parser:
    def __init__(self, tokens: list[_Token]):
        self.tokens = tokens
        self.pos = 0

    def _peek(self) -> _Token | None:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def _advance(self) -> _Token:
        tok = self._peek()
        if tok is None:
            raise ValueError("Unexpected end of expression")
        self.pos += 1
        return tok

    def _expect(self, kind: str) -> _Token:
        tok = self._peek()
        if tok is None or tok.kind != kind:
            expected = kind
            got = tok.kind if tok else "end of input"
            raise ValueError(f"Expected {expected}, got {got}")
        return self._advance()

    def parse(self) -> int | float:
        if not self.tokens:
            raise ValueError("Empty expression")
        result = self._expr()
        if self.pos != len(self.tokens):
            raise ValueError(f"Unexpected token: {self.tokens[self.pos].kind!r}")
        return result

    def _expr(self) -> int | float:
        left = self._term()
        while True:
            tok = self._peek()
            if tok is None:
                break
            if tok.kind == "PLUS":
                self._advance()
                right = self._term()
                left = left + right
            elif tok.kind == "MINUS":
                self._advance()
                right = self._term()
                left = left - right
            else:
                break
        return left

    def _term(self) -> int | float:
        left = self._unary()
        while True:
            tok = self._peek()
            if tok is None:
                break
            if tok.kind == "MUL":
                self._advance()
                right = self._unary()
                left = left * right
            elif tok.kind == "DIV":
                self._advance()
                right = self._unary()
                if right == 0:
                    raise ZeroDivisionError("division by zero")
                left = left / right
            elif tok.kind == "FLOORDIV":
                self._advance()
                right = self._unary()
                if right == 0:
                    raise ZeroDivisionError("integer division or modulo by zero")
                left = left // right
            elif tok.kind == "MOD":
                self._advance()
                right = self._unary()
                if right == 0:
                    raise ZeroDivisionError("integer division or modulo by zero")
                left = left % right
            else:
                break
        return left

    def _unary(self) -> int | float:
        tok = self._peek()
        if tok is not None and tok.kind == "PLUS":
            self._advance()
            operand = self._unary()
            return +operand
        if tok is not None and tok.kind == "MINUS":
            self._advance()
            operand = self._unary()
            return -operand
        return self._power()

    def _power(self) -> int | float:
        base = self._primary()
        tok = self._peek()
        if tok is not None and tok.kind == "POW":
            self._advance()
            # Right operand is a unary expression (can have unary signs)
            exponent = self._unary()
            return self._pow(base, exponent)
        return base

    def _pow(self, base: int | float, exponent: int | float) -> int | float:
        # Handle 0 ** negative
        if base == 0 and isinstance(exponent, (int, float)) and exponent < 0:
            raise ZeroDivisionError("0.0 cannot be raised to a negative power")
        # In Python, int ** negative int -> float
        if isinstance(base, int) and isinstance(exponent, int) and exponent < 0:
            return float(base) ** float(exponent)
        # int ** int -> int (if exponent >= 0)
        # float ** anything -> float
        # int ** float -> float
        result = base ** exponent
        # Python's ** on two ints with non-negative exponent gives int
        if isinstance(base, int) and isinstance(exponent, int) and exponent >= 0:
            return int(result)
        return result

    def _primary(self) -> int | float:
        tok = self._peek()
        if tok is None:
            raise ValueError("Unexpected end of expression")
        if tok.kind == "NUMBER":
            self._advance()
            text = tok.value
            if "." in text:
                return float(text)
            return int(text)
        if tok.kind == "LPAREN":
            self._advance()
            result = self._expr()
            self._expect("RPAREN")
            return result
        raise ValueError(f"Unexpected token: {tok.kind!r}")


def evaluate(expr: str) -> int | float:
    if not isinstance(expr, str):
        raise ValueError("Expression must be a string")
    if not expr.strip():
        raise ValueError("Empty expression")
    tokens = _tokenize(expr)
    if not tokens:
        raise ValueError("Empty expression")
    parser = _Parser(tokens)
    return parser.parse()
