def evaluate(expr: str) -> int | float:
    """
    Evaluate an arithmetic expression string according to Python semantics.
    
    Supported: integers, decimals, +, -, *, /, //, %, **, unary +/-, parentheses.
    Raises ValueError for malformed input, ZeroDivisionError for division by zero.
    """
    if not isinstance(expr, str):
        raise ValueError("Input must be a string")
    
    # Tokenizer
    tokens = _tokenize(expr)
    
    if not tokens:
        raise ValueError("Empty expression")
    
    # Parser using recursive descent
    parser = _Parser(tokens)
    result = parser.parse_expression()
    
    # Check that all tokens were consumed
    if parser.pos < len(tokens):
        raise ValueError(f"Unexpected token at position {parser.pos}: {tokens[parser.pos]}")
    
    return result


def _tokenize(expr: str) -> list:
    """
    Tokenize the expression string into a list of tokens.
    
    Token types:
    - ('NUM', value) where value is int or float
    - ('OP', operator_string)
    - ('LPAREN', '(')
    - ('RPAREN', ')')
    """
    tokens = []
    i = 0
    n = len(expr)
    
    while i < n:
        ch = expr[i]
        
        # Skip whitespace
        if ch in ' \t\n\r':
            i += 1
            continue
        
        # Check for digits or decimal point (number)
        if ch.isdigit() or ch == '.':
            num_str, end_i = _read_number(expr, i)
            # Validate the number
            _validate_number(num_str)
            if '.' in num_str:
                tokens.append(('NUM', float(num_str)))
            else:
                tokens.append(('NUM', int(num_str)))
            i = end_i
            continue
        
        # Check for operators
        if ch in '+-*/%':
            # Check for two-character operators: //
            if ch == '/' and i + 1 < n and expr[i + 1] == '/':
                tokens.append(('OP', '//'))
                i += 2
                continue
            elif ch == '*' and i + 1 < n and expr[i + 1] == '*':
                tokens.append(('OP', '**'))
                i += 2
                continue
            else:
                tokens.append(('OP', ch))
                i += 1
                continue
        
        # Parentheses
        if ch == '(':
            tokens.append(('LPAREN', '('))
            i += 1
            continue
        elif ch == ')':
            tokens.append(('RPAREN', ')'))
            i += 1
            continue
        
        # Invalid character
        raise ValueError(f"Invalid character: '{ch}' at position {i}")
    
    return tokens


def _read_number(expr: str, start: int) -> tuple:
    """
    Read a number starting at position start.
    Returns (number_string, end_position).
    """
    i = start
    n = len(expr)
    has_dot = False
    
    while i < n:
        ch = expr[i]
        if ch.isdigit():
            i += 1
        elif ch == '.':
            if has_dot:
                break  # Second dot, stop reading
            has_dot = True
            i += 1
        else:
            break
    
    num_str = expr[start:i]
    return num_str, i


def _validate_number(num_str: str) -> None:
    """
    Validate that the number string is well-formed.
    """
    if not num_str:
        raise ValueError("Empty number")
    
    # Check for lone dot
    if num_str == '.':
        raise ValueError("Lone '.' is not a valid number")
    
    # Check for multiple dots
    if num_str.count('.') > 1:
        raise ValueError(f"Malformed number: {num_str}")
    
    # Check that it's not just a dot at the end with no digits before
    # Actually, '.5' and '2.' are valid, but we need at least one digit
    if num_str.startswith('.') and len(num_str) == 1:
        raise ValueError("Lone '.' is not a valid number")
    
    # Check that all characters are digits or at most one dot
    for ch in num_str:
        if not (ch.isdigit() or ch == '.'):
            raise ValueError(f"Invalid character in number: '{ch}'")


class _Parser:
    """
    Recursive descent parser for arithmetic expressions.
    
    Grammar (highest to lowest precedence):
    expression   : additive
    additive     : multiplicative (('+' | '-') multiplicative)*
    multiplicative : unary (('*' | '/' | '//' | '%') unary)*
    unary        : ('+' | '-')* exponent
    exponent     : primary ('**' unary)?  # Note: right operand of ** can have unary
    primary      : NUMBER | '(' expression ')'
    
    Note: ** is right-associative, so 2**3**2 = 2**(3**2) = 512.
    Also, -2**2 = -(2**2) = -4, so unary minus has lower precedence than **.
    """
    
    def __init__(self, tokens: list):
        self.tokens = tokens
        self.pos = 0
    
    def current_token(self) -> tuple:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None
    
    def eat(self, expected_type: str = None, expected_value: str = None) -> tuple:
        token = self.current_token()
        if token is None:
            raise ValueError("Unexpected end of expression")
        
        if expected_type and token[0] != expected_type:
            raise ValueError(f"Expected {expected_type}, got {token}")
        
        if expected_value and token[1] != expected_value:
            raise ValueError(f"Expected '{expected_value}', got '{token[1]}'")
        
        self.pos += 1
        return token
    
    def parse_expression(self) -> float | int:
        """Parse the full expression."""
        return self.parse_additive()
    
    def parse_additive(self) -> float | int:
        """Parse additive operators: + -"""
        left = self.parse_multiplicative()
        
        while self.current_token() and self.current_token()[0] == 'OP' and self.current_token()[1] in ('+', '-'):
            op = self.eat('OP')[1]
            right = self.parse_multiplicative()
            if op == '+':
                left = left + right
            else:
                left = left - right
        
        return left
    
    def parse_multiplicative(self) -> float | int:
        """Parse multiplicative operators: * / // %"""
        left = self.parse_unary()
        
        while self.current_token() and self.current_token()[0] == 'OP' and self.current_token()[1] in ('*', '/', '//', '%'):
            op = self.eat('OP')[1]
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
                left = left // right
            elif op == '%':
                if right == 0:
                    raise ZeroDivisionError("division by zero")
                left = left % right
        
        return left
    
    def parse_unary(self) -> float | int:
        """Parse unary operators: + -"""
        # Check for unary + or -
        while self.current_token() and self.current_token()[0] == 'OP' and self.current_token()[1] in ('+', '-'):
            op = self.eat('OP')[1]
            # Parse the exponent (which may itself have unary operators)
            operand = self.parse_exponent()
            if op == '-':
                operand = -operand
            # + is no-op
        else:
            # No unary operator, parse exponent directly
            operand = self.parse_exponent()
        
        return operand
    
    def parse_exponent(self) -> float | int:
        """Parse exponentiation: ** (right-associative)"""
        base = self.parse_primary()
        
        # Check for **
        if self.current_token() and self.current_token()[0] == 'OP' and self.current_token()[1] == '**':
            self.eat('OP', '**')
            # Right operand of ** can have unary operators, so parse unary
            exponent = self.parse_unary()
            
            # Handle 0 ** negative exponent
            if base == 0 and exponent < 0:
                raise ZeroDivisionError("0 cannot be raised to a negative power")
            
            result = base ** exponent
            
            # If base is int and exponent is int and exponent >= 0, result should be int
            # But Python's ** returns int for int**int with non-negative exponent
            # However, if the result is a float (e.g., due to intermediate calculation), we keep it
            # Actually, let's follow Python's behavior exactly:
            # int ** int with non-negative exponent -> int
            # Otherwise -> float
            if isinstance(base, int) and isinstance(exponent, int) and exponent >= 0:
                result = int(result)
            
            return result
        
        return base
    
    def parse_primary(self) -> float | int:
        """Parse primary expressions: numbers and parenthesized expressions."""
        token = self.current_token()
        
        if token is None:
            raise ValueError("Unexpected end of expression")
        
        # Number
        if token[0] == 'NUM':
            self.eat('NUM')
            return token[1]
        
        # Parenthesized expression
        if token[0] == 'LPAREN':
            self.eat('LPAREN', '(')
            
            # Check for empty parentheses
            if self.current_token() and self.current_token()[0] == 'RPAREN':
                raise ValueError("Empty parentheses ()")
            
            result = self.parse_expression()
            
            if not self.current_token() or self.current_token()[0] != 'RPAREN':
                raise ValueError("Missing closing parenthesis")
            
            self.eat('RPAREN', ')')
            return result
        
        # If we get here, we have an unexpected token
        if token[0] == 'OP':
            raise ValueError(f"Unexpected operator '{token[1]}'")
        elif token[0] == 'RPAREN':
            raise ValueError("Unexpected ')'")
        else:
            raise ValueError(f"Unexpected token: {token}")


# Test cases
if __name__ == '__main__':
    # Basic tests
    assert evaluate('3') == 3
    assert evaluate('3.5') == 3.5
    assert evaluate('.5') == 0.5
    assert evaluate('2.') == 2.0
    
    # Binary operators
    assert evaluate('2 + 3') == 5
    assert evaluate('2 - 3') == -1
    assert evaluate('2 * 3') == 6
    assert evaluate('6 / 2') == 3.0
    assert evaluate('7 // 2') == 3
    assert evaluate('7 % 2') == 1
    assert evaluate('2 ** 3') == 8
    
    # Precedence
    assert evaluate('2 + 3 * 4') == 14
    assert evaluate('(2 + 3) * 4') == 20
    
    # Right-associative **
    assert evaluate('2 ** 3 ** 2') == 512
    
    # Unary operators
    assert evaluate('-2') == -2
    assert evaluate('+2') == 2
    assert evaluate('--2') == 2
    assert evaluate('+-2') == -2
    assert evaluate('-+2') == -2
    assert evaluate('--+2') == 2
    
    # Unary with **
    assert evaluate('-2 ** 2') == -4
    assert evaluate('2 ** -1') == 0.5
    assert evaluate('2 ** -2 ** 2') == 0.0625
    
    # Division by zero
    try:
        evaluate('1 / 0')
        assert False, "Should have raised ZeroDivisionError"
    except ZeroDivisionError:
        pass
    
    try:
        evaluate('1 // 0')
        assert False, "Should have raised ZeroDivisionError"
    except ZeroDivisionError:
        pass
    
    try:
        evaluate('1 % 0')
        assert False, "Should have raised ZeroDivisionError"
    except ZeroDivisionError:
        pass
    
    try:
        evaluate('0 ** -1')
        assert False, "Should have raised ZeroDivisionError"
    except ZeroDivisionError:
        pass
    
    # ValueError tests
    try:
        evaluate('')
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    
    try:
        evaluate('   ')
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    
    try:
        evaluate('()')
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    
    try:
        evaluate('1 +')
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    
    try:
        evaluate('* 2')
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    
    try:
        evaluate('1 2')
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    
    try:
        evaluate('1..2')
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    
    try:
        evaluate('1.2.3')
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    
    try:
        evaluate('.')
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    
    try:
        evaluate('1e3')
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    
    # Floor division and modulo with negatives
    assert evaluate('-7 // 2') == -4
    assert evaluate('7 // -2') == -4
    assert evaluate('-7 % 2') == 1
    assert evaluate('7 % -2') == -1
    
    # Float operations
    assert evaluate('1.5 * 2') == 3.0
    assert evaluate('3 / 2') == 1.5
    
    print("All tests passed!")
