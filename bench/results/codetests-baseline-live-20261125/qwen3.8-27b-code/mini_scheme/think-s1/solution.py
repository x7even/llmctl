import sys
import re
import operator

if hasattr(sys, 'set_int_max_str_digits'):
    sys.set_int_max_str_digits(0)
sys.setrecursionlimit(200000)


class SchemeError(Exception):
    def __init__(self, msg=""):
        super().__init__(msg)
        self.output = ''


class Symbol:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name


class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr


class _Unspecified:
    _instance = None
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    def __repr__(self):
        return '#<unspecified>'

UNSPECIFIED = _Unspecified()
_UNINIT = object()


class Closure:
    __slots__ = ('fixed_params', 'rest_param', 'body', 'env')
    def __init__(self, fixed_params, rest_param, body, env):
        self.fixed_params = fixed_params
        self.rest_param = rest_param
        self.body = body
        self.env = env


class Builtin:
    __slots__ = ('name', 'func')
    def __init__(self, name, func):
        self.name = name
        self.func = func


class Body:
    __slots__ = ('forms',)
    def __init__(self, forms):
        self.forms = forms


class Env:
    __slots__ = ('bindings', 'parent')
    def __init__(self, bindings, parent=None):
        self.bindings = bindings
        self.parent = parent


def env_lookup(env, name):
    e = env
    while e is not None:
        if name in e.bindings:
            val = e.bindings[name]
            if val is _UNINIT:
                raise SchemeError(f"uninitialized variable: {name}")
            return val
        e = e.parent
    raise SchemeError(f"unbound variable: {name}")


def env_set(env, name, value):
    e = env
    while e is not None:
        if name in e.bindings:
            e.bindings[name] = value
            return
        e = e.parent
    raise SchemeError(f"unbound variable: {name}")


def env_define(env, name, value):
    env.bindings[name] = value


def is_true(val):
    return val is not False


# ==================== READER ====================

def read_all(source):
    pos = 0
    forms = []
    n = len(source)
    while True:
        pos = _skip_ws(source, pos)
        if pos >= n:
            break
        form, pos = _read_one(source, pos)
        forms.append(form)
    return forms


def _skip_ws(source, pos):
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


def _read_one(source, pos):
    pos = _skip_ws(source, pos)
    n = len(source)
    if pos >= n:
        raise SchemeError("unexpected end of input")
    c = source[pos]
    if c == '(':
        return _read_list(source, pos)
    if c == ')':
        raise SchemeError("unexpected )")
    if c == "'":
        pos += 1
        pos = _skip_ws(source, pos)
        if pos >= n:
            raise SchemeError("quote not followed by datum")
        datum, pos = _read_one(source, pos)
        return [Symbol('quote'), datum], pos
    if c == '"':
        return _read_string(source, pos)
    start = pos
    while pos < n and source[pos] not in ' \t\n\r()";\'':
        pos += 1
    token = source[start:pos]
    if not token:
        raise SchemeError("empty token")
    return _read_token(token), pos


def _read_list(source, pos):
    assert source[pos] == '('
    pos += 1
    n = len(source)
    elements = []
    while True:
        pos = _skip_ws(source, pos)
        if pos >= n:
            raise SchemeError("unbalanced (")
        c = source[pos]
        if c == ')':
            pos += 1
            return elements, pos
        if c == '(':
            elem, pos = _read_list(source, pos)
        elif c == "'":
            pos += 1
            pos = _skip_ws(source, pos)
            if pos >= n:
                raise SchemeError("quote not followed by datum")
            datum, pos = _read_one(source, pos)
            elem = [Symbol('quote'), datum]
        elif c == '"':
            elem, pos = _read_string(source, pos)
        else:
            start = pos
            while pos < n and source[pos] not in ' \t\n\r()";\'':
                pos += 1
            token = source[start:pos]
            if token == '.':
                if len(elements) == 0:
                    raise SchemeError("dot must be preceded by element")
                pos = _skip_ws(source, pos)
                if pos >= n or source[pos] == ')':
                    raise SchemeError("dot must be followed by datum")
                tail, pos = _read_one(source, pos)
                pos = _skip_ws(source, pos)
                if pos >= n or source[pos] != ')':
                    raise SchemeError("dotted list must end with )")
                pos += 1
                return _build_dotted(elements, tail), pos
            else:
                elem = _read_token(token)
        elements.append(elem)


def _read_string(source, pos):
    assert source[pos] == '"'
    pos += 1
    n = len(source)
    chars = []
    while pos < n:
        c = source[pos]
        if c == '"':
            pos += 1
            return ''.join(chars), pos
        elif c == '\\':
            pos += 1
            if pos >= n:
                raise SchemeError("unterminated string")
            esc = source[pos]
            if esc == '"':
                chars.append('"')
            elif esc == '\\':
                chars.append('\\')
            elif esc == 'n':
                chars.append('\n')
            else:
                raise SchemeError(f"invalid escape: \\{esc}")
            pos += 1
        else:
            chars.append(c)
            pos += 1
    raise SchemeError("unterminated string")


def _read_token(token):
    if token == '#t':
        return True
    if token == '#f':
        return False
    if token.startswith('#'):
        raise SchemeError(f"invalid token: {token}")
    if re.fullmatch(r'[+-]?[0-9]+', token):
        return int(token)
    return Symbol(token)


def _build_dotted(elements, tail):
    if len(elements) == 0:
        return tail
    if isinstance(tail, list):
        return elements + tail
    else:
        p = tail
        for i in range(len(elements) - 1, -1, -1):
            p = Pair(elements[i], p)
        return p


# ==================== DISPLAY / WRITE ====================

def display_value(val, out):
    if isinstance(val, bool):
        out.append('#t' if val else '#f')
    elif isinstance(val, int):
        out.append(str(val))
    elif isinstance(val, str):
        out.append(val)
    elif isinstance(val, Symbol):
        out.append(val.name)
    elif isinstance(val, list):
        if len(val) == 0:
            out.append('()')
        else:
            out.append('(')
            for i, elem in enumerate(val):
                if i > 0:
                    out.append(' ')
                display_value(elem, out)
            out.append(')')
    elif isinstance(val, Pair):
        out.append('(')
        first = True
        p = val
        while isinstance(p, Pair):
            if not first:
                out.append(' ')
            display_value(p.car, out)
            first = False
            p = p.cdr
        out.append(' . ')
        display_value(p, out)
        out.append(')')
    elif isinstance(val, (Closure, Builtin)):
        out.append('#<procedure>')
    elif val is UNSPECIFIED:
        pass
    else:
        out.append(repr(val))


def write_repr(val):
    if isinstance(val, bool):
        return '#t' if val else '#f'
    elif isinstance(val, int):
        return str(val)
    elif isinstance(val, str):
        s = val.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        return f'"{s}"'
    elif isinstance(val, Symbol):
        return val.name
    elif isinstance(val, list):
        if len(val) == 0:
            return '()'
        parts = [write_repr(e) for e in val]
        return '(' + ' '.join(parts) + ')'
    elif isinstance(val, Pair):
        parts = []
        p = val
        first = True
        while isinstance(p, Pair):
            if not first:
                parts.append(' ')
            parts.append(write_repr(p.car))
            first = False
            p = p.cdr
        parts.append(' . ')
        parts.append(write_repr(p))
        return '(' + ''.join(parts) + ')'
    elif isinstance(val, (Closure, Builtin)):
        return '#<procedure>'
    elif val is UNSPECIFIED:
        return ''
    else:
        return str(val)


# ==================== EQUALITY ====================

def scheme_eq(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        if isinstance(a, bool) and isinstance(b, bool):
            return a is b
        return False
    if isinstance(a, int) and isinstance(b, int):
        return a == b
    if isinstance(a, str) and isinstance(b, str):
        return a is b
    if isinstance(a, Symbol) and isinstance(b, Symbol):
        return a.name == b.name
    if isinstance(a, list) and isinstance(b, list):
        if len(a) == 0 and len(b) == 0:
            return True
        return a is b
    if isinstance(a, (Closure, Builtin)) and isinstance(b, (Closure, Builtin)):
        return a is b
    if isinstance(a, Pair) and isinstance(b, Pair):
        return a is b
    if a is UNSPECIFIED and b is UNSPECIFIED:
        return True
    return False


def scheme_equal(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        if isinstance(a, bool) and isinstance(b, bool):
            return a is b
        return False
    if isinstance(a, int) and isinstance(b, int):
        return a == b
    if isinstance(a, str) and isinstance(b, str):
        return a == b
    if isinstance(a, Symbol) and isinstance(b, Symbol):
        return a.name == b.name
    if isinstance(a, list) and isinstance(b, list):
        if len(a) == 0 and len(b) == 0:
            return True
        if len(a) != len(b):
            return False
        for i in range(len(a)):
            if not scheme_equal(a[i], b[i]):
                return False
        return True
    if isinstance(a, Pair) and isinstance(b, Pair):
        return scheme_equal(a.car, b.car) and scheme_equal(a.cdr, b.cdr)
    if isinstance(a, list) and isinstance(b, Pair):
        return False
    if isinstance(a, Pair) and isinstance(b, list):
        return False
    if isinstance(a, (Closure, Builtin)) and isinstance(b, (Closure, Builtin)):
        return a is b
    if a is UNSPECIFIED and b is UNSPECIFIED:
        return True
    return False


# ==================== BUILTINS ====================

def _num_check(args):
    for a in args:
        if isinstance(a, bool) or not isinstance(a, int):
            raise SchemeError("numeric argument required")


def _int_to_radix(n, radix):
    if n < 0:
        return '-' + _int_to_radix(-n, radix)
    if radix == 10:
        return str(n)
    elif radix == 16:
        return hex(n)[2:]
    elif radix == 8:
        return oct(n)[2:]
    elif radix == 2:
        return bin(n)[2:]
    raise SchemeError("invalid radix")


def make_global_env():
    env = Env({})

    def b_plus(args, out):
        _num_check(args)
        return sum(args)
    env_define(env, '+', Builtin('+', b_plus))

    def b_star(args, out):
        _num_check(args)
        r = 1
        for a in args:
            r *= a
        return r
    env_define(env, '*', Builtin('*', b_star))

    def b_minus(args, out):
        _num_check(args)
        if len(args) == 1:
            return -args[0]
        r = args[0]
        for a in args[1:]:
            r -= a
        return r
    env_define(env, '-', Builtin('-', b_minus))

    def b_quotient(args, out):
        _num_check(args)
        if len(args) != 2:
            raise SchemeError("quotient: exactly 2 arguments")
        if args[1] == 0:
            raise SchemeError("division by zero")
        q = abs(args[0]) // abs(args[1])
        if (args[0] < 0) != (args[1] < 0):
            q = -q
        return q
    env_define(env, 'quotient', Builtin('quotient', b_quotient))

    def b_remainder(args, out):
        _num_check(args)
        if len(args) != 2:
            raise SchemeError("remainder: exactly 2 arguments")
        if args[1] == 0:
            raise SchemeError("division by zero")
        q = abs(args[0]) // abs(args[1])
        if (args[0] < 0) != (args[1] < 0):
            q = -q
        return args[0] - q * args[1]
    env_define(env, 'remainder', Builtin('remainder', b_remainder))

    def b_modulo(args, out):
        _num_check(args)
        if len(args) != 2:
            raise SchemeError("modulo: exactly 2 arguments")
        if args[1] == 0:
            raise SchemeError("division by zero")
        r = abs(args[0]) % abs(args[1])
        if args[1] < 0:
            r = -r
        return r
    env_define(env, 'modulo', Builtin('modulo', b_modulo))

    def _make_cmp(op):
        def cmp_fn(args, out):
            _num_check(args)
            if len(args) == 0:
                raise SchemeError("comparison: at least 1 argument")
            for i in range(len(args) - 1):
                if not op(args[i], args[i + 1]):
                    return False
            return True
        return cmp_fn

    env_define(env, '=', Builtin('=', _make_cmp(operator.eq)))
    env_define(env, '<', Builtin('<', _make_cmp(operator.lt)))
    env_define(env, '>', Builtin('>', _make_cmp(operator.gt)))
    env_define(env, '<=', Builtin('<=', _make_cmp(operator.le)))
    env_define(env, '>=', Builtin('>=', _make_cmp(operator.ge)))

    def b_num_to_str(args, out):
        _num_check(args)
        if len(args) not in (1, 2):
            raise SchemeError("number->string: 1 or 2 arguments")
        n = args[0]
        radix = args[1] if len(args) == 2 else 10
        if not isinstance(radix, int) or isinstance(radix, bool):
            raise SchemeError("number->string: radix must be integer")
        if radix not in (2, 8, 10, 16):
            raise SchemeError("number->string: invalid radix")
        return _int_to_radix(n, radix)
    env_define(env, 'number->string', Builtin('number->string', b_num_to_str))

    def b_cons(args, out):
        if len(args) != 2:
            raise SchemeError("cons: exactly 2 arguments")
        a, b = args
        if isinstance(b, list):
            return [a] + b
        return Pair(a, b)
    env_define(env, 'cons', Builtin('cons', b_cons))

    def b_car(args, out):
        if len(args) != 1:
            raise SchemeError("car: exactly 1 argument")
        a = args[0]
        if isinstance(a, list):
            if len(a) == 0:
                raise SchemeError("car: not a pair")
            return a[0]
        elif isinstance(a, Pair):
            return a.car
        raise SchemeError("car: not a pair")
    env_define(env, 'car', Builtin('car', b_car))

    def b_cdr(args, out):
        if len(args) != 1:
            raise SchemeError("cdr: exactly 1 argument")
        a = args[0]
        if isinstance(a, list):
            if len(a) == 0:
                raise SchemeError("cdr: not a pair")
            return a[1:]
        elif isinstance(a, Pair):
            return a.cdr
        raise SchemeError("cdr: not a pair")
    env_define(env, 'cdr', Builtin('cdr', b_cdr))

    def b_list(args, out):
        return list(args)
    env_define(env, 'list', Builtin('list', b_list))

    def b_null_p(args, out):
        if len(args) != 1:
            raise SchemeError("null?: exactly 1 argument")
        return isinstance(args[0], list) and len(args[0]) == 0
    env_define(env, 'null?', Builtin('null?', b_null_p))

    def b_pair_p(args, out):
        if len(args) != 1:
            raise SchemeError("pair?: exactly 1 argument")
        a = args[0]
        return (isinstance(a, list) and len(a) > 0) or isinstance(a, Pair)
    env_define(env, 'pair?', Builtin('pair?', b_pair_p))

    def b_list_p(args, out):
        if len(args) != 1:
            raise SchemeError("list?: exactly 1 argument")
        return isinstance(args[0], list)
    env_define(env, 'list?', Builtin('list?', b_list_p))

    def b_length(args, out):
        if len(args) != 1:
            raise SchemeError("length: exactly 1 argument")
        a = args[0]
        if not isinstance(a, list):
            raise SchemeError("length: not a proper list")
        return len(a)
    env_define(env, 'length', Builtin('length', b_length))

    def b_append(args, out):
        for a in args[:-1]:
            if not isinstance(a, list):
                raise SchemeError("append: not a proper list")
        if len(args) == 0:
            return []
        if len(args) == 1:
            return args[0]
        result = []
        for a in args[:-1]:
            result.extend(a)
        last = args[-1]
        if isinstance(last, list):
            result.extend(last)
            return result
        else:
            if len(result) == 0:
                return last
            p = last
            for i in range(len(result) - 1, -1, -1):
                p = Pair(result[i], p)
            return p
    env_define(env, 'append', Builtin('append', b_append))

    def b_reverse(args, out):
        if len(args) != 1:
            raise SchemeError("reverse: exactly 1 argument")
        a = args[0]
        if not isinstance(a, list):
            raise SchemeError("reverse: not a proper list")
        return list(reversed(a))
    env_define(env, 'reverse', Builtin('reverse', b_reverse))

    def b_apply(args, out):
        if len(args) < 2:
            raise SchemeError("apply: at least 2 arguments")
        f = args[0]
        extra = args[1:-1]
        lst = args[-1]
        if not isinstance(lst, list):
            raise SchemeError("apply: last argument must be a proper list")
        all_args = extra + lst
        return _call_procedure(f, all_args, out)
    env_define(env, 'apply', Builtin('apply', b_apply))

    def b_eq(args, out):
        if len(args) != 2:
            raise SchemeError("eq?: exactly 2 arguments")
        return scheme_eq(args[0], args[1])
    env_define(env, 'eq?', Builtin('eq?', b_eq))

    def b_equal(args, out):
        if len(args) != 2:
            raise SchemeError("equal?: exactly 2 arguments")
        return scheme_equal(args[0], args[1])
    env_define(env, 'equal?', Builtin('equal?', b_equal))

    def b_not(args, out):
        if len(args) != 1:
            raise SchemeError("not: exactly 1 argument")
        return args[0] is False
    env_define(env, 'not', Builtin('not', b_not))

    def b_number_p(args, out):
        if len(args) != 1:
            raise SchemeError("number?: exactly 1 argument")
        a = args[0]
        return isinstance(a, int) and not isinstance(a, bool)
    env_define(env, 'number?', Builtin('number?', b_number_p))

    def b_symbol_p(args, out):
        if len(args) != 1:
            raise SchemeError("symbol?: exactly 1 argument")
        return isinstance(args[0], Symbol)
    env_define(env, 'symbol?', Builtin('symbol?', b_symbol_p))

    def b_string_p(args, out):
        if len(args) != 1:
            raise SchemeError("string?: exactly 1 argument")
        return isinstance(args[0], str)
    env_define(env, 'string?', Builtin('string?', b_string_p))

    def b_procedure_p(args, out):
        if len(args) != 1:
            raise SchemeError("procedure?: exactly 1 argument")
        return isinstance(args[0], (Closure, Builtin))
    env_define(env, 'procedure?', Builtin('procedure?', b_procedure_p))

    def b_str_append(args, out):
        for a in args:
            if not isinstance(a, str):
                raise SchemeError("string-append: all arguments must be strings")
        return ''.join(args)
    env_define(env, 'string-append', Builtin('string-append', b_str_append))

    def b_display(args, out):
        if len(args) != 1:
            raise SchemeError("display: exactly 1 argument")
        display_value(args[0], out)
        return UNSPECIFIED
    env_define(env, 'display', Builtin('display', b_display))

    def b_newline(args, out):
        if len(args) != 0:
            raise SchemeError("newline: 0 arguments")
        out.append('\n')
        return UNSPECIFIED
    env_define(env, 'newline', Builtin('newline', b_newline))

    def b_error(args, out):
        if len(args) < 1:
            raise SchemeError("error: at least 1 argument")
        msg = args[0]
        if not isinstance(msg, str):
            raise SchemeError("error: first argument must be a string")
        parts = [msg]
        for irritant in args[1:]:
            parts.append(' ')
            parts.append(write_repr(irritant))
        raise SchemeError(''.join(parts))
    env_define(env, 'error', Builtin('error', b_error))

    return env


# ==================== EVALUATOR ====================

def _call_procedure(op, args, out):
    if isinstance(op, Closure):
        return _call_closure(op, args, out)
    elif isinstance(op, Builtin):
        return op.func(args, out)
    raise SchemeError("not a procedure")


def _bind_closure_args(closure, args):
    fixed = closure.fixed_params
    rest = closure.rest_param
    if rest is not None:
        if len(args) < len(fixed):
            raise SchemeError(f"wrong number of arguments: expected at least {len(fixed)}, got {len(args)}")
        bindings = {}
        for i, name in enumerate(fixed):
            bindings[name] = args[i]
        bindings[rest] = args[len(fixed):]
        return Env(bindings, closure.env)
    else:
        if len(args) != len(fixed):
            raise SchemeError(f"wrong number of arguments: expected {len(fixed)}, got {len(args)}")
        bindings = {}
        for i, name in enumerate(fixed):
            bindings[name] = args[i]
        return Env(bindings, closure.env)


def _call_closure(closure, args, out):
    new_env = _bind_closure_args(closure, args)
    return _eval_body(closure.body, new_env, out)


def _get_internal_def_names(forms):
    names = []
    for form in forms:
        if (isinstance(form, list) and len(form) > 0 and
                isinstance(form[0], Symbol) and form[0].name == 'define'):
            if len(form) >= 3:
                if isinstance(form[1], Symbol):
                    names.append(form[1].name)
                elif isinstance(form[1], list) and len(form[1]) > 0 and isinstance(form[1][0], Symbol):
                    names.append(form[1][0].name)
                elif isinstance(form[1], Pair) and isinstance(form[1].car, Symbol):
                    names.append(form[1].car.name)
    return names


def _is_define_form(form):
    return (isinstance(form, list) and len(form) > 0 and
            isinstance(form[0], Symbol) and form[0].name == 'define')


def _parse_formals(formals):
    if isinstance(formals, Symbol):
        return [], formals.name
    if isinstance(formals, list):
        for f in formals:
            if not isinstance(f, Symbol):
                raise SchemeError("formals must be symbols")
        return [f.name for f in formals], None
    if isinstance(formals, Pair):
        fixed = []
        p = formals
        while isinstance(p, Pair):
            if not isinstance(p.car, Symbol):
                raise SchemeError("formals must be symbols")
            fixed.append(p.car.name)
            p = p.cdr
        if not isinstance(p, Symbol):
            raise SchemeError("rest param must be a symbol")
        return fixed, p.name
    raise SchemeError("invalid formals")


def _parse_formals_from_list(formals_list):
    if len(formals_list) == 0:
        return [], None
    if len(formals_list) == 1 and isinstance(formals_list[0], Symbol):
        return [], formals_list[0].name
    for f in formals_list:
        if not isinstance(f, Symbol):
            raise SchemeError("formals must be symbols")
    return [f.name for f in formals_list], None