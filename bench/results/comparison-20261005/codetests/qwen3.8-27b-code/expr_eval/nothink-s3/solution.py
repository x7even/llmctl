"""Arithmetic expression evaluator with a real tokenizer + parser."""

from __future__ import annotations
import math
import re

__all__ = ["evaluate"]


class _Tokenizer:
    """Tokenizes an arithmetic expression into a list of tokens."""

    # Token kinds
    NUMBER = "NUMBER"
    PLUS = "PLUS"
    MINUS = "MINUS"
    STAR = "STAR"
    SLASH = "SLASH"
    DSTAR = "DSTAR"
    DSLASH = "DSLASH"
    PERCENT = "PERCENT"
    LPAREN = "LPAREN"
    RPAREN = "RPAREN"
    EOF = "EOF"

    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.tokens: list[tuple[str, object]] = []

    def tokenize(self) -> list[tuple[str, object]]:
        text = self.text
        n = len(text)
        i = 0
        tokens: list[tuple[str, object]] = []

        while i < n:
            ch = text[i]

            # Skip whitespace
            if ch in " \t\r\n":
                i += 1
                continue

            # Numbers
            if ch.isdigit() or ch == ".":
                start = i
                # Handle decimal numbers
                # A number can be: digits, digits.digits, digits., .digits
                # No exponent notation, no underscores, no hex
                if ch == ".":
                    # Must be followed by a digit to be a valid number start
                    if i + 1 < n and text[i + 1].isdigit():
                        i += 1
                        while i < n and text[i].isdigit():
                            i += 1
                        # Optionally a trailing part after dot? No, .5 is valid, but .5. is not
                        # Actually .5 is valid. Let's just take the digits after dot.
                        num_str = text[start:i]
                        tokens.append((self.NUMBER, float(num_str)))
                    else:
                        raise ValueError(f"Invalid number at position {start}: lone '.'")
                else:
                    # Start with a digit
                    while i < n and text[i].isdigit():
                        i += 1
                    # Check for decimal point
                    if i < n and text[i] == ".":
                        i += 1
                        # After the dot, we need at least one digit? No, "2." is valid.
                        # But "1..2" is invalid.
                        # If next char is a dot, that's invalid.
                        if i < n and text[i] == ".":
                            raise ValueError(f"Invalid number at position {start}: malformed number")
                        while i < n and text[i].isdigit():
                            i += 1
                    num_str = text[start:i]
                    if "." in num_str:
                        tokens.append((self.NUMBER, float(num_str)))
                    else:
                        tokens.append((self.NUMBER, int(num_str)))
                continue

            # Operators and parentheses
            if ch == "+":
                tokens.append((self.PLUS, "+"))
                i += 1
            elif ch == "-":
                tokens.append((self.MINUS, "-"))
                i += 1
            elif ch == "*":
                if i + 1 < n and text[i + 1] == "*":
                    tokens.append((self.DSTAR, "**"))
                    i += 2
                else:
                    tokens.append((self.STAR, "*"))
                    i += 1
            elif ch == "/":
                if i + 1 < n and text[i + 1] == "/":
                    tokens.append((self.DSLASH, "//"))
                    i += 2
                else:
                    tokens.append((self.SLASH, "/"))
                    i += 1
            elif ch == "%":
                tokens.append((self.PERCENT, "%"))
                i += 1
            elif ch == "(":
                tokens.append((self.LPAREN, "("))
                i += 1
            elif ch == ")":
                tokens.append((self.RPAREN, ")"))
                i += 1
            else:
                raise ValueError(f"Invalid character '{ch}' at position {i}")

        tokens.append((self.EOF, None))
        return tokens


class _Parser:
    """Recursive descent parser for arithmetic expressions."""

    def __init__(self, tokens: list[tuple[str, object]]):
        self.tokens = tokens
        self.pos = 0

    def current(self) -> tuple[str, object]:
        return self.tokens[self.pos]

    def advance(self) -> tuple[str, object]:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def expect(self, kind: str) -> tuple[str, object]:
        tok = self.current()
        if tok[0] != kind:
            raise ValueError(f"Expected {kind}, got {tok[0]}")
        return self.advance()

    def parse(self) -> int | float:
        if self.current()[0] == _Tokenizer.EOF:
            raise ValueError("Empty expression")
        result = self.parse_expr()
        if self.current()[0] != _Tokenizer.EOF:
            raise ValueError(f"Unexpected token after expression: {self.current()[0]}")
        return result

    def parse_expr(self) -> int | float:
        """expr := term (('+' | '-') term)*"""
        left = self.parse_term()
        while self.current()[0] in (_Tokenizer.PLUS, _Tokenizer.MINUS):
            op = self.advance()[0]
            right = self.parse_term()
            if op == _Tokenizer.PLUS:
                left = left + right
            else:
                left = left - right
        return left

    def parse_term(self) -> int | float:
        """term := factor (('*' | '/' | '//' | '%') factor)*"""
        left = self.parse_factor()
        while self.current()[0] in (_Tokenizer.STAR, _Tokenizer.SLASH, _Tokenizer.DSLASH, _Tokenizer.PERCENT):
            op = self.advance()[0]
            right = self.parse_factor()
            if op == _Tokenizer.STAR:
                left = left * right
            elif op == _Tokenizer.SLASH:
                if right == 0:
                    raise ZeroDivisionError("division by zero")
                left = left / right
            elif op == _Tokenizer.DSLASH:
                if right == 0:
                    raise ZeroDivisionError("division by zero")
                left = left // right
            elif op == _Tokenizer.PERCENT:
                if right == 0:
                    raise ZeroDivisionError("modulo by zero")
                left = left % right
        return left

    def parse_factor(self) -> int | float:
        """factor := ('+' | '-') factor | power"""
        if self.current()[0] in (_Tokenizer.PLUS, _Tokenizer.MINUS):
            op = self.advance()[0]
            operand = self.parse_factor()
            if op == _Tokenizer.PLUS:
                return +operand
            else:
                return -operand
        return self.parse_power()

    def parse_power(self) -> int | float:
        """power := atom ('**' factor)?  -- right-associative, right side is a factor (allows unary)"""
        base = self.parse_atom()
        if self.current()[0] == _Tokenizer.DSTAR:
            self.advance()
            # Right side is a factor, which allows unary signs
            exponent = self.parse_factor()
            try:
                return base ** exponent
            except ZeroDivisionError:
                raise
            except OverflowError:
                # Python's ** can overflow for large ints, but that's fine
                raise
        return base

    def parse_atom(self) -> int | float:
        """atom := NUMBER | '(' expr ')'"""
        tok = self.current()
        if tok[0] == _Tokenizer.NUMBER:
            self.advance()
            return tok[1]
        if tok[0] == _Tokenizer.LPAREN:
            self.advance()
            # Check for empty parentheses
            if self.current()[0] == _Tokenizer.RPAREN:
                raise ValueError("Empty parentheses")
            result = self.parse_expr()
            self.expect(_Tokenizer.RPAREN)
            return result
        raise ValueError(f"Unexpected token: {tok[0]}")


def evaluate(expr: str) -> int | float:
    """Evaluate an arithmetic expression and return the result.
    
    Supports: +, -, *, /, //, %, **, unary +/-, parentheses.
    Semantics match Python's arithmetic for this subset.
    
    Raises:
        ValueError: for malformed input
        ZeroDivisionError: for division/modulo by zero or 0 ** negative
    """
    if not expr or not expr.strip():
        raise ValueError("Empty expression")
    
    tokenizer = _Tokenizer(expr)
    tokens = tokenizer.tokenize()
    parser = _Parser(tokens)
    return parser.parse()
