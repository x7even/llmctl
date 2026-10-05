def evaluate(expr: str) -> int | float:
    """
    Evaluate an arithmetic expression string according to Python's arithmetic semantics.
    
    Supported:
    - Numbers: integers and decimals (no exponent notation, no underscores, no hex)
    - Binary operators: + - * / // % **
    - Unary operators: + - (stackable)
    - Parentheses for grouping
    - Whitespace ignored
    
    Raises ValueError for malformed input, ZeroDivisionError for division by zero.
    """
    if not isinstance(expr, str):
        raise ValueError("Expression must be a string")
    
    # Tokenizer
    tokens = tokenize(expr)
    
    if not tokens:
        raise ValueError("Empty expression")
    
    # Parser using recursive descent
    parser = Parser(tokens)
    result = parser.parse_expression()
    
    # Ensure all tokens were consumed
    if parser.pos < len(parser.tokens):
        raise ValueError(f"Unexpected token at position {parser.pos}: {parser.tokens[parser.pos]}")
    
    return result


def tokenize(expr: str) -> list:
    """
    Tokenize the expression string into a list of tokens.
    Tokens are:
    - ('NUMBER', value) where value is int or float
    - ('OP', operator_string) for binary/unary operators
    - ('LPAREN', '(')
    - ('RPAREN', ')')
    """
    tokens = []
    i = 0
    n = len(expr)
    
    while i < n:
        ch = expr[i]
        
        # Skip whitespace
        if ch in ' \t':
            i += 1
            continue
        
        # Check for parentheses
        if ch == '(':
            tokens.append(('LPAREN', '('))
            i += 1
            continue
        if ch == ')':
            tokens.append(('RPAREN', ')'))
            i += 1
            continue
        
        # Check for operators
        # Multi-char operators: //, **
        if ch == '/' and i + 1 < n and expr[i + 1] == '/':
            tokens.append(('OP', '//'))
            i += 2
            continue
        if ch == '*' and i + 1 < n and expr[i + 1] == '*':
            tokens.append(('OP', '**'))
            i += 2
            continue
        if ch in '+-*/%':
            tokens.append(('OP', ch))
            i += 1
            continue
        
        # Check for numbers (including decimal points)
        if ch.isdigit() or ch == '.':
            # Parse a number
            start = i
            has_dot = False
            has_digit = False
            
            while i < n and (expr[i].isdigit() or expr[i] == '.'):
                if expr[i] == '.':
                    if has_dot:
                        # Double dot like 1..2 or 1.2.3
                        raise ValueError(f"Malformed number at position {start}")
                    has_dot = True
                else:
                    has_digit = True
                i += 1
            
            num_str = expr[start:i]
            
            # Validate the number string
            if not has_digit:
                # Just dots, e.g., "." or ".."
                raise ValueError(f"Malformed number at position {start}")
            
            # Check for leading/trailing dots that might be invalid
            # A lone "." is invalid, but ".5" and "2." are valid
            if num_str == '.':
                raise ValueError(f"Malformed number at position {start}")
            
            # Check for multiple dots (already handled above, but double-check)
            if num_str.count('.') > 1:
                raise ValueError(f"Malformed number at position {start}")
            
            # Parse the number
            if has_dot:
                value = float(num_str)
            else:
                value = int(num_str)
            
            tokens.append(('NUMBER', value))
            continue
        
        # Invalid character
        raise ValueError(f"Invalid character '{ch}' at position {i}")
    
    return tokens


class Parser:
    """
    Recursive descent parser for arithmetic expressions.
    
    Grammar (following Python precedence):
    expression := additive
    additive := multiplicative (('+' | '-') multiplicative)*
    multiplicative := unary (('*' | '/' | '//' | '%') unary)*
    unary := ('+' | '-')* exponentiation
    exponentiation := primary ('**' unary)?  # Right-associative, right operand is unary
    primary := NUMBER | '(' expression ')'
    """
    
    def __init__(self, tokens: list):
        self.tokens = tokens
        self.pos = 0
    
    def peek(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None
    
    def consume(self, expected_type=None, expected_value=None):
        token = self.peek()
        if token is None:
            raise ValueError("Unexpected end of expression")
        if expected_type and token[0] != expected_type:
            raise ValueError(f"Expected {expected_type}, got {token[0]}: {token[1]}")
        if expected_value and token[1] != expected_value:
            raise ValueError(f"Expected {expected_value}, got {token[1]}")
        self.pos += 1
        return token
    
    def parse_expression(self):
        return self.parse_additive()
    
    def parse_additive(self):
        left = self.parse_multiplicative()
        
        while self.peek() and self.peek()[0] == 'OP' and self.peek()[1] in ('+', '-'):
            op = self.consume()[1]
            right = self.parse_multiplicative()
            if op == '+':
                left = left + right
            else:
                left = left - right
        
        return left
    
    def parse_multiplicative(self):
        left = self.parse_unary()
        
        while self.peek() and self.peek()[0] == 'OP' and self.peek()[1] in ('*', '/', '//', '%'):
            op = self.consume()[1]
            right = self.parse_unary()
            if op == '*':
                left = left * right
            elif op == '/':
                if right == 0:
                    raise ZeroDivisionError("division by zero")
                left = left / right
            elif op == '//':
                if right == 0:
                    raise ZeroDivisionError("division by zero")
                # Python's floor division
                left = left // right
            elif op == '%':
                if right == 0:
                    raise ZeroDivisionError("division by zero")
                left = left % right
        
        return left
    
    def parse_unary(self):
        # Handle unary + and -
        # They may be stacked: --3, +-+2, etc.
        sign = 1
        while self.peek() and self.peek()[0] == 'OP' and self.peek()[1] in ('+', '-'):
            op = self.consume()[1]
            if op == '-':
                sign *= -1
            # + does nothing
        
        # If no unary operator was found, or after consuming them, parse exponentiation
        # But we need to be careful: if we consumed unary operators, we apply them to the result
        # of exponentiation. However, the grammar says unary binds tighter than multiplicative
        # but looser than exponentiation on the left.
        
        # Actually, let's re-read the grammar:
        # unary := ('+' | '-')* exponentiation
        # So we consume all unary signs, then parse exponentiation, then apply the sign.
        
        value = self.parse_exponentiation()
        
        # Apply the accumulated sign
        if sign == -1:
            value = -value
        
        return value
    
    def parse_exponentiation(self):
        # exponentiation := primary ('**' unary)?
        # Right-associative: 2 ** 3 ** 2 == 2 ** (3 ** 2)
        # The right operand of ** is a unary expression (so 2 ** -1 is valid)
        
        base = self.parse_primary()
        
        if self.peek() and self.peek()[0] == 'OP' and self.peek()[1] == '**':
            self.consume()
            # Right operand is a unary expression (to handle 2 ** -1)
            exponent = self.parse_unary()
            
            # Handle 0 ** negative exponent
            if base == 0 and exponent < 0:
                raise ZeroDivisionError("0 cannot be raised to a negative power")
            
            result = base ** exponent
            
            # In Python, int ** int with negative exponent gives float
            # int ** int with non-negative exponent gives int
            # float ** anything gives float
            # We let Python's ** handle the type semantics
            
            return result
        else:
            return base
    
    def parse_primary(self):
        token = self.peek()
        
        if token is None:
            raise ValueError("Unexpected end of expression")
        
        if token[0] == 'NUMBER':
            self.consume()
            return token[1]
        
        if token[0] == 'LPAREN':
            self.consume()
            # Check for empty parentheses
            if self.peek() and self.peek()[0] == 'RPAREN':
                raise ValueError("Empty parentheses")
            
            value = self.parse_expression()
            
            if not self.peek() or self.peek()[0] != 'RPAREN':
                raise ValueError("Unmatched parenthesis")
            
            self.consume()
            return value
        
        # If we get here, it's an unexpected token
        raise ValueError(f"Unexpected token: {token}")
