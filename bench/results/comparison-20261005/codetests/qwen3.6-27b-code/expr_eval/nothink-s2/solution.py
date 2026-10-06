def evaluate(expr: str) -> int | float:
    """
    Evaluate an arithmetic expression string and return the result.
    
    Supports: integers, decimals, +, -, *, /, //, %, **, unary +/-, parentheses.
    Follows Python's operator precedence and associativity rules.
    """
    tokens = tokenize(expr)
    if not tokens:
        raise ValueError("Empty expression")
    
    parser = Parser(tokens)
    result = parser.parse_expression()
    
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
        c = expr[i]
        
        # Skip whitespace
        if c in ' \t':
            i += 1
            continue
        
        # Check for number
        if c.isdigit() or c == '.':
            start = i
            has_dot = False
            
            while i < n and (expr[i].isdigit() or expr[i] == '.'):
                if expr[i] == '.':
                    if has_dot:
                        raise ValueError(f"Malformed number at position {start}: multiple dots")
                    has_dot = True
                i += 1
            
            num_str = expr[start:i]
            
            # Validate number format
            if num_str == '.':
                raise ValueError(f"Malformed number: lone dot at position {start}")
            if num_str.startswith('.') and len(num_str) == 1:
                raise ValueError(f"Malformed number: lone dot at position {start}")
            if num_str.endswith('.') and len(num_str) == 1:
                raise ValueError(f"Malformed number: lone dot at position {start}")
            
            # Check for adjacent numbers (e.g., "1 2" would be caught here if no whitespace)
            # But we already skip whitespace, so this shouldn't happen
            
            if has_dot:
                value = float(num_str)
            else:
                value = int(num_str)
            
            tokens.append(('NUMBER', value))
            continue
        
        # Check for operators
        if c in '+-*/%':
            # Check for multi-char operators
            if c == '/' and i + 1 < n and expr[i + 1] == '/':
                tokens.append(('OP', '//'))
                i += 2
                continue
            if c == '*' and i + 1 < n and expr[i + 1] == '*':
                tokens.append(('OP', '**'))
                i += 2
                continue
            tokens.append(('OP', c))
            i += 1
            continue
        
        if c == '(':
            tokens.append(('LPAREN', '('))
            i += 1
            continue
        
        if c == ')':
            tokens.append(('RPAREN', ')'))
            i += 1
            continue
        
        # Invalid character
        raise ValueError(f"Invalid character '{c}' at position {i}")
    
    return tokens


class Parser:
    def __init__(self, tokens):
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
            raise ValueError(f"Expected {expected_type}, got {token}")
        if expected_value is not None and token[1] != expected_value:
            raise ValueError(f"Expected {expected_value}, got {token[1]}")
        
        self.pos += 1
        return token
    
    def parse_expression(self):
        """Parse addition and subtraction (lowest precedence)"""
        left = self.parse_term()
        
        while True:
            token = self.peek()
            if token and token[0] == 'OP' and token[1] in ('+', '-'):
                self.consume()
                right = self.parse_term()
                if token[1] == '+':
                    left = left + right
                else:
                    left = left - right
            else:
                break
        
        return left
    
    def parse_term(self):
        """Parse multiplication, division, floor division, and modulo"""
        left = self.parse_unary()
        
        while True:
            token = self.peek()
            if token and token[0] == 'OP' and token[1] in ('*', '/', '//', '%'):
                self.consume()
                right = self.parse_unary()
                
                if token[1] == '*':
                    left = left * right
                elif token[1] == '/':
                    if right == 0:
                        raise ZeroDivisionError("division by zero")
                    left = left / right
                elif token[1] == '//':
                    if right == 0:
                        raise ZeroDivisionError("division by zero")
                    left = left // right
                elif token[1] == '%':
                    if right == 0:
                        raise ZeroDivisionError("division by zero")
                    left = left % right
            else:
                break
        
        return left
    
    def parse_unary(self):
        """Parse unary + and -"""
        token = self.peek()
        if token and token[0] == 'OP' and token[1] in ('+', '-'):
            self.consume()
            operand = self.parse_unary()
            if token[1] == '-':
                return -operand
            else:
                return +operand
        
        return self.parse_power()
    
    def parse_power(self):
        """Parse exponentiation (right-associative)"""
        base = self.parse_primary()
        
        token = self.peek()
        if token and token[0] == 'OP' and token[1] == '**':
            self.consume()
            # For right-associativity, we need to handle the right operand carefully
            # The right operand can be a unary expression (e.g., 2 ** -1)
            exponent = self.parse_unary()
            
            # Handle special cases for **
            if base == 0 and exponent < 0:
                raise ZeroDivisionError("0 cannot be raised to a negative power")
            
            result = base ** exponent
            return result
        
        return base
    
    def parse_primary(self):
        """Parse numbers and parenthesized expressions"""
        token = self.peek()
        
        if token is None:
            raise ValueError("Unexpected end of expression")
        
        if token[0] == 'NUMBER':
            self.consume()
            return token[1]
        
        if token[0] == 'LPAREN':
            self.consume()
            
            # Check for empty parentheses
            next_token = self.peek()
            if next_token and next_token[0] == 'RPAREN':
                raise ValueError("Empty parentheses")
            
            result = self.parse_expression()
            
            self.consume('RPAREN', ')')
            return result
        
        if token[0] == 'OP':
            raise ValueError(f"Unexpected operator '{token[1]}'")
        
        if token[0] == 'RPAREN':
            raise ValueError("Unexpected ')'")
        
        raise ValueError(f"Unexpected token: {token}")
