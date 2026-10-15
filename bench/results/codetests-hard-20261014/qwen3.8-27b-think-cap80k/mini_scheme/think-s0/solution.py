import re
import sys

sys.setrecursionlimit(1000000)


class SchemeError(Exception):
    def __init__(self, msg='', output=''):
        super().__init__(msg)
        self.output = output


class SchemeSymbol:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name
    def __eq__(self, other):
        return isinstance(other, SchemeSymbol) and self.name == other.name
    def __hash__(self):
        return hash(('sym', self.name))
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


class Env:
    __slots__ = ('bindings', 'parent')
    def __init__(self, bindings, parent=None):
        self.bindings = bindings
        self.parent = parent


UNSPECIFIED = object()
UNINITIALIZED = object()
TRUE = True
FALSE = False
EMPTY_LIST = []

_LARGE_INT_THRESHOLD = 10 ** 4300


def int_to_str(n):
    if n < 0:
        return '-' + int_to_str(-n)
    if n == 0:
        return '0'
    if n >= _LARGE_INT_THRESHOLD:
        digits = []
        while n > 0:
            n, r = divmod(n, 10)
            digits.append(chr(48 + r))
        return ''.join(reversed(digits))
    return str(n)


def int_to_str_radix(n, radix):
    if n < 0:
        return '-' + int_to_str_radix(-n, radix)
    if n == 0:
        return '0'
    digits = []
    while n > 0:
        n, r = divmod(n, radix)
        if r < 10:
            digits.append(chr(48 + r))
        else:
            digits.append(chr(87 + r))
    return ''.join(reversed(digits))


# ─── Reader ───────────────────────────────────────────────────────────────────

def _skip_ws_and_comments(source, pos):
    n = len(source)
    while pos < n:
        c = source[pos]
        if c in ' \t\n\r':
            pos += 1
        elif c == ';':
            while pos < n and source[pos] != '\n':
                pos += 1
        else:
            break
    return pos


def _read_string(source, pos):
    n = len(source)
    pos += 1  # skip opening "
    chars = []
    while pos < n:
        c = source[pos]
        if c == '"':
            return (''.join(chars), pos + 1)
        elif c == '\\':
            pos += 1
            if pos >= n:
                raise SchemeError("syntax error: unterminated string")
            ec = source[pos]
            if ec == '"':
                chars.append('"')
            elif ec == '\\':
                chars.append('\\')
            elif ec == 'n':
                chars.append('\n')
            else:
                raise SchemeError(f"syntax error: invalid escape \\{ec}")
            pos += 1
        else:
            chars.append(c)
            pos += 1
    raise SchemeError("syntax error: unterminated string")


def _read_datum(source, pos):
    n = len(source)
    c = source[pos]
    if c == '(':
        pos += 1
        return _read_list(source, pos)
    if c == "'":
        pos += 1
        pos = _skip_ws_and_comments(source, pos)
        if pos >= n:
            raise SchemeError("syntax error: ' not followed by datum")
        datum, pos = _read_datum(source, pos)
        return ([SchemeSymbol('quote'), datum], pos)
    if c == '"':
        return _read_string(source, pos)
    # Read a token
    start = pos
    while pos < n and source[pos] not in ' \t\n\r()";\'':
        pos += 1
    token = source[start:pos]
    if not token:
        raise SchemeError("syntax error: empty token")
    if token == '#t':
        return (TRUE, pos)
    if token == '#f':
        return (FALSE, pos)
    if token.startswith('#'):
        raise SchemeError(f"syntax error: {token}")
    if re.fullmatch(r'[+-]?[0-9]+', token):
        return (int(token), pos)
    return (SchemeSymbol(token), pos)


def _read_list(source, pos):
    n = len(source)
    elements = []
    while True:
        pos = _skip_ws_and_comments(source, pos)
        if pos >= n:
            raise SchemeError("syntax error: unbalanced (")
        c = source[pos]
        if c == ')':
            if elements:
                return (elements, pos + 1)
            else:
                return (EMPTY_LIST, pos + 1)
        if c == '.':
            if pos + 1 >= n or source[pos + 1] in ' \t\n\r()";\'':
                pos += 1
                pos = _skip_ws_and_comments(source, pos)
                if pos >= n:
                    raise SchemeError("syntax error: unbalanced (")
                tail, pos = _read_datum(source, pos)
                pos = _skip_ws_and_comments(source, pos)
                if pos >= n or source[pos] != ')':
                    raise SchemeError("syntax error: malformed dotted list")
                pos += 1
                if isinstance(tail, list):
                    return (elements + tail, pos)
                else:
                    result = tail
                    for e in reversed(elements):
                        result = Pair(e, result)
                    return (result, pos)
            else:
                start = pos
                while pos < n and source[pos] not in ' \t\n\r()";\'':
                    pos += 1
                elements.append(SchemeSymbol(source[start:pos]))
                continue
        datum, pos = _read_datum(source, pos)
        elements.append(datum)


def read_all(source):
    pos = 0
    n = len(source)
    forms = []
    while True:
        pos = _skip_ws_and_comments(source, pos)
        if pos >= n:
            break
        if source[pos] == ')':
            raise SchemeError("syntax error: unbalanced )")
        form, pos = _read_datum(source, pos)
        forms.append(form)
    return forms


# ─── Helpers ──────────────────────────────────────────────────────────────────

def is_symbol(x, name=None):
    if not isinstance(x, SchemeSymbol):
        return False
    return name is None or x.name == name


def is_number(x):
    return isinstance(x, int) and not isinstance(x, bool)


def is_listlike(x):
    return isinstance(x, list) or isinstance(x, Pair)


def is_proper_list(x):
    if isinstance(x, list):
        return True
    if isinstance(x, Pair):
        p = x
        while isinstance(p, Pair):
            p = p.cdr
        return p is EMPTY_LIST
    return False


def to_proper_list(x):
    if isinstance(x, list):
        return x
    if isinstance(x, Pair):
        result = []
        p = x
        while isinstance(p, Pair):
            result.append(p.car)
            p = p.cdr
        if p is not EMPTY_LIST:
            raise SchemeError("not a proper list")
        return result
    raise SchemeError("not a list")


def get_car(x):
    if isinstance(x, list):
        if len(x) == 0:
            raise SchemeError("car: empty list")
        return x[0]
    elif isinstance(x, Pair):
        return x.car
    else:
        raise SchemeError("car: not a pair")


def get_cdr(x):
    if isinstance(x, list):
        if len(x) == 0:
            raise SchemeError("cdr: empty list")
        r = x[1:]
        return EMPTY_LIST if not r else r
    elif isinstance(x, Pair):
        return x.cdr
    else:
        raise SchemeError("cdr: not a pair")


# ─── Display / Write ──────────────────────────────────────────────────────────

def _display_atom(x, parts):
    if x is UNSPECIFIED:
        pass
    elif isinstance(x, bool):
        parts.append('#t' if x else '#f')
    elif isinstance(x, int):
        parts.append(int_to_str(x))
    elif isinstance(x, str):
        parts.append(x)
    elif isinstance(x, SchemeSymbol):
        parts.append(x.name)
    elif isinstance(x, (Closure, Builtin)):
        parts.append('#<procedure>')
    else:
        parts.append('?')


def _write_atom(x, parts):
    if x is UNSPECIFIED:
        pass
    elif isinstance(x, bool):
        parts.append('#t' if x else '#f')
    elif isinstance(x, int):
        parts.append(int_to_str(x))
    elif isinstance(x, str):
        parts.append('"')
        for ch in x:
            if ch == '"':
                parts.append('\\"')
            elif ch == '\\':
                parts.append('\\\\')
            elif ch == '\n':
                parts.append('\\n')
            else:
                parts.append(ch)
        parts.append('"')
    elif isinstance(x, SchemeSymbol):
        parts.append(x.name)
    elif isinstance(x, (Closure, Builtin)):
        parts.append('#<procedure>')
    else:
        parts.append('?')


def _display_iter(x, parts, atom_func):
    stack = [('datum', x)]
    while stack:
        item = stack.pop()
        tag = item[0]
        if tag == 'datum':
            v = item[1]
            if isinstance(v, list):
                if len(v) == 0:
                    parts.append('()')
                else:
                    stack.append(('close',))
                    for i in range(len(v) - 1, -1, -1):
                        if i < len(v) - 1:
                            stack.append(('space',))
                        stack.append(('datum', v[i]))
                    stack.append(('open',))
            elif isinstance(v, Pair):
                cars = []
                p = v
                while isinstance(p, Pair):
                    cars.append(p.car)
                    p = p.cdr
                stack.append(('close',))
                if p is not EMPTY_LIST:
                    stack.append(('datum', p))
                    stack.append(('dot',))
                for i in range(len(cars) - 1, -1, -1):
                    if i < len(cars) - 1:
                        stack.append(('space',))
                    stack.append(('datum', cars[i]))
                stack.append(('open',))
            else:
                atom_func(v, parts)
        elif tag == 'space':
            parts.append(' ')
        elif tag == 'open':
            parts.append('(')
        elif tag == 'close':
            parts.append(')')
        elif tag == 'dot':
            parts.append(' . ')


def display_value(x):
    parts = []
    _display_iter(x, parts, _display_atom)
    return ''.join(parts)


def write_value(x):
    parts = []
    _display_iter(x, parts, _write_atom)
    return ''.join(parts)


# ─── Evaluator ────────────────────────────────────────────────────────────────

class _Seq:
    __slots__ = ('forms',)
    def __init__(self, forms):
        self.forms = forms


def _bind_params(closure, arg_vals):
    formals = closure.formals
    if isinstance(formals, SchemeSymbol):
        return Env({formals.name: list(arg_vals)}, closure.env)
    elif isinstance(formals, list):
        if len(arg_vals) != len(formals):
            raise SchemeError(f"wrong number of arguments: expected {len(formals)}, got {len(arg_vals)}")
        bindings = {}
        for i, f in enumerate(formals):
            if not isinstance(f, SchemeSymbol):
                raise SchemeError("formal parameter must be a symbol")
            bindings[f.name] = arg_vals[i]
        return Env(bindings, closure.env)
    elif isinstance(formals, Pair):
        fixed = []
        p = formals
        while isinstance(p, Pair):
            if not isinstance(p.car, SchemeSymbol):
                raise SchemeError("formal parameter must be a symbol")
            fixed.append(p.car)
            p = p.cdr
        if not isinstance(p, SchemeSymbol):
            raise SchemeError("formal parameter must be a symbol")
        if len(arg_vals) < len(fixed):
            raise SchemeError(f"wrong number of arguments: expected at least {len(fixed)}, got {len(arg_vals)}")
        bindings = {}
        for i, f in enumerate(fixed):
            bindings[f.name] = arg_vals[i]
        bindings[p.name] = list(arg_vals[len(fixed):])
        return Env(bindings, closure.env)
    else:
        raise SchemeError("mal