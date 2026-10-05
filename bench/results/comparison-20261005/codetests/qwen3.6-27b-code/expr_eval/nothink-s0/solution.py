def evaluate(expr: str) -> int | float:
    """
    Evaluate an arithmetic expression string according to Python's arithmetic semantics.
    
    Supported:
    - Integer and decimal literals (no exponent notation, no underscores, no hex)
    - Binary operators: + - * / // % **
    - Unary operators: + - (stackable)
    - Parentheses for grouping
    - Whitespace is ignored
    
    Raises ValueError for malformed input, ZeroDivisionError for division by zero.
    """
    if not expr or not expr.strip():
        raise ValueError("Empty expression")
    
    # Tokenize
    tokens = tokenize(expr)
    
    if not tokens:
        raise ValueError("Empty expression")
    
    # Parse and evaluate
    parser = Parser(tokens)
    result = parser.parse_expression()
    
    # Check if all tokens were consumed
    if parser.pos < len(parser.tokens):
        raise ValueError(f"Unexpected token at position {parser.pos}: {parser.tokens[parser.pos]}")
    
    return result


class Token:
    def __init__(self, type_, value):
        self.type = type_  # 'NUMBER', 'PLUS', 'MINUS', 'STAR', 'SLASH', 'PERCENT', 'DOUBLESTAR', 'LPAREN', 'RPAREN'
        self.value = value
    
    def __repr__(self):
        return f"Token({self.type}, {self.value!r})"


def tokenize(expr: str) -> list:
    """
    Tokenize the expression string into a list of Token objects.
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
        
        # Numbers
        if c.isdigit() or c == '.':
            # Parse number
            start = i
            has_dot = False
            
            if c == '.':
                has_dot = True
                i += 1
                # Must be followed by a digit
                if i >= n or not expr[i].isdigit():
                    raise ValueError(f"Malformed number at position {start}")
            else:
                while i < n and expr[i].isdigit():
                    i += 1
            
            if i < n and expr[i] == '.':
                if has_dot:
                    raise ValueError(f"Malformed number at position {start}")
                has_dot = True
                i += 1
                # Must be followed by a digit
                if i >= n or not expr[i].isdigit():
                    raise ValueError(f"Malformed number at position {start}")
                while i < n and expr[i].isdigit():
                    i += 1
            
            num_str = expr[start:i]
            
            # Validate: no lone dot, must have at least one digit
            if num_str == '.':
                raise ValueError(f"Malformed number at position {start}")
            
            if has_dot:
                value = float(num_str)
            else:
                value = int(num_str)
            
            tokens.append(Token('NUMBER', value))
            continue
        
        # Operators and parentheses
        if c == '+':
            tokens.append(Token('PLUS', '+'))
            i += 1
        elif c == '-':
            tokens.append(Token('MINUS', '-'))
            i += 1
        elif c == '*':
            if i + 1 < n and expr[i + 1] == '*':
                tokens.append(Token('DOUBLESTAR', '**'))
                i += 2
            else:
                tokens.append(Token('STAR', '*'))
                i += 1
        elif c == '/':
            if i + 1 < n and expr[i + 1] == '/':
                tokens.append(Token('DOUBLESLASH', '//'))
                i += 2
            else:
                tokens.append(Token('SLASH', '/'))
                i += 1
        elif c == '%':
            tokens.append(Token('PERCENT', '%'))
            i += 1
        elif c == '(':
            tokens.append(Token('LPAREN', '('))
            i += 1
        elif c == ')':
            tokens.append(Token('RPAREN', ')'))
            i += 1
        else:
            raise ValueError(f"Invalid character '{c}' at position {i}")
    
    return tokens


class Parser:
    def __init__(self, tokens: list):
        self.tokens = tokens
        self.pos = 0
    
    def peek(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None
    
    def consume(self, expected_type=None):
        token = self.peek()
        if token is None:
            raise ValueError("Unexpected end of expression")
        if expected_type and token.type != expected_type:
            raise ValueError(f"Expected {expected_type}, got {token.type}")
        self.pos += 1
        return token
    
    def parse_expression(self):
        """
        Parse addition and subtraction (lowest precedence).
        """
        return self.parse_additive()
    
    def parse_additive(self):
        """
        Parse + and - (left-associative).
        """
        left = self.parse_multiplicative()
        
        while self.peek() and self.peek().type in ('PLUS', 'MINUS'):
            op = self.consume()
            right = self.parse_multiplicative()
            if op.type == 'PLUS':
                left = left + right
            else:
                left = left - right
        
        return left
    
    def parse_multiplicative(self):
        """
        Parse *, /, //, % (left-associative).
        """
        left = self.parse_unary()
        
        while self.peek() and self.peek().type in ('STAR', 'SLASH', 'DOUBLESLASH', 'PERCENT'):
            op = self.consume()
            right = self.parse_unary()
            
            if op.type == 'STAR':
                left = left * right
            elif op.type == 'SLASH':
                if right == 0:
                    raise ZeroDivisionError("Division by zero")
                left = left / right
            elif op.type == 'DOUBLESLASH':
                if right == 0:
                    raise ZeroDivisionError("Division by zero")
                left = left // right
            elif op.type == 'PERCENT':
                if right == 0:
                    raise ZeroDivisionError("Division by zero")
                left = left % right
        
        return left
    
    def parse_unary(self):
        """
        Parse unary + and - (right-associative, higher precedence than multiplicative).
        """
        if self.peek() and self.peek().type in ('PLUS', 'MINUS'):
            op = self.consume()
            operand = self.parse_unary()
            if op.type == 'PLUS':
                return +operand
            else:
                return -operand
        
        return self.parse_power()
    
    def parse_power(self):
        """
        Parse ** (right-associative).
        Note: ** binds tighter than unary on the left, but unary on the right is part of the exponent.
        So -2 ** 2 means -(2 ** 2) = -4, and 2 ** -1 means 2 ** (-1) = 0.5.
        """
        base = self.parse_primary()
        
        if self.peek() and self.peek().type == 'DOUBLESTAR':
            self.consume()
            # The exponent includes unary operators
            exponent = self.parse_unary()
            
            # Handle 0 ** negative exponent
            if base == 0 and exponent < 0:
                raise ZeroDivisionError("0 cannot be raised to a negative power")
            
            return base ** exponent
        
        return base
    
    def parse_primary(self):
        """
        Parse primary expressions: numbers and parenthesized expressions.
        """
        token = self.peek()
        
        if token is None:
            raise ValueError("Unexpected end of expression")
        
        if token.type == 'NUMBER':
            self.consume()
            return token.value
        
        if token.type == 'LPAREN':
            self.consume()
            
            # Check for empty parentheses
            if self.peek() and self.peek().type == 'RPAREN':
                raise ValueError("Empty parentheses")
            
            result = self.parse_expression()
            
            if not self.peek() or self.peek().type != 'RPAREN':
                raise ValueError("Unmatched parenthesis")
            
            self.consume()
            return result
        
        # If we get here, it's an unexpected token
        raise ValueError(f"Unexpected token: {token}")
