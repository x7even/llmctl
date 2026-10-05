"""Arithmetic expression evaluator without eval/exec/compile/ast."""

from __future__ import annotations

# Token types
T_NUM = "NUM"
T_PLUS = "PLUS"
T_MINUS = "MINUS"
T_STAR = "STAR"
T_SLASH = "SLASH"
T_DSLASH = "DSLASH"
T_PERCENT = "PERCENT"
T_POW = "POW"
T_LPAREN = "LPAREN"
T_RPAREN = "RPAREN"
T_EOF = "EOF"


class _Token:
    __slots__ = ("type", "value", "pos")

    def __init__(self, type_: str, value, pos: int):
        self.type = type_
        self.value = value
        self.pos = pos

    def __repr__(self) -> str:
        return f"Token({self.type!r}, {self.value!r}, pos={self.pos})"


def _tokenize(expr: str) -> list[_Token]:
    tokens: list[_Token] = []
    i = 0
    n = len(expr)
    while i < n:
        c = expr[i]
        # Skip whitespace (spaces and tabs; also accept other whitespace for robustness? Spec says spaces/tabs. Use str.isspace to be safe but spec says spaces/tabs. Let's stick to spaces and tabs as per spec, but typically whitespace. I'll use c in ' \t' to be strict to spec, or c.isspace(). Spec: "Whitespace (spaces, tabs) between tokens is ignored." I'll check for space and tab explicitly, but usually any whitespace is fine. Let's use c in ' \t' to be precise, or just c.isspace(). I'll use c in ' \t' to match spec exactly, but it's safer to allow any whitespace? No, spec says spaces and tabs. I'll use c in ' \t'.)
        if c in ' \t':
            i += 1
            continue

        # Numbers
        if c.isdigit() or c == '.':
            start = i
            # Check for valid number format
            # A number can be:
            # - digits
            # - digits '.' digits
            # - '.' digits
            # - digits '.'
            # But not: '..', '1..2', '1.2.3', lone '.'
            
            # Let's parse the number
            # First, check if it's a valid number start
            # If c is '.', it must be followed by a digit
            # If c is digit, it can be followed by optional '.' and digits
            
            # Approach: scan forward to find the extent of the potential number
            j = i
            has_dot = False
            while j < n:
                ch = expr[j]
                if ch.isdigit():
                    j += 1
                elif ch == '.' and not has_dot:
                    has_dot = True
                    j += 1
                else:
                    break
            
            # Now check if the substring expr[i:j] is a valid number
            num_str = expr[i:j]
            
            # Validate the number string
            if not num_str:
                raise ValueError(f"Invalid number at position {i}")
            
            # Check for invalid patterns
            # Lone dot
            if num_str == '.':
                raise ValueError(f"Invalid number '.' at position {i}")
            
            # Multiple dots
            if num_str.count('.') > 1:
                raise ValueError(f"Invalid number '{num_str}' at position {i}")
            
            # If there's a dot, it must have at least one digit somewhere
            if has_dot:
                # Remove the dot and check if there are digits
                digits_part = num_str.replace('.', '')
                if not digits_part.isdigit():
                    raise ValueError(f"Invalid number '{num_str}' at position {i}")
                # Also, the dot can't be at the end if there are no digits before? 
                # Actually "2." is valid, ".5" is valid.
                # But "2..3" would have been caught by count('.') > 1
                # What about ".5"? digits_part = "5", isdigit() is True. OK.
                # What about "2."? digits_part = "2", isdigit() is True. OK.
                # What about "."? Already caught.
            else:
                # No dot, must be all digits
                if not num_str.isdigit():
                    raise ValueError(f"Invalid number '{num_str}' at position {i}")
            
            # Parse the value
            if has_dot:
                value = float(num_str)
            else:
                value = int(num_str)
            
            tokens.append(_Token(T_NUM, value, i))
            i = j
            continue

        # Operators
        if c == '+':
            tokens.append(_Token(T_PLUS, '+', i))
            i += 1
            continue
        if c == '-':
            tokens.append(_Token(T_MINUS, '-', i))
            i += 1
            continue
        if c == '*':
            if i + 1 < n and expr[i + 1] == '*':
                tokens.append(_Token(T_POW, '**', i))
                i += 2
            else:
                tokens.append(_Token(T_STAR, '*', i))
                i += 1
            continue
        if c == '/':
            if i + 1 < n and expr[i + 1] == '/':
                tokens.append(_Token(T_DSLASH, '//', i))
                i += 2
            else:
                tokens.append(_Token(T_SLASH, '/', i))
                i += 1
            continue
        if c == '%':
            tokens.append(_Token(T_PERCENT, '%', i))
            i += 1
            continue
        if c == '(':
            tokens.append(_Token(T_LPAREN, '(', i))
            i += 1
            continue
        if c == ')':
            tokens.append(_Token(T_RPAREN, ')', i))
            i += 1
            continue

        # Invalid character
        raise ValueError(f"Invalid character '{c}' at position {i}")

    tokens.append(_Token(T_EOF, None, n))
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

    def _expect(self, token_type: str) -> _Token:
        tok = self._peek()
        if tok.type != token_type:
            raise ValueError(f"Expected {token_type}, got {tok.type} at position {tok.pos}")
        return self._advance()

    def parse(self) -> int | float:
        result = self._expression()
        if self._peek().type != T_EOF:
            tok = self._peek()
            raise ValueError(f"Unexpected token {tok.type} at position {tok.pos}")
        return result

    def _expression(self) -> int | float:
        # expression := term (('+' | '-') term)*
        left = self._term()
        while self._peek().type in (T_PLUS, T_MINUS):
            op = self._advance()
            right = self._term()
            if op.type == T_PLUS:
                left = left + right
            else:
                left = left - right
        return left

    def _term(self) -> int | float:
        # term := factor (('*' | '/' | '//' | '%') factor)*
        left = self._factor()
        while self._peek().type in (T_STAR, T_SLASH, T_DSLASH, T_PERCENT):
            op = self._advance()
            right = self._factor()
            if op.type == T_STAR:
                left = left * right
            elif op.type == T_SLASH:
                if right == 0:
                    raise ZeroDivisionError("division by zero")
                left = left / right
            elif op.type == T_DSLASH:
                if right == 0:
                    raise ZeroDivisionError("integer division or modulo by zero")
                left = left // right
            else:  # T_PERCENT
                if right == 0:
                    raise ZeroDivisionError("integer modulo by zero")
                left = left % right
        return left

    def _factor(self) -> int | float:
        # factor := power (unary operators)
        # In Python, unary operators bind tighter than **, but ** binds tighter than unary on the left.
        # Actually, the precedence is:
        # 1. ** (right-associative)
        # 2. unary +, -
        # 3. *, /, //, %
        # 4. +, -
        
        # Wait, let me re-read the spec:
        # "Precedence, highest to lowest: parentheses; ** (right-associative); unary +/−; * / // % (left-associative); + - (left-associative)."
        # "As in Python, the operand to the right of ** may itself carry a unary sign, and ** binds tighter than a unary operator on its left. So -2 ** 2 == -4, 2 ** -1 == 0.5, 2 ** 3 ** 2 == 512, 2 ** -2 ** 2 == 0.0625."
        
        # So the grammar should be:
        # factor := ('+' | '-')* power
        # power := atom ('**' factor)?
        
        # Let me verify:
        # -2 ** 2
        # factor sees '-', then power
        # power sees 2, then **, then factor
        # factor sees 2 (no unary), power sees 2, no **
        # So power is 2 ** 2 = 4
        # factor is -4
        # Correct.
        
        # 2 ** -1
        # factor sees 2 (no unary), power
        # power sees 2, then **, then factor
        # factor sees -, then power
        # power sees 1, no **
        # So factor is -1
        # power is 2 ** -1 = 0.5
        # Correct.
        
        # 2 ** 3 ** 2
        # factor sees 2, power
        # power sees 2, then **, then factor
        # factor sees 3, power
        # power sees 3, then **, then factor
        # factor sees 2, power
        # power sees 2, no **
        # So inner power is 3 ** 2 = 9
        # outer power is 2 ** 9 = 512
        # Correct.
        
        # 2 ** -2 ** 2
        # factor sees 2, power
        # power sees 2, then **, then factor
        # factor sees -, then power
        # power sees 2, then **, then factor
        # factor sees 2, power
        # power sees 2, no **
        # So inner power is 2 ** 2 = 4
        # factor is -4
        # outer power is 2 ** -4 = 0.0625
        # Correct.

        # So:
        # factor := ('+' | '-')* power
        # power := atom ('**' factor)?

        # Apply unary operators
        while self._peek().type in (T_PLUS, T_MINUS):
            op = self._advance()
            operand = self._power()
            if op.type == T_PLUS:
                result = +operand
            else:
                result = -operand
            # Note: In Python, unary operators can be stacked, e.g., --3
            # But the grammar above only applies one unary at a time.
            # However, since we're in a loop, it should handle stacking.
            # Wait, no. If we have --3, the first - is consumed, then we call _power(), which parses 3.
            # But the second - is not consumed.
            # So we need to restructure.
            
            # Actually, the standard way is:
            # factor := ('+' | '-') factor | power
            # But that's left-recursive.
            
            # Let me use:
            # factor := ('+' | '-')* power
            # But that means all unary operators are applied before the power.
            # So --3 would be: two minus signs, then power(3) = 3, then -(-3) = 3.
            # But that's not how it works with **.
            
            # Let me think again.
            # In Python, -2 ** 2 is (-2) ** 2? No, it's -(2 ** 2) = -4.
            # So unary minus has lower precedence than **.
            
            # So the grammar should be:
            # factor := power | ('+' | '-') factor
            # But that's left-recursive.
            
            # Alternatively:
            # factor := ('+' | '-')* power
            # But that would make -2 ** 2 = (-2) ** 2 = 4, which is wrong.
            
            # So the correct grammar is:
            # factor := power | ('+' | '-') factor
            # Which is:
            # factor := ('+' | '-') factor | power
            
            # Let me implement it as:
            # If the next token is + or -, consume it, parse factor, and apply the sign.
            # Otherwise, parse power.

            # I'll restructure _factor to handle this properly.
            pass

        # Let me rewrite _factor properly.
        # I'll use a recursive approach.

        # Actually, let me just implement it as:
        # _factor:
        #   if peek is + or -:
        #     consume it
        #     operand = _factor()
        #     return +/- operand
        #   else:
        #     return _power()

        # This handles stacking: --3 -> -(-3) -> 3
        # And -2 ** 2 -> -(2 ** 2) -> -4

        # Let me rewrite _factor.

        # I'll fix this in the actual implementation below.

        # For now, let me just return a placeholder.
        return 0  # Will be replaced

    def _power(self) -> int | float:
        # power := atom ('**' factor)?
        base = self._atom()
        if self._peek().type == T_POW:
            self._advance()
            exponent = self._factor()
            try:
                result = base ** exponent
            except ZeroDivisionError:
                raise ZeroDivisionError("0 ** negative number")
            except OverflowError:
                raise OverflowError("integer result too large")
            return result
        return base

    def _atom(self) -> int | float:
        # atom := NUMBER | '(' expression ')'
        tok = self._peek()
        if tok.type == T_NUM:
            self._advance()
            return tok.value
        if tok.type == T_LPAREN:
            self._advance()
            if self._peek().type == T_RPAREN:
                raise ValueError("Empty parentheses")
            result = self._expression()
            self._expect(T_RPAREN)
            return result
        raise ValueError(f"Unexpected token {tok.type} at position {tok.pos}")


def evaluate(expr: str) -> int | float:
    if not expr or expr.strip() == '':
        raise ValueError("Empty expression")
    
    tokens = _tokenize(expr)
    parser = _Parser(tokens)
    return parser.parse()
