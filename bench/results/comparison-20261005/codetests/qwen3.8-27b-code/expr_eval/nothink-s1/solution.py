"""Arithmetic expression evaluator without eval/exec/compile/ast."""

from __future__ import annotations


class _Token:
    __slots__ = ("kind", "value")

    def __init__(self, kind: str, value: object = None) -> None:
        self.kind = kind
        self.value = value

    def __repr__(self) -> str:
        return f"_Token({self.kind!r}, {self.value!r})"


def _tokenize(expr: str) -> list[_Token]:
    tokens: list[_Token] = []
    i = 0
    n = len(expr)
    while i < n:
        ch = expr[i]
        if ch in " \t":
            i += 1
            continue
        if ch in "+-*/%()":
            if ch == "*":
                if i + 1 < n and expr[i + 1] == "*":
                    tokens.append(_Token("OP", "**"))
                    i += 2
                else:
                    tokens.append(_Token("OP", "*"))
                    i += 1
            elif ch == "/":
                if i + 1 < n and expr[i + 1] == "/":
                    tokens.append(_Token("OP", "//"))
                    i += 2
                else:
                    tokens.append(_Token("OP", "/"))
                    i += 1
            else:
                tokens.append(_Token("OP", ch))
                i += 1
        elif ch.isdigit() or ch == ".":
            # Parse a number: digits, optional single dot, more digits
            j = i
            seen_dot = False
            seen_digit = False
            while j < n:
                c = expr[j]
                if c.isdigit():
                    seen_digit = True
                    j += 1
                elif c == ".":
                    if seen_dot:
                        raise ValueError(f"Malformed number at position {i}: {expr[i:j+1]!r}")
                    seen_dot = True
                    j += 1
                else:
                    break
            if not seen_digit:
                raise ValueError(f"Invalid number: lone dot or malformed number at position {i}")
            num_str = expr[i:j]
            if seen_dot:
                tokens.append(_Token("NUM", float(num_str)))
            else:
                tokens.append(_Token("NUM", int(num_str)))
            i = j
        else:
            raise ValueError(f"Invalid character {ch!r} at position {i}")
    return tokens


def _parse(tokens: list[_Token], pos: int = 0):
    """
    Grammar (precedence low to high):
      expression  := additive
      additive    := multiplicative (('+' | '-') multiplicative)*
      multiplicative := unary (('*' | '/' | '//' | '%') unary)*
      unary       := ('+' | '-')* power
      power       := atom ('**' unary)?   # right-assoc, right side can have unary
      atom        := NUM | '(' expression ')'

    Note on ** and unary: In Python, -2**2 == -4, 2**-1 == 0.5, 2**3**2 == 512.
    The rule: power := atom ('**' unary)? where the right side is a unary
    (which itself can be a power). This makes ** right-associative and allows
    unary on the right.
    """
    def parse_expression():
        return parse_additive()

    def parse_additive():
        left, pos = parse_multiplicative()
        while pos < len(tokens) and tokens[pos].kind == "OP" and tokens[pos].value in ("+", "-"):
            op = tokens[pos].value
            pos += 1
            right, pos = parse_multiplicative()
            if op == "+":
                left = left + right
            else:
                left = left - right
        return left, pos

    def parse_multiplicative():
        left, pos = parse_unary()
        while pos < len(tokens) and tokens[pos].kind == "OP" and tokens[pos].value in ("*", "/", "//", "%"):
            op = tokens[pos].value
            pos += 1
            right, pos = parse_unary()
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
                    raise ZeroDivisionError("integer division or modulo by zero")
                left = left % right
        return left, pos

    def parse_unary():
        pos = pos
        sign = 1
        while pos < len(tokens) and tokens[pos].kind == "OP" and tokens[pos].value in ("+", "-"):
            if tokens[pos].value == "-":
                sign = -sign
            pos += 1
        value, pos = parse_power()
        if sign == -1:
            value = -value
        return value, pos

    def parse_power():
        left, pos = parse_atom()
        if pos < len(tokens) and tokens[pos].kind == "OP" and tokens[pos].value == "**":
            pos += 1
            # Right side is a unary (to allow 2**-1)
            right, pos = parse_unary()
            if isinstance(left, int) and isinstance(right, int):
                if right < 0:
                    if left == 0:
                        raise ZeroDivisionError("0.0 cannot be raised to a negative power")
                    left = float(left) ** float(right)
                else:
                    left = left ** right
            else:
                if left == 0 and right < 0:
                    raise ZeroDivisionError("0.0 cannot be raised to a negative power")
                left = left ** right
        return left, pos

    def parse_atom():
        nonlocal pos
        if pos >= len(tokens):
            raise ValueError("Unexpected end of expression")
        tok = tokens[pos]
        if tok.kind == "NUM":
            pos += 1
            return tok.value, pos
        if tok.kind == "OP" and tok.value == "(":
            pos += 1
            if pos >= len(tokens):
                raise ValueError("Unbalanced parentheses")
            if tokens[pos].kind == "OP" and tokens[pos].value == ")":
                raise ValueError("Empty parentheses")
            value, pos = parse_expression()
            if pos >= len(tokens) or tokens[pos].kind != "OP" or tokens[pos].value != ")":
                raise ValueError("Unbalanced parentheses")
            pos += 1
            return value, pos
        raise ValueError(f"Unexpected token {tok!r}")

    # We need to use a mutable pos; let's restructure with a class or use a list
    # Actually, let's use a wrapper
    state = {"pos": pos}

    def parse_expression2():
        return parse_additive2()

    def parse_additive2():
        left, state["pos"] = parse_multiplicative2()
        while state["pos"] < len(tokens) and tokens[state["pos"]].kind == "OP" and tokens[state["pos"]].value in ("+", "-"):
            op = tokens[state["pos"]].value
            state["pos"] += 1
            right, state["pos"] = parse_multiplicative2()
            if op == "+":
                left = left + right
            else:
                left = left - right
        return left

    def parse_multiplicative2():
        left, state["pos"] = parse_unary2()
        while state["pos"] < len(tokens) and tokens[state["pos"]].kind == "OP" and tokens[state["pos"]].value in ("*", "/", "//", "%"):
            op = tokens[state["pos"]].value
            state["pos"] += 1
            right, state["pos"] = parse_unary2()
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
                    raise ZeroDivisionError("integer division or modulo by zero")
                left = left % right
        return left

    def parse_unary2():
        sign = 1
        while state["pos"] < len(tokens) and tokens[state["pos"]].kind == "OP" and tokens[state["pos"]].value in ("+", "-"):
            if tokens[state["pos"]].value == "-":
                sign = -sign
            state["pos"] += 1
        value = parse_power2()
        if sign == -1:
            value = -value
        return value

    def parse_power2():
        left = parse_atom2()
        if state["pos"] < len(tokens) and tokens[state["pos"]].kind == "OP" and tokens[state["pos"]].value == "**":
            state["pos"] += 1
            right = parse_unary2()
            if isinstance(left, int) and isinstance(right, int):
                if right < 0:
                    if left == 0:
                        raise ZeroDivisionError("0.0 cannot be raised to a negative power")
                    left = float(left) ** float(right)
                else:
                    left = left ** right
            else:
                if left == 0 and right < 0:
                    raise ZeroDivisionError("0.0 cannot be raised to a negative power")
                left = left ** right
        return left

    def parse_atom2():
        p = state["pos"]
        if p >= len(tokens):
            raise ValueError("Unexpected end of expression")
        tok = tokens[p]
        if tok.kind == "NUM":
            state["pos"] = p + 1
            return tok.value
        if tok.kind == "OP" and tok.value == "(":
            state["pos"] = p + 1
            if state["pos"] >= len(tokens):
                raise ValueError("Unbalanced parentheses")
            if tokens[state["pos"]].kind == "OP" and tokens[state["pos"]].value == ")":
                raise ValueError("Empty parentheses")
            value = parse_expression2()
            if state["pos"] >= len(tokens) or tokens[state["pos"]].kind != "OP" or tokens[state["pos"]].value != ")":
                raise ValueError("Unbalanced parentheses")
            state["pos"] += 1
            return value
        raise ValueError(f"Unexpected token {tok!r}")

    result = parse_expression2()
    if state["pos"] != len(tokens):
        raise ValueError(f"Unexpected token {tokens[state['pos']]!r}")
    return result


def evaluate(expr: str) -> int | float:
    if not expr or not expr.strip():
        raise ValueError("Empty expression")
    tokens = _tokenize(expr)
    if not tokens:
        raise ValueError("Empty expression")
    return _parse(tokens, 0)
