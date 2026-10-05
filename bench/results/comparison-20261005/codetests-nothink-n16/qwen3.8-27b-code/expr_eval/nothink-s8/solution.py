"""Arithmetic expression evaluator with a real tokenizer + parser.

No eval/exec/compile/ast. Standard library only.
"""

from __future__ import annotations

import re
from typing import List, Tuple, Union

Number = Union[int, float]

# Token kinds
TOK_NUM = 'NUM'
TOK_OP = 'OP'
TOK_LPAREN = 'LPAREN'
TOK_RPAREN = 'RPAREN'
TOK_EOF = 'EOF'

# Token is (kind, value, pos)
Token = Tuple[str, object, int]


def _tokenize(expr: str) -> List[Token]:
    tokens: List[Token] = []
    i = 0
    n = len(expr)
    while i < n:
        ch = expr[i]
        if ch in ' \t':
            i += 1
            continue
        if ch == '(':
            tokens.append((TOK_LPAREN, '(', i))
            i += 1
            continue
        if ch == ')':
            tokens.append((TOK_RPAREN, ')', i))
            i += 1
            continue
        # Number: integer or decimal
        # A number can start with a digit or a dot.
        if ch.isdigit() or ch == '.':
            start = i
            # Consume digits
            while i < n and expr[i].isdigit():
                i += 1
            # If next is '.', consume it and following digits
            if i < n and expr[i] == '.':
                i += 1
                while i < n and expr[i].isdigit():
                    i += 1
                # After a dot, must have at least one digit or we need to check
                # Actually, "2." is valid, ".5" is valid.
                # But "1..2" is invalid. Let's check:
                # If we saw a dot, we consumed it. Now we check if next is also dot?
                # The while loop above consumed digits. If expr[i] is '.', we consumed it.
                # Then we consumed digits.
                # The problem "1..2": 
                # i=0: '1' -> digit, i=1
                # i=1: '.' -> dot, i=2
                # i=2: '.' -> not digit, stop. Token is "1."
                # Then next char is '.' -> will be parsed as another number start?
                # Let's trace "1..2":
                # Token 1: "1." (int or float? "1." is float 1.0)
                # i is now at second '.'
                # Next iteration: ch='.' -> number start
                # start=i, no digits, ch is '.', consume dot, i++, no digits.
                # Token is "." -> invalid number
                # So "1..2" will produce two tokens: "1." and "."
                # The parser will see two adjacent numbers -> ValueError
                # But we need to make sure "." alone is invalid.
                pass
            text = expr[start:i]
            # Validate the number text
            # It must be a valid number: digits, or digits.dot, or dot.digits, or digits
            # "2." is valid, ".5" is valid, "1.2" is valid
            # "." is invalid, "1.." is invalid (but that would be "1." then ".")
            # Let's check if text is valid
            if text == '.':
                raise ValueError(f"Invalid number at position {start}: '.'")
            # Check for multiple dots
            if text.count('.') > 1:
                raise ValueError(f"Invalid number at position {start}: {text!r}")
            # Check that if it starts with dot, it has digits after
            if text.startswith('.') and len(text) == 1:
                raise ValueError(f"Invalid number at position {start}: '.'")
            # Check that if it ends with dot, it has digits before
            if text.endswith('.') and len(text) == 1:
                raise ValueError(f"Invalid number at position {start}: '.'")
            # More robust: use regex
            if not re.fullmatch(r'(\d+\.?\d*|\.\d+)', text):
                raise ValueError(f"Invalid number at position {start}: {text!r}")
            # Determine if int or float
            if '.' in text:
                tokens.append((TOK_NUM, float(text), start))
            else:
                tokens.append((TOK_NUM, int(text), start))
            continue
        # Operators
        if ch == '*':
            if i + 1 < n and expr[i + 1] == '*':
                tokens.append((TOK_OP, '**', i))
                i += 2
            else:
                tokens.append((TOK_OP, '*', i))
                i += 1
            continue
        if ch == '/':
            if i + 1 < n and expr[i + 1] == '/':
                tokens.append((TOK_OP, '//', i))
                i += 2
            else:
                tokens.append((TOK_OP, '/', i))
                i += 1
            continue
        if ch in '+-':
            tokens.append((TOK_OP, ch, i))
            i += 1
            continue
        if ch == '%':
            tokens.append((TOK_OP, '%', i))
            i += 1
            continue
        # Invalid character
        raise ValueError(f"Invalid character at position {i}: {ch!r}")
    tokens.append((TOK_EOF, None, n))
    return tokens


class _Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0

    def _current(self) -> Token:
        return self.tokens[self.pos]

    def _advance(self) -> Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def _expect(self, kind: str) -> Token:
        tok = self._current()
        if tok[0] != kind:
            raise ValueError(f"Expected {kind}, got {tok[0]} at position {tok[2]}")
        return self._advance()

    def parse(self) -> Number:
        result = self._expr()
        if self._current()[0] != TOK_EOF:
            tok = self._current()
            raise ValueError(f"Unexpected token {tok[0]} at position {tok[2]}")
        return result

    def _expr(self) -> Number:
        # expr := term (('+' | '-') term)*
        left = self._term()
        while self._current()[0] == TOK_OP and self._current()[1] in ('+', '-'):
            op = self._advance()[1]
            right = self._term()
            if op == '+':
                left = left + right
            else:
                left = left - right
        return left

    def _term(self) -> Number:
        # term := factor (('*' | '/' | '//' | '%') factor)*
        left = self._factor()
        while self._current()[0] == TOK_OP and self._current()[1] in ('*', '/', '//', '%'):
            op = self._advance()[1]
            right = self._factor()
            if op == '*':
                left = left * right
            elif op == '/':
                if right == 0:
                    raise ZeroDivisionError("division by zero")
                left = left / right
            elif op == '//':
                if right == 0:
                    raise ZeroDivisionError("integer division or modulo by zero")
                left = left // right
            elif op == '%':
                if right == 0:
                    raise ZeroDivisionError("integer modulo by zero")
                left = left % right
        return left

    def _factor(self) -> Number:
        # factor := power | ('+' | '-') factor
        # But note: ** binds tighter than unary on the left.
        # In Python: -2 ** 2 == -4, which means unary minus applies to the result of 2**2.
        # So the grammar is:
        # factor := ('+' | '-') factor | power
        # power := atom ('**' factor)?  -- right associative, and the right side can have unary
        # Actually, let's think about this more carefully.
        # Python's grammar:
        # power: (await_expr | primary) ['**' u_expr]
        # u_expr: power | '-' u_expr | '+' u_expr
        # So unary is above power. That means -2**2 is (-2)**2? No, Python says -2**2 == -4.
        # Let me check: In Python, -2**2 is -(2**2) = -4.
        # So unary minus has LOWER precedence than **.
        # So the grammar should be:
        # u_expr := ('+' | '-') u_expr | power
        # power := atom ('**' u_expr)?
        # This way, -2**2 is parsed as: u_expr sees '-', then u_expr -> power -> atom(2) ** u_expr -> power -> atom(2)
        # So it's -(2**2) = -4. Correct.
        # And 2**-2 is: power -> atom(2) ** u_expr -> '-' u_expr -> power -> atom(2). So 2**(-2). Correct.
        # And 2**3**2 is: power -> atom(2) ** u_expr -> power -> atom(3) ** u_expr -> power -> atom(2). 
        # Right associative: 2**(3**2) = 2**9 = 512. Correct.
        
        tok = self._current()
        if tok[0] == TOK_OP and tok[1] in ('+', '-'):
            op = self._advance()[1]
            operand = self._factor()
            if op == '+':
                return +operand
            else:
                return -operand
        return self._power()

    def _power(self) -> Number:
        # power := atom ('**' factor)?
        # Right associative: the right side is a factor (which can be unary)
        base = self._atom()
        if self._current()[0] == TOK_OP and self._current()[1] == '**':
            self._advance()
            exponent = self._factor()
            if base == 0 and exponent < 0:
                raise ZeroDivisionError("0.0 cannot be raised to a negative power")
            return base ** exponent
        return base

    def _atom(self) -> Number:
        # atom := NUM | '(' expr ')'
        tok = self._current()
        if tok[0] == TOK_NUM:
            self._advance()
            return tok[1]
        if tok[0] == TOK_LPAREN:
            self._advance()
            result = self._expr()
            self._expect(TOK_RPAREN)
            return result
        raise ValueError(f"Unexpected token {tok[0]} at position {tok[2]}")


def evaluate(expr: str) -> int | float:
    if not expr or not expr.strip():
        raise ValueError("Empty expression")
    tokens = _tokenize(expr)
    parser = _Parser(tokens)
    return parser.parse()
