"""Arithmetic expression evaluator with hand-written tokenizer and recursive-descent parser."""

from __future__ import annotations


class _Token:
    __slots__ = ("type", "value")

    def __init__(self, type_: str, value):
        self.type = type_
        self.value = value

    def __repr__(self):
        return f"Token({self.type}, {self.value!r})"


def _tokenize(expr: str) -> list[_Token]:
    tokens: list[_Token] = []
    i = 0
    n = len(expr)

    while i < n:
        ch = expr[i]

        # Skip whitespace (spaces and tabs)
        if ch in (" ", "\t"):
            i += 1
            continue

        # Number literals
        if ch.isdigit() or ch == ".":
            start = i
            if ch == ".":
                i += 1
                if i >= n or not expr[i].isdigit():
                    raise ValueError("Invalid number: lone '.'")
                while i < n and expr[i].isdigit():
                    i += 1
            else:
                while i < n and expr[i].isdigit():
                    i += 1
                if i < n and expr[i] == ".":
                    i += 1
                    while i < n and expr[i].isdigit():
                        i += 1

            # Detect malformed numbers like 1..2, 1.2.3, 1.2e3, etc.
            if i < n and (expr[i].isdigit() or expr[i] == "."):
                raise ValueError(f"Malformed number starting at position {start}")

            num_str = expr[start:i]
            if "." in num_str:
                tokens.append(_Token("NUMBER", float(num_str)))
            else:
                tokens.append(_Token("NUMBER", int(num_str)))
            continue

        # Two-character operators
        if ch == "*":
            if i + 1 < n and expr[i + 1] == "*":
                tokens.append(_Token("OP", "**"))
                i += 2
            else:
                tokens.append(_Token("OP", "*"))
                i += 1
        elif ch == "/":
            if i + 1 < n and expr[i + 1] == "/":
                tokens.append(_Token("OP", "//"))
                i += 2
            else:
                tokens.append(_Token("OP", "/"))
                i += 1
        elif ch == "+":
            tokens.append(_Token("OP", "+"))
            i += 1
        elif ch == "-":
            tokens.append(_Token("OP", "-"))
            i += 1
        elif ch == "%":
            tokens.append(_Token("OP", "%"))
            i += 1
        elif ch == "(":
            tokens.append(_Token("LPAREN", "("))
            i += 1
        elif ch == ")":
            tokens.append(_Token("RPAREN", ")"))
            i += 1
        else:
            raise ValueError(f"Invalid character: {ch!r}")

    return tokens


class _Parser:
    def __init__(self, tokens: list[_Token]) -> None:
        self._tokens = tokens
        self._pos = 0

    # ------------------------------------------------------------------ helpers
    def _peek(self) -> _Token | None:
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return None

    def _consume(self) -> _Token:
        tok = self._peek()
        if tok is None:
            raise ValueError("Unexpected end of expression")
        self._pos += 1
        return tok

    # --------------------------------------------------------------- grammar
    # expr   : term (('+' | '-') term)*
    # term   : factor (('*' | '/' | '//' | '%') factor)*
    # factor : ('+' | '-') factor | power
    # power  : atom ('**' factor)?
    # atom   : NUMBER | '(' expr ')'

    def parse(self) -> int | float:
        if not self._tokens:
            raise ValueError("Empty expression")
        result = self._expr()
        if self._pos < len(self._tokens):
            raise ValueError(
                f"Unexpected token after expression: {self._tokens[self._pos]!r}"
            )
        return result

    def _expr(self) -> int | float:
        result = self._term()
        while True:
            tok = self._peek()
            if tok is not None and tok.type == "OP" and tok.value in ("+", "-"):
                self._consume()
                right = self._term()
                result = result + right if tok.value == "+" else result - right
            else:
                break
        return result

    def _term(self) -> int | float:
        result = self._factor()
        while True:
            tok = self._peek()
            if tok is not None and tok.type == "OP" and tok.value in ("*", "/", "//", "%"):
                self._consume()
                right = self._factor()
                if tok.value == "*":
                    result = result * right
                elif tok.value == "/":
                    result = result / right
                elif tok.value == "//":
                    result = result // right
                else:
                    result = result % right
            else:
                break
        return result

    def _factor(self) -> int | float:
        tok = self._peek()
        if tok is not None and tok.type == "OP" and tok.value in ("+", "-"):
            self._consume()
            operand = self._factor()
            return -operand if tok.value == "-" else operand
        return self._power()

    def _power(self) -> int | float:
        base = self._atom()
        tok = self._peek()
        if tok is not None and tok.type == "OP" and tok.value == "**":
            self._consume()
            exponent = self._factor()  # right-associative; allows unary on right
            return base ** exponent
        return base

    def _atom(self) -> int | float:
        tok = self._peek()
        if tok is None:
            raise ValueError("Unexpected end of expression")

        if tok.type == "NUMBER":
            self._consume()
            return tok.value

        if tok.type == "LPAREN":
            self._consume()
            # Check for empty parentheses
            nxt = self._peek()
            if nxt is not None and nxt.type == "RPAREN":
                raise ValueError("Empty parentheses")
            result = self._expr()
            if self._peek() is None or self._peek().type != "RPAREN":
                raise ValueError("Unbalanced parentheses")
            self._consume()
            return result

        raise ValueError(f"Unexpected token: {tok!r}")


def evaluate(expr: str) -> int | float:
    """Evaluate an arithmetic expression string and return an int or float.

    Raises ValueError for malformed input, ZeroDivisionError for division by zero.
    """
    tokens = _tokenize(expr)
    parser = _Parser(tokens)
    return parser.parse()
