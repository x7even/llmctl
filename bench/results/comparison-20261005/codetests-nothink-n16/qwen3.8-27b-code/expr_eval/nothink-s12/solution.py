"""Arithmetic expression evaluator without eval/exec/compile/ast."""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Union


class TokenType(Enum):
    NUMBER = auto()
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    DOUBLE_SLASH = auto()
    PERCENT = auto()
    DOUBLE_STAR = auto()
    LPAREN = auto()
    RPAREN = auto()
    EOF = auto()


@dataclass
class Token:
    type: TokenType
    value: Union[int, float, str]
    pos: int


class Tokenizer:
    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.tokens: List[Token] = []

    def tokenize(self) -> List[Token]:
        while self.pos < len(self.text):
            ch = self.text[self.pos]
            if ch in ' \t':
                self.pos += 1
                continue
            if ch.isdigit() or ch == '.':
                self._read_number()
            elif ch == '+':
                self.tokens.append(Token(TokenType.PLUS, '+', self.pos))
                self.pos += 1
            elif ch == '-':
                self.tokens.append(Token(TokenType.MINUS, '-', self.pos))
                self.pos += 1
            elif ch == '*':
                if self.pos + 1 < len(self.text) and self.text[self.pos + 1] == '*':
                    self.tokens.append(Token(TokenType.DOUBLE_STAR, '**', self.pos))
                    self.pos += 2
                else:
                    self.tokens.append(Token(TokenType.STAR, '*', self.pos))
                    self.pos += 1
            elif ch == '/':
                if self.pos + 1 < len(self.text) and self.text[self.pos + 1] == '/':
                    self.tokens.append(Token(TokenType.DOUBLE_SLASH, '//', self.pos))
                    self.pos += 2
                else:
                    self.tokens.append(Token(TokenType.SLASH, '/', self.pos))
                    self.pos += 1
            elif ch == '%':
                self.tokens.append(Token(TokenType.PERCENT, '%', self.pos))
                self.pos += 1
            elif ch == '(':
                self.tokens.append(Token(TokenType.LPAREN, '(', self.pos))
                self.pos += 1
            elif ch == ')':
                self.tokens.append(Token(TokenType.RPAREN, ')', self.pos))
                self.pos += 1
            else:
                raise ValueError(f"Invalid character '{ch}' at position {self.pos}")

        self.tokens.append(Token(TokenType.EOF, None, self.pos))
        return self.tokens

    def _read_number(self):
        start = self.pos
        has_dot = False
        has_digit = False

        while self.pos < len(self.text):
            ch = self.text[self.pos]
            if ch.isdigit():
                has_digit = True
                self.pos += 1
            elif ch == '.':
                if has_dot:
                    raise ValueError(f"Malformed number at position {start}")
                has_dot = True
                self.pos += 1
            else:
                break

        if not has_digit:
            raise ValueError(f"Malformed number at position {start}")

        num_str = self.text[start:self.pos]
        if has_dot:
            self.tokens.append(Token(TokenType.NUMBER, float(num_str), start))
        else:
            self.tokens.append(Token(TokenType.NUMBER, int(num_str), start))


class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0

    def current(self) -> Token:
        return self.tokens[self.pos]

    def consume(self, expected_type: TokenType = None) -> Token:
        tok = self.current()
        if expected_type is not None and tok.type != expected_type:
            raise ValueError(f"Expected {expected_type.name} but got {tok.type.name} at position {tok.pos}")
        self.pos += 1
        return tok

    def parse(self) -> Union[int, float]:
        if self.current().type == TokenType.EOF:
            raise ValueError("Empty expression")
        result = self.parse_expression()
        if self.current().type != TokenType.EOF:
            raise ValueError(f"Unexpected token {self.current().type.name} at position {self.current().pos}")
        return result

    def parse_expression(self) -> Union[int, float]:
        return self.parse_additive()

    def parse_additive(self) -> Union[int, float]:
        left = self.parse_multiplicative()
        while self.current().type in (TokenType.PLUS, TokenType.MINUS):
            op = self.consume()
            right = self.parse_multiplicative()
            if op.type == TokenType.PLUS:
                left = left + right
            else:
                left = left - right
        return left

    def parse_multiplicative(self) -> Union[int, float]:
        left = self.parse_unary()
        while self.current().type in (TokenType.STAR, TokenType.SLASH, TokenType.DOUBLE_SLASH, TokenType.PERCENT):
            op = self.consume()
            right = self.parse_unary()
            if op.type == TokenType.STAR:
                left = left * right
            elif op.type == TokenType.SLASH:
                if right == 0:
                    raise ZeroDivisionError("division by zero")
                left = left / right
            elif op.type == TokenType.DOUBLE_SLASH:
                if right == 0:
                    raise ZeroDivisionError("integer division or modulo by zero")
                left = left // right
            else:  # PERCENT
                if right == 0:
                    raise ZeroDivisionError("integer division or modulo by zero")
                left = left % right
        return left

    def parse_unary(self) -> Union[int, float]:
        if self.current().type in (TokenType.PLUS, TokenType.MINUS):
            op = self.consume()
            operand = self.parse_unary()
            if op.type == TokenType.MINUS:
                return -operand
            else:
                return +operand
        return self.parse_power()

    def parse_power(self) -> Union[int, float]:
        base = self.parse_primary()
        if self.current().type == TokenType.DOUBLE_STAR:
            self.consume()
            exponent = self.parse_unary()
            if base == 0 and exponent < 0:
                raise ZeroDivisionError("0.0 cannot be raised to a negative power")
            result = base ** exponent
            return result
        return base

    def parse_primary(self) -> Union[int, float]:
        tok = self.current()
        if tok.type == TokenType.NUMBER:
            self.consume()
            return tok.value
        elif tok.type == TokenType.LPAREN:
            self.consume()
            if self.current().type == TokenType.RPAREN:
                raise ValueError("Empty parentheses")
            expr = self.parse_expression()
            self.consume(TokenType.RPAREN)
            return expr
        else:
            raise ValueError(f"Unexpected token {tok.type.name} at position {tok.pos}")


def evaluate(expr: str) -> Union[int, float]:
    if not expr or not expr.strip():
        raise ValueError("Empty expression")
    tokenizer = Tokenizer(expr)
    tokens = tokenizer.tokenize()
    parser = Parser(tokens)
    return parser.parse()
