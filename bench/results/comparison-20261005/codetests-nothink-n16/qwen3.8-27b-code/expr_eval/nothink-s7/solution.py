"""Arithmetic expression evaluator without eval/exec/compile/ast."""

from __future__ import annotations

import re
from typing import List, Tuple, Union

Number = Union[int, float]
Token = Tuple[str, str]  # (kind, value)


class _Tokenizer:
    """Tokenizes an arithmetic expression string."""

    _NUMBER_RE = re.compile(r"(\d+\.?\d*|\.\d+|\d+\.)")
    _WHITESPACE_RE = re.compile(r"[ \t]+")

    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0
        self.n = len(text)

    def _skip_whitespace(self) -> None:
        while self.pos < self.n and self.text[self.pos] in " \t":
            self.pos += 1

    def _peek(self) -> str:
        if self.pos < self.n:
            return self.text[self.pos]
        return ""

    def _advance(self) -> str:
        ch = self.text[self.pos]
        self.pos += 1
        return ch

    def _read_number(self) -> str:
        start = self.pos
        # Match digits, optional dot, optional digits
        # Patterns: 123, 123., 123.45, .45
        while self.pos < self.n:
            ch = self.text[self.pos]
            if ch.isdigit():
                self.pos += 1
            elif ch == "." and self.pos > start:
                # Check that we haven't already consumed a dot
                if "." in self.text[start:self.pos]:
                    raise ValueError(f"Malformed number at position {start}")
                self.pos += 1
                # After dot, must have at least one digit or end
                if self.pos >= self.n or not self.text[self.pos].isdigit():
                    # Allow trailing dot like "2."
                    if self.text[start:self.pos].count(".") == 1:
                        break
                    else:
                        raise ValueError(f"Malformed number at position {start}")
            else:
                break
        num_str = self.text[start:self.pos]
        if not num_str:
            raise ValueError(f"Empty number at position {start}")
        # Validate: no more than one dot
        if num_str.count(".") > 1:
            raise ValueError(f"Malformed number '{num_str}'")
        # Must have at least one digit
        if not any(c.isdigit() for c in num_str):
            raise ValueError(f"Malformed number '{num_str}'")
        return num_str

    def _read_operator(self) -> str:
        ch = self._peek()
        if ch == "*" and self.pos + 1 < self.n and self.text[self.pos + 1] == "*":
            self.pos += 2
            return "**"
        if ch == "/" and self.pos + 1 < self.n and self.text[self.pos + 1] == "/":
            self.pos += 2
            return "//"
        if ch in "+-*/%":
            self.pos += 1
            return ch
        raise ValueError(f"Invalid character '{ch}' at position {self.pos}")

    def tokenize(self) -> List[Token]:
        tokens: List[Token] = []
        while True:
            self._skip_whitespace()
            if self.pos >= self.n:
                break
            ch = self._peek()
            if ch.isdigit() or ch == ".":
                num_str = self._read_number()
                tokens.append(("NUMBER", num_str))
            elif ch in "+-*/%":
                op = self._read_operator()
                tokens.append(("OP", op))
            elif ch == "(":
                self._advance()
                tokens.append(("LPAREN", "("))
            elif ch == ")":
                self._advance()
                tokens.append(("RPAREN", ")"))
            else:
                raise ValueError(f"Invalid character '{ch}' at position {self.pos}")
        return tokens


class _Parser:
    """
    Recursive descent parser for arithmetic expressions.

    Grammar:
        expr        := term (('+' | '-') term)*
        term        := factor (('*' | '/' | '//' | '%') factor)*
        factor      := ('+' | '-')* power
        power       := atom ('**' factor)?
        atom        := NUMBER | '(' expr ')'

    Note: In Python, unary operators have lower precedence than ** on the left,
    but the right operand of ** can include unary operators.
    
    Actually, let me reconsider the grammar to match Python semantics exactly:
    
    Python's actual precedence (high to low):
    1. ** (right-associative)
    2. Unary +, -
    3. *, /, //, %
    4. +, -
    
    So -2**2 = -(2**2) = -4
    And 2**-1 = 2**(-1) = 0.5
    
    The grammar should be:
        expr        := term (('+' | '-') term)*
        term        := unary (('*' | '/' | '//' | '%') unary)*
        unary       := ('+' | '-') unary | power
        power       := atom ('**' unary)?
        atom        := NUMBER | '(' expr ')'
    """

    def __init__(self, tokens: List[Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    def _peek(self) -> Token:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return ("EOF", "")

    def _advance(self) -> Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def _expect(self, kind: str, value: str = None) -> Token:
        tok = self._peek()
        if tok[0] != kind:
            raise ValueError(f"Expected {kind} but got {tok[0]}: {tok[1]}")
        if value is not None and tok[1] != value:
            raise ValueError(f"Expected '{value}' but got '{tok[1]}'")
        return self._advance()

    def parse(self) -> Number:
        if not self.tokens:
            raise ValueError("Empty expression")
        result = self._expr()
        if self.pos != len(self.tokens):
            raise ValueError(f"Unexpected token: {self._peek()}")
        return result

    def _expr(self) -> Number:
        result = self._term()
        while self._peek()[0] == "OP" and self._peek()[1] in ("+", "-"):
            op = self._advance()[1]
            right = self._term()
            if op == "+":
                result = result + right
            else:
                result = result - right
        return result

    def _term(self) -> Number:
        result = self._unary()
        while self._peek()[0] == "OP" and self._peek()[1] in ("*", "/", "//", "%"):
            op = self._advance()[1]
            right = self._unary()
            if op == "*":
                result = result * right
            elif op == "/":
                if right == 0:
                    raise ZeroDivisionError("division by zero")
                result = result / right
            elif op == "//":
                if right == 0:
                    raise ZeroDivisionError("division by zero")
                result = result // right
            elif op == "%":
                if right == 0:
                    raise ZeroDivisionError("modulo by zero")
                result = result % right
        return result

    def _unary(self) -> Number:
        if self._peek()[0] == "OP" and self._peek()[1] in ("+", "-"):
            op = self._advance()[1]
            operand = self._unary()
            if op == "+":
                return +operand
            else:
                return -operand
        return self._power()

    def _power(self) -> Number:
        base = self._atom()
        if self._peek()[0] == "OP" and self._peek()[1] == "**":
            self._advance()
            # Right operand can include unary operators
            exponent = self._unary()
            if base == 0 and exponent < 0:
                raise ZeroDivisionError("0.0 cannot be raised to a negative power")
            result = base ** exponent
            return result
        return base

    def _atom(self) -> Number:
        tok = self._peek()
        if tok[0] == "NUMBER":
            self._advance()
            num_str = tok[1]
            if "." in num_str:
                return float(num_str)
            else:
                return int(num_str)
        elif tok[0] == "LPAREN":
            self._advance()
            result = self._expr()
            self._expect("RPAREN")
            return result
        else:
            raise ValueError(f"Unexpected token: {tok}")


def evaluate(expr: str) -> int | float:
    """Evaluate an arithmetic expression string and return the result."""
    if not expr or not expr.strip():
        raise ValueError("Empty expression")
    tokens = _Tokenizer(expr).tokenize()
    if not tokens:
        raise ValueError("Empty expression")
    parser = _Parser(tokens)
    return parser.parse()
