import sys
import re
import threading

# === Data Types ===

class SchemeError(Exception):
    def __init__(self, msg='', output=''):
        super().__init__(msg)
        self.output = output

class Symbol:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name
    def __repr__(self):
        return f"Symbol({self.name!r})"
    def __eq__(self, other):
        return isinstance(other, Symbol) and self.name == other.name
    def __hash__(self):
        return hash(('Sym', self.name))

class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr
    def __repr__(self):
        return f"Pair({self.car!r}, {self.cdr!r})"

class _EmptyList:
    pass

SCHEME_EMPTY = _EmptyList()

class _Unspecified:
    pass

UNSPEC = _Unspecified()

class Closure:
    __slots__ = ('formals', 'body', 'env')
    def __init__(self, formals, body, env):
        self.formals = formals
        self.body = body
        self.env = env

class Builtin:
    __slots__ = ('name', 'func', 'min_args', 'max_args')
    def __init__(self, name, func, min_args=0, max_args=None):
        self.name = name
        self.func = func
        self.min_args = min_args
        self.max_args = max_args

class TailCall:
    __slots__ = ('body', 'env')
    def __init__(self, body, env):
        self.body = body
        self.env = env

NOT_DEFINED = object()

# === Environment ===

class Env:
    __slots__ = ('bindings', 'parent')
    def __init__(self, bindings=None, parent=None):
        self.bindings = bindings if bindings is not None else {}
        self.parent = parent

    def lookup(self, name):
        env = self
        while env is not None:
            if name in env.bindings:
                val = env.bindings[name]
                if val is NOT_DEFINED:
                    raise SchemeError(f"variable '{name}' is not yet defined")
                return val
            env = env.parent
        raise SchemeError(f"unbound variable: {name}")

    def set(self, name, value):
        env = self
        while env is not None:
            if name in env.bindings:
                if env.bindings[name] is NOT_DEFINED:
                    raise SchemeError(f"variable '{name}' is not yet defined")
                env.bindings[name] = value
                return
            env = env.parent
        raise SchemeError(f"unbound variable: {name}")

    def define(self, name, value):
        self.bindings[name] = value

# === Helpers ===

def _is_proper_list(x):
    while isinstance(x, Pair):
        x = x.cdr
    return isinstance(x, _EmptyList)

def _list_elements(x):
    elements = []
    while isinstance(x, Pair):
        elements.append(x.car)
        x = x.cdr
    return elements

def _is_procedure(x):
    return isinstance(x, (Closure, Builtin))

def _is_number(x):
    return isinstance(x, int) and not isinstance(x, bool)

# === Output ===

_output = []

# === Display / Write ===

def _int_to_str(n, radix=10):
    if radix == 10:
        try:
            old = sys.get_int_max_str_digits()
            sys.set_int_max_str_digits(0)
            try:
                return str(n)
            finally:
                sys.set_int_max_str_digits(old)
        except (AttributeError, ValueError):
            return str(n)
    else:
        if n == 0:
            return '0'
        neg = n < 0
        n = abs(n)
        digits = '0123456789abcdef'
        result = []
        while n > 0:
            n, r = divmod(n, radix)
            result.append(digits[r])
        if neg:
            result.append('-')
        return ''.join(reversed(result))

def _display_str(x):
    if isinstance(x, bool):
        return '#t' if x else '#f'
    if isinstance(x, int):
        return _int_to_str(x)
    if isinstance(x, str):
        return x
    if isinstance(x, Symbol):
        return x.name
    if isinstance(x, _EmptyList):
        return '()'
    if isinstance(x, (Closure, Builtin)):
        return '#<procedure>'
    if isinstance(x, _Unspecified):
        return ''
    if isinstance(x, Pair):
        return _display_pair(x)
    raise SchemeError("cannot display value")

def _display_pair(x):
    parts = ['(']
    first = True
    while isinstance(x, Pair):
        if not first:
            parts.append(' ')
        parts.append(_display_str(x.car))
        first = False
        x = x.cdr
    if isinstance(x, _EmptyList):
        parts.append(')')
    else:
        parts.append(' . ')
        parts.append(_display_str(x))
        parts.append(')')
    return ''.join(parts)

def _write_str(x):
    if isinstance(x, bool):
        return '#t' if x else '#f'
    if isinstance(x, int):
        return _int_to_str(x)
    if isinstance(x, str):
        escaped = x.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        return f'"{escaped}"'
    if isinstance(x, Symbol):
        return x.name
    if isinstance(x, _EmptyList):
        return '()'
    if isinstance(x, (Closure, Builtin)):
        return '#<procedure>'
    if isinstance(x, _Unspecified):
        return ''
    if isinstance(x, Pair):
        return _write_pair(x)
    raise SchemeError("cannot write value")

def _write_pair(x):
    parts = ['(']
    first = True
    while isinstance(x, Pair):
        if not first:
            parts.append(' ')
        parts.append(_write_str(x.car))
        first = False
        x = x.cdr
    if isinstance(x, _EmptyList):
        parts.append(')')
    else:
        parts.append(' . ')
        parts.append(_write_str(x))
        parts.append(')')
    return ''.join(parts)

# === Reader ===

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
            tokens.append(('LPAREN', None))
            i += 1
        elif c == ')':
            tokens.append(('RPAREN', None))
            i += 1
        elif c == "'":
            tokens.append(('QUOTE', None))
            i += 1
        elif c == '"':
            i +=