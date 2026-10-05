"""Arithmetic expression evaluator without eval/exec/compile/ast."""

from __future__ import annotations


class _Token:
    __slots__ = ("kind", "value")

    def __init__(self, kind: str, value: object) -> None:
        self.kind = kind
        self.value = value


def _tokenize(expr: str) -> list[_Token]:
    tokens: list[_Token] = []
    i = 0
    n = len(expr)
    while i < n:
        ch = expr[i]
        if ch in " \t":
            i += 1
            continue
        if ch.isdigit() or ch == ".":
            # Number literal: integer or decimal
            j = i
            seen_dot = False
            if ch == ".":
                seen_dot = True
                j += 1
                if j >= n or not expr[j].isdigit():
                    raise ValueError("Malformed number: lone '.'")
            else:
                while j < n and expr[j].isdigit():
                    j += 1
                if j < n and expr[j] == ".":
                    seen_dot = True
                    j += 1
                    if j >= n or not expr[j].isdigit():
                        # e.g. "2." is valid, but "2..3" - check next
                        if j < n and expr[j] == ".":
                            raise ValueError("Malformed number")
                    # after dot, must have digits
                    if j < n:
                        if not expr[j].isdigit():
                            raise ValueError("Malformed number")
                        while j < n and expr[j].isdigit():
                            j += 1
                    else:
                        # "2." is valid
                        pass
                elif j < n and expr[j].isdigit():
                    # already handled
                    pass
            # Check for malformed like 1.2.3
            # We've consumed up to j. Verify no extra dots.
            # Actually let's re-validate the substring
            num_str = expr[i:j]
            # Count dots
            dot_count = num_str.count(".")
            if dot_count > 1:
                raise ValueError("Malformed number")
            # Ensure valid format
            if num_str == ".":
                raise ValueError("Malformed number")
            if num_str.endswith(".") and len(num_str) == 1:
                raise ValueError("Malformed number")
            # Validate: digits [. digits]
            if seen_dot:
                # Must have at least one digit somewhere
                if not any(c.isdigit() for c in num_str):
                    raise ValueError("Malformed number")
                # Check structure
                parts = num_str.split(".")
                if len(parts) != 2:
                    raise ValueError("Malformed number")
                if parts[0] and not parts[0].isdigit():
                    raise ValueError("Malformed number")
                if parts[1] and not parts[1].isdigit():
                    raise ValueError("Malformed number")
                # Both empty is invalid (just ".")
                if not parts[0] and not parts[1]:
                    raise ValueError("Malformed number")
            else:
                if not num_str.isdigit():
                    raise ValueError("Malformed number")
            if seen_dot:
                tokens.append(_Token("NUM", float(num_str)))
            else:
                tokens.append(_Token("NUM", int(num_str)))
            i = j
            continue
        if ch in "+-*/%":
            if ch == "*":
                if i + 1 < n and expr[i + 1] == "*":
                    tokens.append(_Token("OP", "**"))
                    i += 2
                    continue
                else:
                    tokens.append(_Token("OP", "*"))
                    i += 1
                    continue
            elif ch == "/":
                if i + 1 < n and expr[i + 1] == "/":
                    tokens.append(_Token("OP", "//"))
                    i += 2
                    continue
                else:
                    tokens.append(_Token("OP", "/"))
                    i += 1
                    continue
            else:
                tokens.append(_Token("OP", ch))
                i += 1
                continue
        if ch == "(":
            tokens.append(_Token("LPAREN", "("))
            i += 1
            continue
        if ch == ")":
            tokens.append(_Token("RPAREN", ")"))
            i += 1
            continue
        raise ValueError(f"Invalid character: {ch!r}")
    return tokens


def _parse(tokens: list[_Token]) -> object:
    if not tokens:
        raise ValueError("Empty expression")
    pos = [0]  # mutable index

    def peek() -> _Token | None:
        if pos[0] < len(tokens):
            return tokens[pos[0]]
        return None

    def advance() -> _Token:
        tok = tokens[pos[0]]
        pos[0] += 1
        return tok

    def parse_expression() -> object:
        # Lowest precedence: + and - (left-associative)
        left = parse_term()
        while True:
            tok = peek()
            if tok is None:
                break
            if tok.kind == "OP" and tok.value in ("+", "-"):
                op = advance().value
                right = parse_term()
                if op == "+":
                    left = left + right
                else:
                    left = left - right
            else:
                break
        return left

    def parse_term() -> object:
        # * / // % (left-associative)
        left = parse_unary()
        while True:
            tok = peek()
            if tok is None:
                break
            if tok.kind == "OP" and tok.value in ("*", "/", "//", "%"):
                op = advance().value
                right = parse_unary()
                if op == "*":
                    left = left * right
                elif op == "/":
                    if right == 0:
                        raise ZeroDivisionError("division by zero")
                    left = left / right
                elif op == "//":
                    if right == 0:
                        raise ZeroDivisionError("integer division or modulo by zero")
                    left = left // right
                elif op == "%":
                    if right == 0:
                        raise ZeroDivisionError("integer modulo by zero")
                    left = left % right
            else:
                break
        return left

    def parse_unary() -> object:
        # Unary + and -
        tok = peek()
        if tok is not None and tok.kind == "OP" and tok.value in ("+", "-"):
            op = advance().value
            operand = parse_unary()
            if op == "+":
                return +operand
            else:
                return -operand
        return parse_power()

    def parse_power() -> object:
        # ** is right-associative
        # The base is a unary expression (so -2**2 works: - applies to result of 2**2)
        # But the exponent can be a unary expression
        base = parse_primary()
        tok = peek()
        if tok is not None and tok.kind == "OP" and tok.value == "**":
            advance()
            # Exponent is a unary expression (to allow 2 ** -3)
            exponent = parse_unary()
            try:
                result = base ** exponent
            except ZeroDivisionError:
                raise
            except OverflowError:
                raise
            return result
        return base

    def parse_primary() -> object:
        tok = peek()
        if tok is None:
            raise ValueError("Unexpected end of expression")
        if tok.kind == "NUM":
            advance()
            return tok.value
        if tok.kind == "LPAREN":
            advance()
            # Check for empty parentheses
            next_tok = peek()
            if next_tok is not None and next_tok.kind == "RPAREN":
                raise ValueError("Empty parentheses")
            val = parse_expression()
            next_tok = peek()
            if next_tok is None or next_tok.kind != "RPAREN":
                raise ValueError("Missing closing parenthesis")
            advance()
            return val
        raise ValueError(f"Unexpected token: {tok.value!r}")

    result = parse_expression()
    if pos[0] != len(tokens):
        raise ValueError(f"Unexpected token after expression: {tokens[pos[0]].value!r}")
    return result


def evaluate(expr: str) -> int | float:
    if not expr or not expr.strip():
        raise ValueError("Empty expression")
    tokens = _tokenize(expr)
    if not tokens:
        raise ValueError("Empty expression")
    result = _parse(tokens)
    return result
