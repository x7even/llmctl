import re
import sys

try:
    sys.set_int_max_str_digits(0)
except AttributeError:
    pass
sys.setrecursionlimit(1000000)


class SchemeError(Exception):
    def __init__(self, msg, output=''):
        super().__init__(msg)
        self.output = output


# ─── Data Types ───────────────────────────────────────────────────────────────

class _EmptyList:
    def __repr__(self):
        return "()"

EMPTY_LIST = _EmptyList()

UNSPECIFIED = object()
UNINITIALIZED = object()


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


class Thunk:
    __slots__ = ('expr', 'env')
    def __init__(self, expr, env):
        self.expr = expr
        self.env = env


class BodyThunk:
    __slots__ = ('body', 'env')
    def __init__(self, body, env):
        self.body = body
        self.env = env


# ─── Environment ──────────────────────────────────────────────────────────────

class Env:
    __slots__ = ('frame', 'parent')
    def __init__(self, frame, parent=None):
        self.frame = frame
        self.parent = parent

    def lookup(self, name):
        if name in self.frame:
            val = self.frame[name]
            if val is UNINITIALIZED:
                raise SchemeError(f"Uninitialized variable: {name}")
            return val
        if self.parent is not None:
            return self.parent.lookup(name)
        raise SchemeError(f"Unbound variable: {name}")

    def set(self, name, value):
        if name in self.frame:
            self.frame[name] = value
            return
        if self.parent is not None:
            self.parent.set(name, value)
        raise SchemeError(f"Unbound variable: {name}")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def scheme_true(x):
    return x is not False


def is_proper_list(x):
    current = x
    while isinstance(current, Pair):
        current = current.cdr
    return current is EMPTY_LIST


def list_to_py(l):
    result = []
    current = l
    while isinstance(current, Pair):
        result.append(current.car)
        current = current.cdr
    if current is not EMPTY_LIST:
        raise SchemeError("Expected proper list")
    return result


def py_to_list(lst):
    result = EMPTY_LIST
    for item in reversed(lst):
        result = Pair(item, result)
    return result


def is_pair(x):
    return isinstance(x, Pair)


def is_procedure(x):
    return isinstance(x, (Closure, Builtin))


# ─── Display / Write ──────────────────────────────────────────────────────────

def display_repr(x):
    if x is UNSPECIFIED:
        return ""
    if x is True:
        return "#t"
    if x is False:
        return "#f"
    if isinstance(x, int):
        return str(x)
    if isinstance(x, str):
        return x
    if isinstance(x, Symbol):
        return x.name
    if x is EMPTY_LIST:
        return "()"
    if isinstance(x, (Closure, Builtin)):
        return "#<procedure>"
    if isinstance(x, Pair):
        return _pair_display(x)
    return ""


def _pair_display(p):
    parts = []
    current = p
    while isinstance(current, Pair):
        parts.append(display_repr(current.car))
        current = current.cdr
    if current is EMPTY_LIST:
        return "(" + " ".join(parts) + ")"
    else:
        return "(" + " ".join(parts) + " . " + display_repr(current) + ")"


def write_repr(x):
    if x is UNSPECIFIED:
        return ""
    if x is True:
        return "#t"
    if x is False:
        return "#f"
    if isinstance(x, int):
        return str(x)
    if isinstance(x, str):
        s = x.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        return '"' + s + '"'
    if isinstance(x, Symbol):
        return x.name
    if x is EMPTY_LIST:
        return "()"
    if isinstance(x, (Closure, Builtin)):
        return "#<procedure>"
    if isinstance(x, Pair):
        return _pair_write(x)
    return ""


def _pair_write(p):
    parts = []
    current = p
    while isinstance(current, Pair):
        parts.append(write_repr(current.car))
        current = current.cdr
    if current is EMPTY_LIST:
        return "(" + " ".join(parts) + ")"
    else:
        return "(" + " ".join(parts) + " . " + write_repr(current) + ")"


# ─── Reader ───────────────────────────────────────────────────────────────────

_DELIMS = set(' \t\n\r()"\'')


class Reader:
    def __init__(self, source):
        self.src = source
        self.pos = 0
        self.n = len(source)

    def read_all(self):
        forms = []
        while True:
            self._skip()
            if self.pos >= self.n:
                break
            forms.append(self._read_form())
        return forms

    def _skip(self):
        while self.pos < self.n:
            c = self.src[self.pos]
            if c in ' \t\n\r':
                self.pos += 1
            elif c == ';':
                while self.pos < self.n and self.src[self.pos] != '\n':
                    self.pos += 1
            else:
                break

    def _read_form(self):
        self._skip()
        if self.pos >= self.n:
            raise SchemeError("Unexpected end of input")
        c = self.src[self.pos]
        if c == '(':
            return self._read_list()
        elif c == ')':
            raise SchemeError("Unexpected )")
        elif c == "'":
            self.pos += 1
            datum = self._read_form()
            return Pair(Symbol('quote'), Pair(datum, EMPTY_LIST))
        elif c == '"':
            return self._read_string()
        else:
            return self._read_atom()

    def _read_list(self):
        self.pos += 1  # skip '('
        self._skip()
        if self.pos < self.n and self.src[self.pos] == ')':
            self.pos += 1
            return EMPTY_LIST

        elements = []
        while True:
            self._skip()
            if self.pos >= self.n:
                raise SchemeError("Unbalanced (")
            c = self.src[self.pos]
            if c == ')':
                self.pos += 1
                result = EMPTY_LIST
                for el in reversed(elements):
                    result = Pair(el, result)
                return result
            if c == '.' and self._is_dot():
                self.pos += 1
                self._skip()
                if self.pos >= self.n:
                    raise SchemeError("Expected datum after .")
                tail = self._read_form()
                self._skip()
                if self.pos >= self.n or self.src[self.pos] != ')':
                    raise SchemeError("Expected ) after dotted list")
                self.pos += 1
                result = tail
                for el in reversed(elements):
                    result = Pair(el, result)
                return result
            form = self._read_form()
            elements.append(form)

    def _is_dot(self):
        if self.src[self.pos] != '.':
            return False
        if self.pos + 1 >= self.n:
            return True
        return self.src[self.pos + 1] in _DELIMS

    def _read_string(self):
        self.pos += 1  # skip opening "
        result = []
        while self.pos < self.n:
            c = self.src[self.pos]
            if c == '"':
                self.pos += 1
                return ''.join(result)
            elif c == '\\':
                self.pos += 1
                if self.pos >= self.n:
                    raise SchemeError("Unterminated string")
                esc = self.src[self.pos]
                if esc == '"':
                    result.append('"')
                elif esc == '\\':
                    result.append('\\')
                elif esc == 'n':
                    result.append('\n')
                else:
                    raise SchemeError(f"Invalid escape: \\{esc}")
                self.pos += 1
            else:
                result.append(c)
                self.pos += 1
        raise SchemeError("Unterminated string")

    def _read_atom(self):
        start = self.pos
        while self.pos < self.n:
            c = self.src[self.pos]
            if c in ' \t\n\r()"\'':
                break
            self.pos += 1
        token = self.src[start:self.pos]
        if not token:
            raise SchemeError("Unexpected delimiter")
        if token.startswith('#'):
            if token == '#t':
                return True
            elif token == '#f':
                return False
            else:
                raise SchemeError(f"Invalid token: {token}")
        if re.fullmatch(r'[+-]?[0-9]+', token):
            return int(token)
        return Symbol(token)


# ─── Builtins ─────────────────────────────────────────────────────────────────

def _check_ints(args, min_args=None, max_args=None):
    for a in args:
        if isinstance(a, bool) or not isinstance(a, int):
            raise SchemeError("Expected integer argument")
    if min_args is not None and len(args) < min_args:
        raise SchemeError("Wrong number of arguments")
    if max_args is not None and len(args) > max_args:
        raise SchemeError("Wrong number of arguments")


def builtin_plus(args):
    _check_ints(args)
    return sum(args)


def builtin_star(args):
    _check_ints(args)
    r = 1
    for a in args:
        r *= a
    return r


def builtin_minus(args):
    _check_ints(args, min_args=1)
    if len(args) == 1:
        return -args[0]
    r = args[0]
    for a in args[1:]:
        r -= a
    return r


def _divmod_check(a, b):
    if isinstance(a, bool) or isinstance(b, bool) or not isinstance(a, int) or not isinstance(b, int):
        raise SchemeError("Expected integer arguments")
    if b == 0:
        raise SchemeError("Division by zero")


def builtin_quotient(args):
    if len(args) != 2:
        raise SchemeError("Wrong number of arguments")
    a, b = args
    _divmod_check(a, b)
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        q = -q
    return q


def builtin_remainder(args):
    if len(args) != 2:
        raise SchemeError("Wrong number of arguments")
    a, b = args
    _divmod_check(a, b)
    r = abs(a) % abs(b)
    if a < 0:
        r = -r
    return r


def builtin_modulo(args):
    if len(args) != 2:
        raise SchemeError("Wrong number of arguments")
    a, b = args
    _divmod_check(a, b)
    m = abs(a) % abs(b)
    if b < 0:
        m = -m
    return m


def _check_comparable(args):
    if len(args) < 1:
        raise SchemeError("Wrong number of arguments")
    for a in args:
        if isinstance(a, bool) or not isinstance(a, int):
            raise SchemeError("Expected integer argument")


def builtin_eq_op(args):
    _check_comparable(args)
    for i in range(len(args) - 1):
        if not (args[i] == args[i + 1]):
            return False
    return True


def builtin_lt(args):
    _check_comparable(args)
    for i in range(len(args) - 1):
        if not (args[i] < args[i + 1]):
            return False
    return True


def builtin_gt(args):
    _check_comparable(args)
    for i in range(len(args) - 1):
        if not (args[i] > args[i + 1]):
            return False
    return True


def builtin_le(args):
    _check_comparable(args)
    for i in range(len(args) - 1):
        if not (args[i] <= args[i + 1]):
            return False
    return True


def builtin_ge(args):
    _check_comparable(args)
    for i in range(len(args) - 1):
        if not (args[i] >= args[i + 1]):
            return False
    return True


def _int_to_radix(n, radix):
    if n == 0:
        return "0"
    negative = n < 0
    n = abs(n)
    digits = "0123456789abcdef"
    result = []
    while n > 0:
        result.append(digits[n % radix])
        n //= radix
    if negative:
        result.append('-')
    result.reverse()
    return ''.join(result)


def builtin_number_to_string(args):
    if len(args) not in (1, 2):
        raise SchemeError("Wrong number of arguments")
    n = args[0]
    if isinstance(n, bool) or not isinstance(n, int):
        raise SchemeError("Expected integer")
    if len(args) == 1:
        return str(n)
    radix = args[1]
    if isinstance(radix, bool) or not isinstance(radix, int) or radix not in (2, 8, 10, 16):
        raise SchemeError("Invalid radix")
    if radix == 10:
        return str(n)
    return _int_to_radix(n, radix)


def builtin_cons(args):
    if len(args) != 2:
        raise SchemeError("Wrong number of arguments")
    return Pair(args[0], args[1])


def builtin_car(args):
    if len(args) != 1:
        raise SchemeError("Wrong number of arguments")
    if not isinstance(args[0], Pair):
        raise SchemeError("car: argument must be a pair")
    return args[0].car


def builtin_cdr(args):
    if len(args) != 1:
        raise SchemeError("Wrong number of arguments")
    if not isinstance(args[0], Pair):
        raise SchemeError("cdr: argument must be a pair")
    return args[0].cdr


def builtin_list(args):
    return py_to_list(args)


def builtin_null(args):
    if len(args) != 1:
        raise SchemeError("Wrong number of arguments")
    return args[0] is EMPTY_LIST


def builtin_pair(args):
    if len(args) != 1:
        raise SchemeError("Wrong number of arguments")
    return isinstance(args[0], Pair)


def builtin_listp(args):
    if len(args) != 1:
        raise SchemeError("Wrong number of arguments")
    return is_proper_list(args[0])


def builtin_length(args):
    if len(args) != 1:
        raise SchemeError("Wrong number of arguments")
    l = args[0]
    if not is_proper_list(l):
        raise SchemeError("length: argument must be a proper list")
    count = 0
    current = l
    while isinstance(current, Pair):
        count += 1
        current = current.cdr
    return count


def builtin_append(args):
    for l in args[:-1]:
        if not is_proper_list(l):
            raise SchemeError("append: argument must be a proper list")
    if not args:
        return EMPTY_LIST
    result = args[-1]
    for l in reversed(args[:-1]):
        current = l
        while isinstance(current, Pair):
            result = Pair(current.car, result)
            current = current.cdr
    return result


def builtin_reverse(args):
    if len(args) != 1:
        raise SchemeError("Wrong number of arguments")
    l = args[0]
    if not is_proper_list(l):
        raise SchemeError("reverse: argument must be a proper list")
    result = EMPTY_LIST
    current = l
    while isinstance(current, Pair):
        result = Pair(current.car, result)
        current = current.cdr
    return result


def builtin_apply(args):
    if len(args) < 2:
        raise SchemeError("apply: at least 2 arguments")
    f = args[0]
    middle = args[1:-1]
    lst = args[-1]
    if not is_proper_list(lst):
        raise SchemeError("apply: last argument must be a proper list")
    all_args = middle + list_to_py(lst)
    if isinstance(f, Closure):
        new_env = make_env(f.formals, all_args, f.env)
        return BodyThunk(f.body, new_env)
    elif isinstance(f, Builtin):
        return f.func(all_args)
    else:
        raise SchemeError("apply: first argument must be a procedure")


def builtin_eq(args):
    if len(args) != 2:
        raise SchemeError("Wrong number of arguments")
    a, b = args
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, int) and isinstance(b, int):
        return a == b
    if isinstance(a, Symbol) and isinstance(b, Symbol):
        return a.name == b.name
    if a is EMPTY_LIST and b is EMPTY_LIST:
        return True
    return a is b


def _equal(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, int) and isinstance(b, int):
        return a == b
    if isinstance(a, str) and isinstance(b, str):
        return a == b
    if isinstance(a, Symbol) and isinstance(b, Symbol):
        return a.name == b.name
    if a is EMPTY_LIST and b is EMPTY_LIST:
        return True
    if isinstance(a, Pair) and isinstance(b, Pair):
        return _equal(a.car, b.car) and _equal(a.cdr, b.cdr)
    if isinstance(a, (Closure, Builtin)) or isinstance(b, (Closure, Builtin)):
        return a is b
    if a is UNSPECIFIED or b is UNSPECIFIED:
        return a is b
    return False


def builtin_equal(args):
    if len(args) != 2:
        raise SchemeError("Wrong number of arguments")
    return _equal(args[0], args[1])


def builtin_not(args):
    if len(args) != 1:
        raise SchemeError("Wrong number of arguments")
    return args[0] is False


def builtin_number(args):
    if len(args) != 1:
        raise SchemeError("Wrong number of arguments")
    return isinstance(args[0], int) and not isinstance(args[0], bool)


def builtin_symbol(args):
    if len(args) != 1:
        raise SchemeError("Wrong number of arguments")
    return isinstance(args[0], Symbol)


def builtin_string(args):
    if len(args) != 1:
        raise SchemeError("Wrong number of arguments")
    return isinstance(args[0], str)