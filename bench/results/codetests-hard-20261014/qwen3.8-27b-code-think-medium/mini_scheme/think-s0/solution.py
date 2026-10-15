import sys
import re

try:
    sys.set_int_max_str_digits(0)
except (AttributeError, ValueError):
    pass

sys.setrecursionlimit(200000)


class SchemeError(Exception):
    def __init__(self, msg='', output=''):
        super().__init__(msg)
        self.output = output


# ─── Data Types ───────────────────────────────────────────────────────────────

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

class _EmptyList:
    pass

EMPTY = _EmptyList()

class _Unspecified:
    pass

UNSPECIFIED = _Unspecified()

UNINITIALIZED = object()

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

class TailCall:
    __slots__ = ('proc', 'args')
    def __init__(self, proc, args):
        self.proc = proc
        self.args = args

class Env:
    __slots__ = ('frame', 'parent')
    def __init__(self, frame, parent=None):
        self.frame = frame
        self.parent = parent
    def lookup(self, name):
        env = self
        while env is not None:
            if name in env.frame:
                val = env.frame[name]
                if val is UNINITIALIZED:
                    raise SchemeError(f"variable not yet initialized: {name}")
                return val
            env = env.parent
        raise SchemeError(f"unbound variable: {name}")
    def set(self, name, value):
        env = self
        while env is not None:
            if name in env.frame:
                env.frame[name] = value
                return
            env = env.parent
        raise SchemeError(f"unbound variable: {name}")
    def define(self, name, value):
        self.frame[name] = value


# ─── Helpers ──────────────────────────────────────────────────────────────────

def is_scheme_int(x):
    return isinstance(x, int) and not isinstance(x, bool)

def is_procedure(x):
    return isinstance(x, (Closure, Builtin))

def is_proper_list(x):
    cur = x
    while cur is not EMPTY:
        if not isinstance(cur, Pair):
            return False
        cur = cur.cdr
    return True

def list_to_py(lst):
    result = []
    cur = lst
    while cur is not EMPTY:
        if not isinstance(cur, Pair):
            raise SchemeError("expected proper list")
        result.append(cur.car)
        cur = cur.cdr
    return result

def build_scheme_list(py_list):
    result = EMPTY
    for item in reversed(py_list):
        result = Pair(item, result)
    return result

def is_truthy(x):
    return x is not False


# ─── Reader ───────────────────────────────────────────────────────────────────

def _skip_ws(src, pos, n):
    while pos < n:
        c = src[pos]
        if c in ' \t\n\r':
            pos += 1
        elif c == ';':
            while pos < n and src[pos] != '\n':
                pos += 1
        else:
            break
    return pos

def _read_form(src, pos, n):
    c = src[pos