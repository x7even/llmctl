"""Reference solution (used only to validate the hidden tests; never shown to models)."""
import re

_TOKEN = re.compile(r"\s*(?:(\d+\.\d*|\.\d+|\d+)|(\*\*|//|[-+*/%()])|(\S))")


def _tokenize(s):
    toks, pos = [], 0
    s = s.rstrip()
    while pos < len(s):
        m = _TOKEN.match(s, pos)
        if not m:
            break
        num, op, bad = m.groups()
        if bad:
            raise ValueError(f"bad char {bad!r}")
        if num is not None:
            # a number directly followed by '.' or digit-run means malformed (1..2, 1.2.3)
            nxt = s[m.end():m.end() + 1]
            if nxt == ".":
                raise ValueError("malformed number")
            toks.append(("num", float(num) if "." in num else int(num)))
        else:
            toks.append(("op", op))
        pos = m.end()
    return toks


def evaluate(expr):
    toks = _tokenize(expr)
    if not toks:
        raise ValueError("empty")
    i = 0

    def peek():
        return toks[i] if i < len(toks) else (None, None)

    def eat():
        nonlocal i
        t = toks[i]
        i += 1
        return t

    def add():
        v = mul()
        while peek() in (("op", "+"), ("op", "-")):
            op = eat()[1]
            r = mul()
            v = v + r if op == "+" else v - r
        return v

    def mul():
        v = unary()
        while peek()[0] == "op" and peek()[1] in ("*", "/", "//", "%"):
            op = eat()[1]
            r = unary()
            if op == "*":
                v = v * r
            elif op == "/":
                v = v / r
            elif op == "//":
                v = v // r
            else:
                v = v % r
        return v

    def unary():
        if peek() in (("op", "-"), ("op", "+")):
            op = eat()[1]
            v = unary()
            return -v if op == "-" else +v
        return power()

    def power():
        base = primary()
        if peek() == ("op", "**"):
            eat()
            return base ** unary()
        return base

    def primary():
        t = peek()
        if t[0] == "num":
            return eat()[1]
        if t == ("op", "("):
            eat()
            v = add()
            if peek() != ("op", ")"):
                raise ValueError("expected )")
            eat()
            return v
        raise ValueError(f"unexpected {t}")

    v = add()
    if i != len(toks):
        raise ValueError("trailing tokens")
    return v
