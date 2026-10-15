import sys
import re
import threading

try:
    sys.set_int_max_str_digits(0)
except AttributeError:
    pass


class SchemeError(Exception):
    def __init__(self, msg, output=''):
        super().__init__(msg)
        self.output = output


# ─── Data Types ───────────────────────────────────────────────────────────────

class _Nil:
    pass

NIL = _Nil()
UNSPECIFIED = object()
_UNASSIGNED = object()


class Symbol:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name
    def __repr__(self):
        return f"Symbol({self.name!r})"


class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr
    def __repr__(self):
        return f"Pair({self.car!r}, {self.cdr!r})"


class Closure:
    __slots__ = ('formals', 'body', 'env')
    def __init__(self, formals, body, env):
        self.formals = formals
        self.body = body
        self.env = env


class Builtin:
    __slots__ = ('name', 'func')
    def __init__(self, name, func):
        self.name = name
        self.func = func


# ─── Environment ──────────────────────────────────────────────────────────────

class Env:
    __slots__ = ('vars', 'parent')
    def __init__(self, parent=None):
        self.vars = {}
        self.parent = parent

    def lookup(self, sym):
        env = self
        while env is not None:
            if sym.name in env.vars:
                val = env.vars[sym.name]
                if val is _UNASSIGNED:
                    raise SchemeError(f"Unbound variable: {sym.name}")
                return val
            env = env.parent
        raise SchemeError(f"Unbound variable: {sym.name}")

    def set(self, sym, value):
        env = self
        while env is not None:
            if sym.name in env.vars:
                env.vars[sym.name] = value
                return
            env = env.parent
        raise SchemeError(f"Unbound variable: {sym.name}")

    def define(self, sym, value):
        self.vars[sym.name] = value


# ─── Output ───────────────────────────────────────────────────────────────────

_output = []


def _append_output(s):
    _output.append(s)


# ─── Reader ───────────────────────────────────────────────────────────────────

def _tokenize(source):
    tokens = []
    i = 0
    n = len(source)
    while i < n:
        c = source[i]
        if c in ' \t\n\r':
            i += 1
        elif c == ';':
            while i < n and source[i] != '\n':
                i += 1
        elif c == '(':
            tokens.append('(')
            i += 1
        elif c == ')':
            tokens.append(')')
            i += 1
        elif c == "'":
            tokens.append("'")
            i += 1
        elif c == '"':
            i += 1
            chars = []
            while True:
                if i >= n:
                    raise SchemeError("Unterminated string")
                if source[i] == '"':
                    i += 1
                    break
                elif source[i] == '\\' and i + 1 < n:
                    esc = source[i + 1]
                    if esc == '"':
                        chars.append('"')
                        i += 2
                    elif esc == '\\':
                        chars.append('\\')
                        i += 2
                    elif esc == 'n':
                        chars.append('\n')
                        i += 2
                    else:
                        raise SchemeError(f"Invalid escape: \\{esc}")
                else:
                    chars.append(source[i])
                    i += 1
            tokens.append(('STR', ''.join(chars)))
        else:
            j = i
            while j < n and source[j] not in ' \t\n\r()";\'':
                j += 1
            tokens.append(source[i:j])
            i = j
    return tokens


def _parse_atom(s):
    if s == '#t':
        return True
    if s == '#f':
        return False
    if s.startswith('#'):
        raise SchemeError(f"Syntax error: invalid token {s}")
    if re.fullmatch(r'[+-]?[0-9]+', s):
        return int(s)
    return Symbol(s)


def _parse_expr(tokens, i):
    if i >= len(tokens):
        raise SchemeError("Unexpected end of input")
    tok = tokens[i]
    if tok == '(':
        i += 1
        items = []
        dot_val = None
        dot_seen = False
        while True:
            if i >= len(tokens):
                raise SchemeError("Unbalanced parenthesis")
            tok = tokens[i]
            if tok == ')':
                i += 1
                break
            if tok == '.' and not dot_seen:
                if len(items) == 0:
                    raise SchemeError("Dot must be preceded by at least one element")
                dot_seen = True
                i += 1
                if i >= len(tokens) or tokens[i] == ')':
                    raise SchemeError("Expected datum after dot")
                dot_val, i = _parse_expr(tokens, i)
                if i >= len(tokens) or tokens[i] != ')':
                    raise SchemeError("Expected ) after dotted list")
                i += 1
                result = dot_val
                for item in reversed(items):
                    result = Pair(item, result)
                return result, i
            elif dot_seen:
                raise SchemeError("Expected ) after dotted list element")
            else:
                item, i = _parse_expr(tokens, i)
                items.append(item)
        result = NIL
        for item in reversed(items):
            result = Pair(item, result)
        return result, i
    if tok == ')':
        raise SchemeError("Unexpected )")
    if tok == "'":
        i += 1
        if i >= len(tokens) or tokens[i] == ')':
            raise SchemeError("Syntax error: ' not followed by datum")
        datum, i = _parse_expr(tokens, i)
        return Pair(Symbol('quote'), Pair(datum, NIL)), i
    if isinstance(tok, tuple) and tok[0] == 'STR':
        return tok[1], i + 1
    return _parse_atom(tok), i + 1


def parse_source(source):
    tokens = _tokenize(source)
    forms = []
    i = 0
    while i < len(tokens):
        form, i = _parse_expr(tokens, i)
        forms.append(form)
    return forms


# ─── Helpers ──────────────────────────────────────────────────────────────────

def is_pair(x):
    return isinstance(x, Pair)


def is_proper_list(x):
    while x is not NIL:
        if not isinstance(x, Pair):
            return False
        x = x.cdr
    return True


def to_list(pair):
    result = []
    while pair is not NIL:
        if not isinstance(pair, Pair):
            raise SchemeError("Expected proper list")
        result.append(pair.car)
        pair = pair.cdr
    return result


def truthy(x):
    return x is not False


def int_to_str(n, radix=10):
    if n == 0:
        return '0'
    neg = n < 0
    n = abs(n)
    digits = '0123456789abcdef'
    result = []
    while n > 0:
        result.append(digits[n % radix])
        n //= radix
    s = ''.join(reversed(result))
    return '-' + s if neg else s


# ─── Display / Write ──────────────────────────────────────────────────────────

def _display_value(val):
    _append_output(_display_str(val))


def _display_str(val):
    if val is True:
        return '#t'
    if val is False:
        return '#f'
    if isinstance(val, int):
        return int_to_str(val)
    if isinstance(val, str):
        return val
    if isinstance(val, Symbol):
        return val.name
    if val is NIL:
        return '()'
    if val is UNSPECIFIED:
        return ''
    if isinstance(val, (Closure, Builtin)):
        return '#<procedure>'
    if isinstance(val, Pair):
        return _display_pair(val)
    return ''


def _display_pair(pair):
    parts = ['(']
    first = True
    current = pair
    while True:
        if current is NIL:
            break
        if not isinstance(current, Pair):
            if not first:
                parts.append(' . ')
            parts.append(_display_str(current))
            break
        if not first:
            parts.append(' ')
        parts.append(_display_str(current.car))
        first = False
        current = current.cdr
    parts.append(')')
    return ''.join(parts)


def _write_value(val):
    if val is True:
        return '#t'
    if val is False:
        return '#f'
    if isinstance(val, int):
        return int_to_str(val)
    if isinstance(val, str):
        return _write_string(val)
    if isinstance(val, Symbol):
        return val.name
    if val is NIL:
        return '()'
    if val is UNSPECIFIED:
        return ''
    if isinstance(val, (Closure, Builtin)):
        return '#<procedure>'
    if isinstance(val, Pair):
        return _write_pair(val)
    return ''


def _write_string(s):
    out = ['"']
    for c in s:
        if c == '"':
            out.append('\\"')
        elif c == '\\':
            out.append('\\\\')
        elif c == '\n':
            out.append('\\n')
        else:
            out.append(c)
    out.append('"')
    return ''.join(out)


def _write_pair(pair):
    parts = ['(']
    first = True
    current = pair
    while True:
        if current is NIL:
            break
        if not isinstance(current, Pair):
            if not first:
                parts.append(' . ')
            parts.append(_write_value(current))
            break
        if not first:
            parts.append(' ')
        parts.append(_write_value(current.car))
        first = False
        current = current.cdr
    parts.append(')')
    return ''.join(parts)


# ─── Equality ─────────────────────────────────────────────────────────────────

def _scheme_eq(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, int) or isinstance(b, int):
        return isinstance(a, int) and isinstance(b, int) and a == b
    if isinstance(a, Symbol) or isinstance(b, Symbol):
        return isinstance(a, Symbol) and isinstance(b, Symbol) and a.name == b.name
    if a is NIL or b is NIL:
        return a is NIL and b is NIL
    if isinstance(a, str) or isinstance(b, str):
        return a is b
    if isinstance(a, (Closure, Builtin)) or isinstance(b, (Closure, Builtin)):
        return a is b
    if isinstance(a, Pair) or isinstance(b, Pair):
        return a is b
    return a is b


def _scheme_equal(a, b):