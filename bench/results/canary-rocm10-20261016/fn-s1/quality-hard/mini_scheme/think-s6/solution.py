"""Scheme interpreter for a small, precisely specified subset."""
import sys

try:
    sys.set_int_max_str_digits(0)
except (AttributeError, ValueError):
    pass

sys.setrecursionlimit(500000)


# ==================== Data Types ====================

class SchemeError(Exception):
    def __init__(self, message='', output=''):
        super().__init__(message)
        self.output = output


_symbol_table = {}


class _Sym:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name
    def __repr__(self):
        return f"Sym({self.name})"


def Symbol(name):
    s = _symbol_table.get(name)
    if s is None:
        s = _Sym(name)
        _symbol_table[name] = s
    return s


class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr


class _NilType:
    def __repr__(self):
        return "()"
NIL = _NilType()


class _UnspecifiedType:
    def __repr__(self):
        return "UNSPEC"
UNSPECIFIED = _UnspecifiedType()


class _UninitType:
    pass
UNINIT = _UninitType()


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


# ==================== Output ====================

class Output:
    def __init__(self):
        self.parts = []
    def write(self, s):
        self.parts.append(s)
    def get(self):
        return ''.join(self.parts)


# ==================== Reader ====================

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
            tokens.append(('(', None))
            i += 1
        elif c == ')':
            tokens.append((')', None))
            i += 1
        elif c == "'":
            tokens.append(("'", None))
            i += 1
        elif c == '"':
            i += 1
            buf = []
            while i < n and source[i] != '"':
                if source[i] == '\\':
                    i += 1
                    if i >= n:
                        raise SchemeError("unterminated string escape")
                    ch = source[i]
                    if ch == '"': buf.append('"')
                    elif ch == '\\': buf.append('\\')
                    elif ch == 'n': buf.append('\n')
                    else: raise SchemeError("bad string escape")
                    i += 1
                else:
                    buf.append(source[i])
                    i += 1
            if i >= n:
                raise SchemeError("unterminated string")
            i += 1
            tokens.append(('STRING', ''.join(buf)))
        else:
            start = i
            while i < n and source[i] not in ' \t\n\r()";\'':
                i += 1
            tokens.append(('ATOM', source[start:i]))
    return tokens


def _is_int_token(s):
    if not s:
        return False
    i = 0
    if s[0] in '+-':
        i = 1
    if i >= len(s):
        return False
    while i < len(s):
        if s[i] < '0' or s[i] > '9':
            return False
        i += 1
    return True


def _parse_atom(text):
    if text == '#t':
        return True
    if text == '#f':
        return False
    if text.startswith('#'):
        raise SchemeError(f"unknown # literal: {text}")
    if _is_int_token(text):
        return int(text)
    return Symbol(text)


def _make_proper_list(elems):
    result = NIL
    for e in reversed(elems):
        result = Pair(e, result)
    return result


def _parse_list(tokens, pos):
    elements = []
    while True:
        if pos[0] >= len(tokens):
            raise SchemeError("unbalanced (")
        tt, tv = tokens[pos[0]]
        if tt == ')':
            pos[0] += 1
            return _make_proper_list(elements)
        if tt == 'ATOM' and tv == '.':
            pos[0] += 1
            if len(elements) == 0:
                raise SchemeError("dot with no preceding element")
            cdr = _parse_datum(tokens, pos)
            if pos[0] >= len(tokens) or tokens[pos[0]][0] != ')':
                raise SchemeError("expected ) after dotted pair")
            pos[0] += 1
            result = cdr
            for e in reversed(elements):
                result = Pair(e, result)
            return result
        elements.append(_parse_datum(tokens, pos))


def _parse_datum(tokens, pos):
    if pos[0] >= len(tokens):
        raise SchemeError("unexpected end of input")
    tt, tv = tokens[pos[0]]
    if tt == '(':
        pos[0] += 1
        return _parse_list(tokens, pos)
    elif tt == ')':
        raise SchemeError("unexpected )")
    elif tt == "'":
        pos[0] += 1
        d = _parse_datum(tokens, pos)
        return Pair(Symbol('quote'), Pair(d, NIL))
    elif tt == 'STRING':
        pos[0] += 1
        return tv
    elif tt == 'ATOM':
        pos[0] += 1
        return _parse_atom(tv)
    raise SchemeError("unexpected token")


def read_all(source):
    tokens = _tokenize(source)
    pos = [0]
    forms = []
    while pos[0] < len(tokens):
        forms.append(_parse_datum(tokens, pos))
    return forms


# ==================== Environment ====================

class Frame:
    __slots__ = ('bindings', 'parent')
    def __init__(self, bindings=None, parent=None):
        self.bindings = bindings if bindings is not None else {}
        self.parent = parent

    def lookup(self, name):
        f = self
        while f is not None:
            if name in f.bindings:
                v = f.bindings[name]
                if v is UNINIT:
                    raise SchemeError(f"uninitialized variable: {name}")
                return v
            f = f.parent
        raise SchemeError(f"unbound variable: {name}")

    def set(self, name, value):
        f = self
        while f is not None:
            if name in f.bindings:
                f.bindings[name] = value
                return
            f = f.parent
        raise SchemeError(f"set!: unbound variable: {name}")

    def define(self, name, value):
        self.bindings[name] = value


# ==================== Helpers ====================

def is_true(x):
    return x is not False

def is_procedure(x):
    return isinstance(x, (Closure, Builtin))

def is_proper_list(x):
    while isinstance(x, Pair):
        x = x.cdr
    return x is NIL

def proper_list_to_py(x):
    result = []
    while isinstance(x, Pair):
        result.append(x.car)
        x = x.cdr
    if x is not NIL:
        raise SchemeError("not a proper list")
    return result

def list_to_scheme(lst):
    result = NIL
    for item in reversed(lst):
        result = Pair(item, result)
    return result


# ==================== Display / Write ====================

def display_repr(x):
    if isinstance(x, bool):
        return '#t' if x else '#f'
    if isinstance(x, int):
        return _int_to_str(x)
    if isinstance(x, str):
        return x
    if isinstance(x, _Sym):
        return x.name
    if x is NIL:
        return '()'
    if isinstance(x, Pair):
        parts = []
        cur = x
        while isinstance(cur, Pair):
            parts.append(display_repr(cur.car))
            cur = cur.cdr
        if cur is NIL:
            return '(' + ' '.join(parts) + ')'
        return '(' + ' '.join(parts) + ' . ' + display_repr(cur) + ')'
    if isinstance(x, (Closure, Builtin)):
        return '#<procedure>'
    if x is UNSPECIFIED:
        return ''
    return str(x)


def write_repr(x):
    if isinstance(x, str):
        esc = x.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        return '"' + esc + '"'
    if isinstance(x, Pair):
        parts = []
        cur = x
        while isinstance(cur, Pair):
            parts.append(write_repr(cur.car))
            cur = cur.cdr
        if cur is NIL:
            return '(' + ' '.join(parts) + ')'
        return '(' + ' '.join(parts) + ' . ' + write_repr(cur) + ')'
    return display_repr(x)


def _int_to_str(n, radix=10):
    if n == 0:
        return '0'
    negative = n < 0
    n = abs(n)
    digits = '0123456789abcdef'
    parts = []
    while n > 0:
        parts.append(digits[n % radix])
        n //= radix
    if negative:
        parts.append('-')
    return ''.join(reversed(parts))


# ==================== Evaluator ====================

def eval_expr(expr, env):
    result = eval_tail(expr, env)
    while isinstance(result, TailCall):
        result = apply_proc(result.proc, result.args)
    return result


def eval_tail(expr, env):
    if isinstance(expr, bool):
        return expr
    if isinstance(expr, int):
        return expr
    if isinstance(expr, str):
        return expr
    if expr is NIL:
        raise SchemeError("cannot evaluate ()")
    if isinstance(expr, _Sym):
        return env.lookup(expr.name)
    if not isinstance(expr, Pair):
        raise SchemeError("cannot evaluate")

    head = expr.car
    if isinstance(head, _Sym):
        nm = head.name
        if nm == 'quote':
            return _ev_quote(expr, env)
        if nm == 'if':
            return _ev_if(expr, env)
        if nm == 'lambda':
            return _ev_lambda(expr, env)
        if nm == 'define':
            return _ev_define(expr, env)
        if nm == 'set!':
            return _ev_set(expr, env)
        if nm == 'begin':
            return _ev_begin(expr, env)
        if nm == 'cond':
            return _ev_cond(expr, env)
        if nm == 'and':
            return _ev_and(expr, env)
        if nm == 'or':
            return _ev_or(expr, env)
        if nm == 'let':
            return _ev_let(expr, env)
        if nm == 'let*':
            return _ev_letstar(expr, env)
        if nm == 'letrec':
            return _ev_letrec(expr, env)
        if nm == 'apply':
            return _ev_apply(expr, env)

    return _ev_application(expr, env)


def apply_proc(proc, args):
    if isinstance(proc, Closure):
        frame = _make_call_env(proc, args)
        return eval_body(proc.body, frame)
    if isinstance(proc, Builtin):
        return proc.func(args)
    raise SchemeError("not a procedure")


def _make_call_env(closure, args):
    formals = closure.formals
    frame = Frame({}, closure.env)
    if isinstance(formals, _Sym):
        frame.bindings[formals.name] = list_to_scheme(args)
    elif isinstance(formals, Pair):
        required = []
        cur = formals
        while isinstance(cur, Pair):
            if not isinstance(cur.car, _Sym):
                raise SchemeError("malformed lambda formals")
            required.append(cur.car)
            cur = cur.cdr
        if cur is NIL:
            if len(args) != len(required):
                raise SchemeError("wrong number of arguments")
            for v, a in zip(required, args):
                frame.bindings[v.name] = a
        elif isinstance(cur, _Sym):
            if len(args) < len(required):
                raise SchemeError("too few arguments")
            for v, a in zip(required, args[:len(required)]):
                frame.bindings[v.name] = a
            frame.bindings[cur.name] = list_to_scheme(args[len(required):])
        else:
            raise SchemeError("malformed lambda formals")
    else:
        raise SchemeError("malformed lambda formals")
    return frame


def eval_body(body, env):
    """Evaluate body forms with letrec* semantics for internal defines."""
    names = []
    for form in body:
        if isinstance(form, Pair) and isinstance(form.car, _Sym) and form.car.name == 'define':
            if isinstance(form.cdr, Pair):
                target = form.cdr.car
                if isinstance(target, _Sym):
                    names.append(target.name)
                elif isinstance(target, Pair) and isinstance(target.car, _Sym):
                    names.append(target.car.name)
    if names:
        frame = Frame({}, env)
        for n in names:
            frame.bindings[n] = UNINIT
    else:
        frame = env
    for form in body[:-1]:
        eval_expr(form, frame)
    return eval_tail(body[-1], frame)


# ==================== Special Forms ====================

def _ev_quote(expr, env):
    if not isinstance(expr.cdr, Pair) or expr.cdr.cdr is not NIL:
        raise SchemeError("malformed quote")
    return expr.cdr.car


def _ev_if(expr, env):
    args = _safe_args(expr, 2, 3, "if")
    test_val = eval_expr(args[0], env)
    if is_true(test_val):
        return eval_tail(args[1], env)
    if len(args) == 3:
        return eval_tail(args[2], env)
    return UNSPECIFIED


def _ev_lambda(expr, env):
    if not isinstance(expr.cdr, Pair):
        raise SchemeError("malformed lambda")
    formals = expr.cdr.car
    body = _rest_to_body(expr.cdr.cdr)
    return Closure(formals, body, env)


def _ev_define(expr, env):
    if not isinstance(expr.cdr, Pair):
        raise SchemeError("malformed define")
    target = expr.cdr.car
    rest = expr.cdr.cdr
    if isinstance(target, _Sym):
        if not isinstance(rest, Pair):
            raise SchemeError("malformed define")
        val = eval_expr(rest.car, env)
        env.define(target.name, val)
        return UNSPECIFIED
    elif isinstance(target, Pair):
        fname = target.car
        if not isinstance(fname, _Sym):
            raise SchemeError("malformed define")
        formals = target.cdr
        body = _rest_to_body(rest)
        closure = Closure(formals, body, env)
        env.define(fname.name, closure)
        return UNSPECIFIED
    raise SchemeError("malformed define")


def _ev_set(expr, env):
    if not isinstance(expr.cdr, Pair):
        raise SchemeError("malformed set!")
    var = expr.cdr.car
    if not isinstance(var, _Sym):
        raise SchemeError("set!: not a symbol")
    if not isinstance(expr.cdr.cdr, Pair):
        raise SchemeError("malformed set!")
    val = eval_expr(expr.cdr.cdr.car, env)
    env.set(var.name, val)
    return UNSPECIFIED


def _ev_begin(expr, env):
    forms = _rest_to_body(expr.cdr)
    for form in forms[:-1]:
        eval_expr(form, env)
    return eval_tail(forms[-1], env)


def _ev_cond(expr, env):
    clauses = _safe_args(expr, 1, None, "cond")
    for i, clause in enumerate(clauses):
        if not isinstance(clause, Pair):
            raise SchemeError("malformed cond clause")
        test = clause.car
        body = _rest_to_body_opt(clause.cdr)
        if isinstance(test, _Sym) and test.name == 'else':
            if i != len(clauses) - 1:
                raise SchemeError("else must be last cond clause")
            if not body:
                return UNSPECIFIED
            for f in body[:-1]:
                eval_expr(f, env)
            return eval_tail(body[-1], env)
        tv = eval_expr(test, env)
        if is_true(tv):
            if not body:
                return tv
            for f in body[:-1]:
                eval_expr(f, env)
            return eval_tail(body[-1], env)
    return UNSPECIFIED


def _ev_and(expr, env):
    exprs = _rest_to_body_opt(expr.cdr)
    if not exprs:
        return True
    for e in exprs[:-1]:
        v = eval_expr(e, env)
        if not is_true(v):
            return False
    return eval_tail(exprs[-1], env)


def _ev_or(expr, env):
    exprs = _rest_to_body_opt(expr.cdr)
    if not exprs:
        return False
    for e in exprs[:-1]:
        v = eval_expr(e, env)
        if is_true(v):
            return v
    return eval_tail(exprs[-1], env)


def _ev_let(expr, env):
    if not isinstance(expr.cdr, Pair):
        raise SchemeError("malformed let")
    first = expr.cdr.car
    if isinstance(first, _Sym):
        return _ev_named_let(expr, env)
    return _ev_regular_let(expr, env)


def _ev_regular_let(expr, env):
    bindings_form = expr.cdr.car
    body = _rest_to_body(expr.cdr.cdr)
    bindings = _parse_bindings(bindings_form)
    vals = [eval_expr(init, env) for _, init in bindings]
    frame = Frame({}, env)
    for (var, _), v in zip(bindings, vals):
        frame.bindings[var.name] = v
    return eval_body(body, frame)


def _ev_named_let(expr, env):
    name = expr.cdr.car.name
    if not isinstance(expr.cdr.cdr, Pair):
        raise SchemeError("malformed named let")
    bindings_form = expr.cdr.cdr.car
    body = _rest_to_body(expr.cdr.cdr.cdr)
    bindings = _parse_bindings(bindings_form)
    init_vals = [eval_expr(init, env) for _, init in bindings]
    vars_ = [var for var, _ in bindings]
    frame = Frame({}, env)
    formals = list_to_scheme(vars_)
    proc = Closure(formals, body, frame)
    frame.bindings[name] = proc
    return TailCall(proc, init_vals)


def _ev_letstar(expr, env):
    if not isinstance(expr.cdr, Pair):
        raise SchemeError("malformed let*")
    bindings_form = expr.cdr.car
    body = _rest_to_body(expr.cdr.cdr)
    bindings = _parse_bindings(bindings_form)
    frame = Frame({}, env)
    for var, init in bindings:
        val = eval_expr(init, frame)
        frame.bindings[var.name] = val
    return eval_body(body, frame)


def _ev_letrec(expr, env):
    if not isinstance(expr.cdr, Pair):
        raise SchemeError("malformed letrec")
    bindings_form = expr.cdr.car
    body = _rest_to_body(expr.cdr.cdr)
    bindings = _parse_bindings(bindings_form)
    frame = Frame({}, env)
    for var, _ in bindings:
        frame.bindings[var.name] = UNINIT
    for var, init in bindings:
        val = eval_expr(init, frame)
        frame.bindings[var.name] = val
    return eval_body(body, frame)


def _ev_apply(expr, env):
    args = _safe_args(expr, 2, None, "apply")
    vals = [eval_expr(a, env) for a in args]
    f = vals[0]
    lst = vals[-1]
    if not is_proper_list(lst):
        raise SchemeError("apply: last argument not a proper list")
    final_args = vals[1:-1] + proper_list_to_py(lst)
    if not is_procedure(f):
        raise SchemeError("apply: not a procedure")
    return TailCall(f, final_args)


def _ev_application(expr, env):
    proc = eval_expr(expr.car, env)
    args = []
    cur = expr.cdr
    while isinstance(cur, Pair):
        args.append(eval_expr(cur.car, env))
        cur = cur.cdr
    if cur is not NIL:
        raise SchemeError("dotted form used as application")
    if not is_procedure(proc):
        raise SchemeError("not a procedure")
    return TailCall(proc, args)


# ==================== Parsing Helpers ====================

def _safe_args(expr, lo, hi, name):
    try:
        args = proper_list_to_py(expr.cdr)
    except SchemeError:
        raise SchemeError(f"malformed {name}")
    if len(args) < lo:
        raise SchemeError(f"malformed {name}")
    if hi is not None and len(args) > hi:
        raise SchemeError(f"malformed {name}")
    return args


def _rest_to_body(rest):
    """Parse a non-empty body from a list."""
    if not isinstance(rest, Pair):
        raise SchemeError("empty body")
    body = proper_list_to_py(rest)
    if not body:
        raise SchemeError("empty body")
    return body


def _rest_to_body_opt(rest):
    """Parse a possibly-empty body from a list."""
    if rest is NIL:
        return []
    if not isinstance(rest, Pair):
        raise SchemeError("malformed body")
    return proper_list_to_py(rest)


def _parse_bindings(bindings_form):
    """Parse ((var init) ...) into [(var, init), ...]."""
    if bindings_form is NIL:
        return []
    if not isinstance(bindings_form, Pair):
        raise SchemeError("malformed bindings")
    items = proper_list_to_py(bindings_form)
    result = []
    for item in items:
        if not isinstance(item, Pair):
            raise SchemeError("malformed binding")
        var = item.car
        if not isinstance(var, _Sym):
            raise SchemeError("malformed binding: not a symbol")
        if not isinstance(item.cdr, Pair):
            raise SchemeError("malformed binding: missing init")
        if item.cdr.cdr is not NIL:
            raise SchemeError("malformed binding: too many elements")
        result.append((var, item.cdr.car))
    return result


# ==================== Builtins ====================

def _make_global_env(output):
    env = Frame({})

    def reg(name, func):
        env.bindings[name] = Builtin(name, func)

    # --- Numbers ---
    def b_plus(args):
        s = 0
        for a in args:
            _check_int(a, '+')
            s += a
        return s

    def b_times(args):
        p = 1
        for a in args:
            _check_int(a, '*')
            p *= a
        return p

    def b_minus(args):
        if len(args) < 1:
            raise SchemeError("-: at least 1 argument")
        _check_int(args[0], '-')
        if len(args) == 1:
            return -args[0]
        r = args[0]
        for a in args[1:]:
            _check_int(a, '-')
            r -= a
        return r

    def b_quotient(args):
        if len(args) != 2:
            raise SchemeError("quotient: 2 arguments required")
        a, b = args
        _check_int(a, 'quotient')
        _check_int(b, 'quotient')
        if b == 0:
            raise SchemeError("quotient: division by zero")
        q = abs(a) // abs(b)
        if (a < 0) != (b < 0):
            q = -q
        return q

    def b_remainder(args):
        if len(args) != 2:
            raise SchemeError("remainder: 2 arguments required")
        a, b = args
        _check_int(a, 'remainder')
        _check_int(b, 'remainder')
        if b == 0:
            raise SchemeError("remainder: division by zero")
        return a - _trunc_div(a, b) * b

    def b_modulo(args):
        if len(args) != 2:
            raise SchemeError("modulo: 2 arguments required")
        a, b = args
        _check_int(a, 'modulo')
        _check_int(b, 'modulo')
        if b == 0:
            raise SchemeError("modulo: division by zero")
        return a - (a // b) * b

    def _trunc_div(a, b):
        q = abs(a) // abs(b)
        if (a < 0) != (b < 0):
            q = -q
        return q

    def _make_cmp(op):
        def f(args):
            if len(args) < 1:
                raise SchemeError(f"{op}: at least 1 argument")
            for a in args:
                _check_int(a, op)
            for i in range(len(args) - 1):
                if not op(args[i], args[i+1]):
                    return False
            return True
        return f

    def b_num2str(args):
        if len(args) < 1 or len(args) > 2:
            raise SchemeError("number->string: 1 or 2 arguments")
        _check_int(args[0], 'number->string')
        radix = 10
        if len(args) == 2:
            _check_int(args[1], 'number->string')
            radix = args[1]
            if radix not in (2, 8, 10, 16):
                raise SchemeError("number->string: invalid radix")
        return _int_to_str(args[0], radix)

    reg('+', b_plus)
    reg('*', b_times)
    reg('-', b_minus)
    reg('quotient', b_quotient)
    reg('remainder', b_remainder)
    reg('modulo', b_modulo)
    reg('=', _make_cmp(lambda a, b: a == b))
    reg('<', _make_cmp(lambda a, b: a < b))
    reg('>', _make_cmp(lambda a, b: a > b))
    reg('<=', _make_cmp(lambda a, b: a <= b))
    reg('>=', _make_cmp(lambda a, b: a >= b))
    reg('number->string', b_num2str)

    # --- Lists and Pairs ---
    def b_cons(args):
        if len(args) != 2:
            raise SchemeError("cons: 2 arguments")
        return Pair(args[0], args[1])

    def b_car(args):
        if len(args) != 1:
            raise SchemeError("car: 1 argument")
        if not isinstance(args[0], Pair):
            raise SchemeError("car: not a pair")
        return args[0].car

    def b_cdr(args):
        if len(args) != 1:
            raise SchemeError("cdr: 1 argument")
        if not isinstance(args[0], Pair):
            raise SchemeError("cdr: not a pair")
        return args[0].cdr

    def b_list(args):
        return list_to_scheme(args)

    def b_null(args):
        if len(args) != 1:
            raise SchemeError("null?: 1 argument")
        return args[0] is NIL

    def b_pair(args):
        if len(args) != 1:
            raise SchemeError("pair?: 1 argument")
        return isinstance(args[0], Pair)

    def b_listp(args):
        if len(args) != 1:
            raise SchemeError("list?: 1 argument")
        return is_proper_list(args[0])

    def b_length(args):
        if len(args) != 1:
            raise SchemeError("length: 1 argument")
        x = args[0]
        n = 0
        while isinstance(x, Pair):
            n += 1
            x = x.cdr
        if x is not NIL:
            raise SchemeError("length: not a proper list")
        return n

    def b_append(args):
        if len(args) == 0:
            return NIL
        if len(args) == 1:
            return args[0]
        for i in range(len(args) - 1):
            if not is_proper_list(args[i]):
                raise SchemeError("append: not a proper list")
        result = args[-1]
        for i in range(len(args) - 2, -1, -1):
            elems = []
            cur = args[i]
            while isinstance(cur, Pair):
                elems.append(cur.car)
                cur = cur.cdr
            for e in reversed(elems):
                result = Pair(e, result)
        return result

    def b_reverse(args):
        if len(args) != 1:
            raise SchemeError("reverse: 1 argument")
        if not is_proper_list(args[0]):
            raise SchemeError("reverse: not a proper list")
        result = NIL
        cur = args[0]
        while isinstance(cur, Pair):
            result = Pair(cur.car, result)
            cur = cur.cdr
        return result

    def b_apply_builtin(args):
        if len(args) < 2:
            raise SchemeError("apply: at least 2 arguments")
        f = args[0]
        lst = args[-1]
        if not is_proper_list(lst):
            raise SchemeError("apply: last argument not a proper list")
        final_args = list(args[1:-1]) + proper_list_to_py(lst)
        if not is_procedure(f):
            raise SchemeError("apply: not a procedure")
        result = apply_proc(f, final_args)
        while isinstance(result, TailCall):
            result = apply_proc(result.proc, result.args)
        return result

    reg('cons', b_cons)
    reg('car', b_car)
    reg('cdr', b_cdr)
    reg('list', b_list)
    reg('null?', b_null)
    reg('pair?', b_pair)
    reg('list?', b_listp)
    reg('length', b_length)
    reg('append', b_append)
    reg('reverse', b_reverse)
    reg('apply', b_apply_builtin)

    # --- Equality and Predicates ---
    def b_eq(args):
        if len(args) != 2:
            raise SchemeError("eq?: 2 arguments")
        return _scheme_eq(args[0], args[1])

    def b_equal(args):
        if len(args) != 2:
            raise SchemeError("equal?: 2 arguments")
        return _scheme_equal(args[0], args[1])

    def b_not(args):
        if len(args) != 1:
            raise SchemeError("not: 1 argument")
        return args[0] is False

    def b_number(args):
        if len(args) != 1:
            raise SchemeError("number?: 1 argument")
        return isinstance(args[0], int) and not isinstance(args[0], bool)

    def b_symbol(args):
        if len(args) != 1:
            raise SchemeError("symbol?: 1 argument")
        return isinstance(args[0], _Sym)

    def b_string(args):
        if len(args) != 1:
            raise SchemeError("string?: 1 argument")
        return isinstance(args[0], str)

    def b_procedure(args):
        if len(args) != 1:
            raise SchemeError("procedure?: 1 argument")
        return is_procedure(args[0])

    def b_str_append(args):
        for a in args:
            if not isinstance(a, str):
                raise SchemeError("string-append: not a string")
        return ''.join(args)

    reg('eq?', b_eq)
    reg('equal?', b_equal)
    reg('not', b_not)
    reg('number?', b_number)
    reg('symbol?', b_symbol)
    reg('string?', b_string)
    reg('procedure?', b_procedure)
    reg('string-append', b_str_append)

    # --- Output and Errors ---
    def b_display(args):
        if len(args) != 1:
            raise SchemeError("display: 1 argument")
        output.write(display_repr(args[0]))
        return UNSPECIFIED

    def b_newline(args):
        if len(args) != 0:
            raise SchemeError("newline: 0 arguments")
        output.write('\n')
        return UNSPECIFIED

    def b_error(args):
        if len(args) < 1:
            raise SchemeError("error: at least 1 argument")
        msg = args[0]
        if not isinstance(msg, str):
            raise SchemeError("error: first argument must be a string")
        full = msg
        for irr in args[1:]:
            full += ' ' + write_repr(irr)
        raise SchemeError(full)

    reg('display', b_display)
    reg('newline', b_newline)
    reg('error', b_error)

    return env


def _check_int(x, name):
    if isinstance(x, bool) or not isinstance(x, int):
        raise SchemeError(f"{name}: expected integer")


def _scheme_eq(a, b):
    if a is b:
        return True
    if isinstance(a, bool) and isinstance(b, bool):
        return a is b
    if isinstance(a, bool) or isinstance(b, bool):
        return False
    if isinstance(a, int) and isinstance(b, int):
        return a == b
    if isinstance(a, _Sym) and isinstance(b, _Sym):
        return a is b
    if a is NIL and b is NIL:
        return True
    return False


def _scheme_equal(a, b):
    while True:
        if a is b:
            return True
        if isinstance(a, bool):
            return isinstance(b, bool) and a is b
        if isinstance(b, bool):
            return False
        if isinstance(a, int) and isinstance(b, int):
            return a == b
        if isinstance(a, str) and isinstance(b, str):
            return a == b
        if isinstance(a, _Sym) and isinstance(b, _Sym):
            return a is b
        if a is NIL and b is NIL:
            return True
        if isinstance(a, Pair) and isinstance(b, Pair):
            if not _scheme_equal(a.car, b.car):
                return False
            a = a.cdr
            b = b.cdr
            continue
        return False


# ==================== Main Entry Point ====================

def run(source):
    output = Output()
    try:
        forms = read_all(source)
        env = _make_global_env(output)
        for form in forms:
            eval_expr(form, env)
    except SchemeError as e:
        e.output = output.get()
        raise
    except RecursionError:
        raise SchemeError("stack overflow", output.get())
    except Exception as e:
        raise SchemeError(str(e), output.get())
    return output.get()
