import sys

try:
    sys.set_int_max_str_digits(0)
except (AttributeError, ValueError):
    pass


class SchemeError(Exception):
    def __init__(self, msg='', output=''):
        super().__init__(msg)
        self.output = output


# ---------- Data types ----------

class Symbol:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name
    def __eq__(self, other):
        return isinstance(other, Symbol) and self.name == other.name
    def __hash__(self):
        return hash(('sym', self.name))
    def __repr__(self):
        return f'Symbol({self.name!r})'


class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr
    def __repr__(self):
        return f'Pair({self.car!r}, {self.cdr!r})'


class _EmptyList:
    _inst = None
    def __new__(cls):
        if cls._inst is None:
            cls._inst = super().__new__(cls)
        return cls._inst
    def __repr__(self):
        return '()'

EMPTY = _EmptyList()


class _Unspecified:
    _inst = None
    def __new__(cls):
        if cls._inst is None:
            cls._inst = super().__new__(cls)
        return cls._inst
    def __repr__(self):
        return '#<unspecified>'

UNSPECIFIED = _Unspecified()


class _Uninitialized:
    _inst = None
    def __new__(cls):
        if cls._inst is None:
            cls._inst = super().__new__(cls)
        return cls._inst
    def __repr__(self):
        return '#<uninitialized>'

UNINITIALIZED = _Uninitialized()


class Closure:
    __slots__ = ('formals', 'body', 'env', 'variadic', 'param', 'fixed_params', 'rest_param')
    def __init__(self, formals, body, env):
        self.body = body
        self.env = env
        if isinstance(formals, Symbol):
            self.variadic = True
            self.param = formals
            self.fixed_params = []
            self.rest_param = None
        elif _is_proper_list(formals):
            self.variadic = False
            self.fixed_params = _list_from_pair(formals)
            self.rest_param = None
        elif isinstance(formals, Pair):
            self.variadic = False
            elems = []
            p = formals
            while isinstance(p, Pair):
                elems.append(p.car)
                p = p.cdr
            self.fixed_params = elems
            self.rest_param = p
        else:
            raise SchemeError("lambda: invalid formals")
        for s in self.fixed_params:
            if not isinstance(s, Symbol):
                raise SchemeError("lambda: formals must be symbols")
        if self.rest_param is not None and not isinstance(self.rest_param, Symbol):
            raise SchemeError("lambda: rest param must be a symbol")
        if not self.variadic and not self.fixed_params and self.rest_param is None:
            raise SchemeError("lambda: empty formals not allowed")
    def __repr__(self):
        return '<closure>'


class Builtin:
    __slots__ = ('name', 'func')
    def __init__(self, name, func):
        self.name = name
        self.func = func
    def __repr__(self):
        return f'<builtin {self.name}>'


# ---------- Reader ----------

def _skip_ws(s, pos):
    n = len(s)
    while pos < n:
        c = s[pos]
        if c in ' \t\n\r':
            pos += 1
        elif c == ';':
            while pos < n and s[pos] != '\n':
                pos += 1
        else:
            break
    return pos


def _is_int_token(tok):
    if not tok:
        return False
    i = 0
    if tok[0] in '+-':
        i = 1
    if i >= len(tok):
        return False
    for c in tok[i:]:
        if c < '0' or c > '9':
            return False
    return True


def _read_string(s, pos):
    # s[pos] == '"'
    pos += 1
    chars = []
    n = len(s)
    while pos < n:
        c = s[pos]
        if c == '\\':
            if pos + 1 >= n:
                raise SchemeError("syntax error: unterminated string")
            nc = s[pos + 1]
            if nc == '"':
                chars.append('"')
                pos += 2
            elif nc == '\\':
                chars.append('\\')
                pos += 2
            elif nc == 'n':
                chars.append('\n')
                pos += 2
            else:
                raise SchemeError(f"syntax error: invalid escape \\{nc}")
        elif c == '"':
            return (''.join(chars), pos + 1)
        else:
            chars.append(c)
            pos += 1
    raise SchemeError("syntax error: unterminated string")


def _read_atom(s, pos):
    start = pos
    n = len(s)
    while pos < n and s[pos] not in ' \t\n\r()";\'':
        pos += 1
    tok = s[start:pos]
    if not tok:
        raise SchemeError("syntax error: empty token")
    if _is_int_token(tok):
        return (int(tok), pos)
    return (Symbol(tok), pos)


def _read_one(s, pos):
    n = len(s)
    c = s[pos]
    if c == '(':
        return _read_list(s, pos)
    if c == ')':
        raise SchemeError("syntax error: unexpected )")
    if c == "'":
        pos += 1
        pos = _skip_ws(s, pos)
        if pos >= n:
            raise SchemeError("syntax error: ' not followed by datum")
        datum, pos = _read_one(s, pos)
        return (Pair(Symbol('quote'), Pair(datum, EMPTY)), pos)
    if c == '"':
        return _read_string(s, pos)
    if c == '#':
        if s[pos:pos+2] == '#t':
            return (True, pos + 2)
        elif s[pos:pos+2] == '#f':
            return (False, pos + 2)
        else:
            raise SchemeError("syntax error: invalid # token")
    return _read_atom(s, pos)


def _read_list(s, pos):
    # s[pos] == '('
    pos += 1
    n = len(s)
    elements = []
    while True:
        pos = _skip_ws(s, pos)
        if pos >= n:
            raise SchemeError("syntax error: unbalanced (")
        if s[pos] == ')':
            return (_build_list(elements, EMPTY), pos + 1)
        if s[pos] == '.' and (pos + 1 >= n or s[pos + 1] in ' \t\n\r()";\''):
            if not elements:
                raise SchemeError("syntax error: . must be preceded by at least one element")
            pos += 1
            pos = _skip_ws(s, pos)
            if pos >= n:
                raise SchemeError("syntax error: unbalanced (")
            tail, pos = _read_one(s, pos)
            pos = _skip_ws(s, pos)
            if pos >= n or s[pos] != ')':
                raise SchemeError("syntax error: expected ) after dotted pair")
            pos += 1
            return (_build_list(elements, tail), pos)
        else:
            elem, pos = _read_one(s, pos)
            elements.append(elem)


def _build_list(elems, tail):
    if not elems:
        return tail
    result = Pair(elems[-1], tail)
    for e in reversed(elems[:-1]):
        result = Pair(e, result)
    return result


def _read_all(source):
    pos = 0
    n = len(source)
    forms = []
    while True:
        pos = _skip_ws(source, pos)
        if pos >= n:
            break
        form, pos = _read_one(source, pos)
        forms.append(form)
    return forms


# ---------- Environment ----------

class Env:
    __slots__ = ('bindings', 'parent')
    def __init__(self, bindings=None, parent=None):
        self.bindings = bindings if bindings is not None else {}
        self.parent = parent


def _lookup(env, sym):
    e = env
    while e is not None:
        if sym in e.bindings:
            val = e.bindings[sym]
            if val is UNINITIALIZED:
                raise SchemeError(f"uninitialized variable: {sym.name}")
            return val
        e = e.parent
    raise SchemeError(f"unbound variable: {sym.name}")


def _set_bang(env, sym, val):
    e = env
    while e is not None:
        if sym in e.bindings:
            e.bindings[sym] = val
            return
        e = e.parent
    raise SchemeError(f"set!: unbound variable: {sym.name}")


# ---------- Helpers ----------

def _is_proper_list(x):
    p = x
    while p is not EMPTY:
        if not isinstance(p, Pair):
            return False
        p = p.cdr
    return True


def _list_from_pair(p):
    result = []
    while p is not EMPTY:
        result.append(p.car)
        p = p.cdr
    return result


def _pair_to_list(p):
    return _list_from_pair(p)


def _make_pair_list(elems, tail=EMPTY):
    if not elems:
        return tail
    result = Pair(elems[-1], tail)
    for e in reversed(elems[:-1]):
        result = Pair(e, result)
    return result


def _is_number(x):
    return isinstance(x, int) and not isinstance(x, bool)


def _is_true(x):
    return x is not False


def _int_to_str(n):
    try:
        return str(n)
    except (ValueError, OverflowError):
        if n == 0:
            return "0"
        neg = n < 0
        n = abs(n)
        result = []
        while n > 0:
            result.append(str(n % 10))
            n //= 10
        if neg:
            result.append('-')
        result.reverse()
        return ''.join(result)


# ---------- Display / Write ----------

def _display_value(x, out):
    if isinstance(x, bool):
        out.append("#t" if x else "#f")
    elif isinstance(x, int):
        out.append(_int_to_str(x))
    elif isinstance(x, str):
        out.append(x)
    elif isinstance(x, Symbol):
        out.append(x.name)
    elif x is EMPTY:
        out.append("()")
    elif isinstance(x, (Closure, Builtin)):
        out.append("#<procedure>")
    elif x is UNSPECIFIED:
        pass
    elif isinstance(x, Pair):
        out.append("(")
        p = x
        while True:
            _display_value(p.car, out)
            p = p.cdr
            if p is EMPTY:
                break
            elif isinstance(p, Pair):
                out.append(" ")
            else:
                out.append(" . ")
                _display_value(p, out)
                break
        out.append(")")
    else:
        out.append("")


def _write_value(x, out):
    if isinstance(x, bool):
        out.append("#t" if x else "#f")
    elif isinstance(x, int):
        out.append(_int_to_str(x))
    elif isinstance(x, str):
        out.append('"')
        for c in x:
            if c == '"':
                out.append('\\"')
            elif c == '\\':
                out.append('\\\\')
            elif c == '\n':
                out.append('\\n')
            else:
                out.append(c)
        out.append('"')
    elif isinstance(x, Symbol):
        out.append(x.name)
    elif x is EMPTY:
        out.append("()")
    elif isinstance(x, (Closure, Builtin)):
        out.append("#<procedure>")
    elif x is UNSPECIFIED:
        pass
    elif isinstance(x, Pair):
        out.append("(")
        p = x
        while True:
            _write_value(p.car, out)
            p = p.cdr
            if p is EMPTY:
                break
            elif isinstance(p, Pair):
                out.append(" ")
            else:
                out.append(" . ")
                _write_value(p, out)
                break
        out.append(")")
    else:
        out.append("")


# ---------- Builtin implementations ----------

def _builtin_add(args):
    for a in args:
        if not _is_number(a):
            raise SchemeError("+: all arguments must be integers")
    return sum(args)


def _builtin_mul(args):
    for a in args:
        if not _is_number(a):
            raise SchemeError("*: all arguments must be integers")
    r = 1
    for a in args:
        r *= a
    return r


def _builtin_sub(args):
    for a in args:
        if not _is_number(a):
            raise SchemeError("-: all arguments must be integers")
    if len(args) == 1:
        return -args[0]
    r = args[0]
    for a in args[1:]:
        r -= a
    return r


def _builtin_quotient(args):
    for a in args:
        if not _is_number(a):
            raise SchemeError("quotient: arguments must be integers")
    if args[1] == 0:
        raise SchemeError("quotient: division by zero")
    q = abs(args[0]) // abs(args[1])
    if (args[0] < 0) != (args[1] < 0):
        q = -q
    return q


def _builtin_remainder(args):
    for a in args:
        if not _is_number(a):
            raise SchemeError("remainder: arguments must be integers")
    if args[1] == 0:
        raise SchemeError("remainder: division by zero")
    r = abs(args[0]) % abs(args[1])
    if args[0] < 0:
        r = -r
    return r


def _builtin_modulo(args):
    for a in args:
        if not _is_number(a):
            raise SchemeError("modulo: arguments must be integers")
    if args[1] == 0:
        raise SchemeError("modulo: division by zero")
    r = abs(args[0]) % abs(args[1])
    if args[1] < 0:
        r = -r
    return r


def _builtin_compare(op_name, args):
    for a in args:
        if not _is_number(a):
            raise SchemeError(f"{op_name}: all arguments must be integers")
    for i in range(len(args) - 1):
        if op_name == '=':
            if args[i] != args[i + 1]:
                return False
        elif op_name == '<':
            if not (args[i] < args[i + 1]):
                return False
        elif op_name == '>':
            if not (args[i] > args[i + 1]):
                return False
        elif op_name == '<=':
            if not (args[i] <= args[i + 1]):
                return False
        elif op_name == '>=':
            if not (args[i] >= args[i + 1]):
                return False
    return True


def _builtin_number_to_string(args):
    n = args[0]
    if not _is_number(n):
        raise SchemeError("number->string: first argument must be an integer")
    if len(args) == 1:
        return _int_to_str(n)
    radix = args[1]
    if not _is_number(radix) or radix not in (2, 8, 10, 16):
        raise SchemeError("number->string: radix must be 2, 8, 10, or 16")
    if radix == 10:
        return _int_to_str(n)
    if n == 0:
        return "0"
    neg = n < 0
    n = abs(n)
    digits = "0123456789abcdef"
    result = []
    while n > 0:
        result.append(digits[n % radix])
        n //= radix
    if neg:
        result.append('-')
    result.reverse()
    return ''.join(result)


def _builtin_cons(args):
    return Pair(args[0], args[1])


def _builtin_car(args):
    if not isinstance(args[0], Pair):
        raise SchemeError("car: argument must be a pair")
    return args[0].car


def _builtin_cdr(args):
    if not isinstance(args[0], Pair):
        raise SchemeError("cdr: argument must be a pair")
    return args[0].cdr


def _builtin_list(args):
    return _make_pair_list(args)


def _builtin_null_p(args):
    return args[0] is EMPTY


def _builtin_pair_p(args):
    return isinstance(args[0], Pair)


def _builtin_list_p(args):
    return _is_proper_list(args[0])


def _builtin_length(args):
    l = args[0]
    if not _is_proper_list(l):
        raise SchemeError("length: argument must be a proper list")
    n = 0
    p = l
    while p is not EMPTY:
        n += 1
        p = p.cdr
    return n


def _builtin_append(args):
    if not args:
        return EMPTY
    last = args[-1]
    for a in args[:-1]:
        if not _is_proper_list(a):
            raise SchemeError("append: all but last argument must be proper lists")
    if len(args) == 1:
        return last
    elements = []
    for a in args[:-1]:
        p = a
        while p is not EMPTY:
            elements.append(p.car)
            p = p.cdr
    result = last
    for e in reversed(elements):
        result = Pair(e, result)
    return result


def _builtin_reverse(args):
    l = args[0]
    if not _is_proper_list(l):
        raise SchemeError("reverse: argument must be a proper list")
    result = EMPTY
    p = l
    while p is not EMPTY:
        result = Pair(p.car, result)
        p = p.cdr
    return result


def _builtin_eq(args):
    a, b = args
    if isinstance(a, bool) and isinstance(b, bool):
        return a == b
    if _is_number(a) and _is_number(b):
        return a == b
    if isinstance(a, Symbol) and isinstance(b, Symbol):
        return a == b
    if a is EMPTY and b is EMPTY:
        return True
    if a is UNSPECIFIED and b is UNSPECIFIED:
        return True
    if isinstance(a, (Closure, Builtin)) and isinstance(b, (Closure, Builtin)):
        return a is b
    return a is b


def _type_tag(x):
    if isinstance(x, bool):
        return 0
    if isinstance(x, int):
        return 1
    if isinstance(x, str):
        return 2
    if isinstance(x, Symbol):
        return 3
    if x is EMPTY:
        return 4
    if isinstance(x, (Closure, Builtin)):
        return 5
    if x is UNSPECIFIED:
        return 6
    if isinstance(x, Pair):
        return 7
    return 8


def _builtin_equal(args):
    a, b = args
    stack = [(a, b)]
    while stack:
        a, b = stack.pop()
        ta, tb = _type_tag(a), _type_tag(b)
        if ta != tb:
            return False
        if ta == 0:  # bool
            if a != b:
                return False
        elif ta == 1:  # int
            if a != b:
                return False
        elif ta == 2:  # str
            if a != b:
                return False
        elif ta == 3:  # symbol
            if a != b:
                return False
        elif ta == 5:  # procedure
            if a is not b:
                return False
        elif ta == 7:  # pair
            stack.append((a.cdr, b.cdr))
            stack.append((a.car, b.car))
    return True


def _builtin_not(args):
    return args[0] is False


def _builtin_number_p(args):
    return _is_number(args[0])


def _builtin_symbol_p(args):
    return isinstance(args[0], Symbol)


def _builtin_string_p(args):
    return isinstance(args[0], str)


def _builtin_procedure_p(args):
    return isinstance(args[0], (Closure, Builtin))


def _builtin_string_append(args):
    for a in args:
        if not isinstance(a, str):
            raise SchemeError("string-append: all arguments must be strings")
    return ''.join(args)


def _builtin_display(args, out):
    _display_value(args[0], out)
    return UNSPECIFIED


def _builtin_newline(args, out):
    out.append("\n")
    return UNSPECIFIED


def _builtin_error(args, out):
    if not args:
        raise SchemeError("error: requires at least one argument")
    msg = args[0]
    if not isinstance(msg, str):
        raise SchemeError("error: first argument must be a string")
    parts = [msg]
    for irr in args[1:]:
        w = []
        _write_value(irr, w)
        parts.append(" " + ''.join(w))
    raise SchemeError(''.join(parts))


# ---------- Evaluator ----------

SPECIAL_FORMS = frozenset({
    'quote', 'if', 'define', 'set!', 'begin', 'cond',
    'and', 'or', 'let', 'let*', 'letrec', 'lambda'
})


def _eval_t(form, env, out):
    """Evaluate form in tail position. Returns value."""
    while True:
        result = _eval_tail_step(form, env, out)
        if isinstance(result, tuple) and len(result) == 2 and result[0] is _TAIL:
            form, env = result[1], result[2]
        else:
            return result


_TAIL = object()


def _eval_tail_step(form, env, out):
    """One step of tail evaluation. Returns value or (_TAIL, form, env)."""
    if isinstance(form, bool) or isinstance(form, int) or isinstance(form, str):
        return form
    if isinstance(form, Symbol):
        return _lookup(env, form)
    if form is EMPTY:
        raise SchemeError("cannot apply the empty list")
    if form is UNSPECIFIED:
        return UNSPECIFIED
    if not isinstance(form, Pair):
        raise SchemeError(f"invalid form")
    if not _is_proper_list(form):
        raise SchemeError("dotted form cannot be applied")
    head = form.car
    if isinstance(head, Symbol) and head.name in SPECIAL_FORMS:
        return _eval_special(head.name, form, env, out, True)
    # Procedure application
    op = _eval_nt(form.car, env, out)
    args = [_eval_nt(a, env, out) for a in _list_from_pair(form.cdr)]
    return _call_proc_tail(op, args, out)


def _eval_nt(form, env, out):
    """Evaluate form in non-tail position. Returns value."""
    if isinstance(form, bool) or isinstance(form, int) or isinstance(form, str):
        return form
    if isinstance(form, Symbol):
        return _lookup(env, form)
    if form is EMPTY:
        raise SchemeError("cannot apply the empty list")
    if form is UNSPECIFIED:
        return UNSPECIFIED
    if not isinstance(form, Pair):
        raise SchemeError(f"invalid form")
    if not _is_proper_list(form):
        raise SchemeError("dotted form cannot be applied")
    head = form.car
    if isinstance(head, Symbol) and head.name in SPECIAL_FORMS:
        return _eval_special(head.name, form, env, out, False)
    # Procedure application
    op = _eval_nt(form.car, env, out)
    args = [_eval_nt(a, env, out) for a in _list_from_pair(form.cdr)]
    return _call_proc_nt(op, args, out)


def _call_proc_nt(op, args, out):
    if not isinstance(op, (Closure, Builtin)):
        raise SchemeError("attempt to apply non-procedure")
    if isinstance(op, Builtin):
        return op.func(args, out)
    # Closure
    new_env = _make_closure_env(op, args)
    body = op.body
    for f in body[:-1]:
        _eval_nt(f, new_env, out)
    return _eval_t(body[-1], new_env, out)


def _call_proc_tail(op, args, out):
    if not isinstance(op, (Closure, Builtin)):
        raise SchemeError("attempt to apply non-procedure")
    if isinstance(op, Builtin):
        return op.func(args, out)
    # Closure: set up env, eval non-tail body forms, return continuation for last
    new_env = _make_closure_env(op, args)
    body = op.body
    for f in body[:-1]:
        _eval_nt(f, new_env, out)
    return (_TAIL, body[-1], new_env)


def _make_closure_env(closure, args):
    if closure.variadic:
        bindings = {closure.param: _make_pair_list(args)}
    else:
        n_fixed = len(closure.fixed_params)
        if closure.rest_param is None:
            if len(args) != n_fixed:
                raise SchemeError(f"wrong number of arguments: expected {n_fixed}, got {len(args)}")
            bindings = dict(zip(closure.fixed_params, args))
        else:
            if len(args) < n_fixed:
                raise SchemeError(f"wrong number of arguments: expected at least {n_fixed}, got {len(args)}")
            bindings = dict(zip(closure.fixed_params, args[:n_fixed]))
            bindings[closure.rest_param] = _make_pair_list(args[n_fixed:])
    return Env(bindings, closure.env)


def _eval_special(name, form, env, out, tail):
    if name == 'quote':
        rest = form.cdr
        if not isinstance(rest, Pair) or not isinstance(rest.cdr, _EmptyList) and rest.cdr is not EMPTY:
            pass
        if not isinstance(rest, Pair):
            raise SchemeError("quote: missing datum")
        datum = rest.car
        if rest.cdr is not EMPTY:
            raise SchemeError("quote: extra arguments")
        return datum

    elif name == 'if':
        rest = _list_from_pair(form.cdr)
        if len(rest) < 2:
            raise SchemeError("if: requires at least 2 arguments")
        if len(rest) > 3:
            raise SchemeError("if: too many arguments")
        test = _eval_nt(rest[0], env, out)
        if _is_true(test):
            if tail:
                return _eval_t(rest[1], env, out)
            else:
                return _eval_nt(rest[1], env, out)
        else:
            if len(rest) == 3:
                if tail:
                    return _eval_t(rest[2], env, out)
                else:
                    return _eval_nt(rest[2], env, out)
            else:
                return UNSPECIFIED

    elif name == 'define':
        return _eval_define(form, env, out)

    elif name == 'set!':
        rest = _list_from_pair(form.cdr)
        if len(rest) != 2:
            raise SchemeError("set!: requires exactly 2 arguments")
        sym = rest[0]
        if not isinstance(sym, Symbol):
            raise SchemeError("set!: first argument must be a symbol")
        val = _eval_nt(rest[1], env, out)
        _set_bang(env, sym, val)
        return UNSPECIFIED

    elif name == 'begin':
        forms = _list_from_pair(form.cdr)
        if not forms:
            raise SchemeError("begin: requires at least one form")
        for f in forms[:-1]:
            _eval_nt(f, env, out)
        if tail:
            return _eval_t(forms[-1], env, out)
        else:
            return _eval_nt(forms[-1], env, out)

    elif name == 'cond':
        return _eval_cond(form, env, out, tail)

    elif name == 'and':
        return _eval_and(form, env, out, tail)

    elif name == 'or':
        return _eval_or(form, env, out, tail)

    elif name == 'let':
        return _eval_let(form, env, out, tail)

    elif name == 'let*':
        return _eval_let_star(form, env, out, tail)

    elif name == 'letrec':
        return _eval_letrec(form, env, out, tail)

    elif name == 'lambda':
        return _eval_lambda(form, env)

    else:
        raise SchemeError(f"unknown special form: {name}")


def _eval_define(form, env, out):
    rest = _list_from_pair(form.cdr)
    if not rest:
        raise SchemeError("define: missing arguments")
    first = rest[0]
    if isinstance(first, Pair):
        # (define (name . formals) body...)
        if not _is_proper_list(first):
            raise SchemeError("define: invalid procedure definition")
        params = _list_from_pair(first)
        if not params:
            raise SchemeError("define: invalid procedure definition")
        name_sym = params[0]
        if not isinstance(name_sym, Symbol):
            raise SchemeError("define: name must be a symbol")
        formals = _make_pair_list(params[1:]) if len(params) > 1 else Symbol('')
        # Actually, formals is the list of params after name
        if len(params) == 1:
            raise SchemeError("define: procedure needs at least a name")
        formals_list = params[1:]
        # formals can be a proper list, dotted list, or lone symbol
        # In the reader, (define (f a b) body) gives params = [f, a, b]
        # formals = (a b) as a pair
        formals_pair = _make_pair_list(formals_list)
        body = rest[1:]
        if not body:
            raise SchemeError("define: procedure body must be non-empty")
        closure = Closure(formals_pair, body, env)
        env.bindings[name_sym] = closure
        return UNSPECIFIED
    else:
        # (define name expr)
        if not isinstance(first, Symbol):
            raise SchemeError("define: name must be a symbol")
        if len(rest) != 2:
            raise SchemeError("define: requires exactly 2 arguments")
        val = _eval_nt(rest[1], env, out)
        env.bindings[first] = val
        return UNSPECIFIED


def _eval_cond(form, env, out, tail):
    clauses = _list_from_pair(form.cdr)
    if not clauses:
        raise SchemeError("cond: requires at least one clause")
    for i, clause in enumerate(clauses):
        if not isinstance(clause, Pair):
            raise SchemeError("cond: clause must be a list")
        clause_list = _list_from_pair(clause)
        if not clause_list:
            raise SchemeError("cond: clause must be non-empty")
        test = clause_list[0]
        if isinstance(test, Symbol) and test.name == 'else':
            if i != len(clauses) - 1:
                raise SchemeError("cond: else must be the last clause")
            exprs = clause_list[1:]
            if not exprs:
                raise SchemeError("cond: else clause requires at least one expression")
            for e in exprs[:-1]:
                _eval_nt(e, env, out)
            if tail:
                return _eval_t(exprs[-1], env, out)
            else:
                return _eval_nt(exprs[-1], env, out)
        else:
            test_val = _eval_nt(test, env, out)
            if _is_true(test_val):
                exprs = clause_list[1:]
                if not exprs:
                    return test_val
                for e in exprs[:-1]:
                    _eval_nt(e, env, out)
                if tail:
                    return _eval_t(exprs[-1], env, out)
                else:
                    return _eval_nt(exprs[-1], env, out)
    return UNSPECIFIED


def _eval_and(form, env, out, tail):
    exprs = _list_from_pair(form.cdr)
    if not exprs:
        return True
    for i, e in enumerate(exprs):
        if i == len(exprs) - 1 and tail:
            val = _eval_t(e, env, out)
            return val
        val = _eval_nt(e, env, out)
        if val is False:
            return False
    return val


def _eval_or(form, env, out, tail):
    exprs = _list_from_pair(form.cdr)
    if not exprs:
        return False
    for e in exprs:
        if tail:
            val = _eval_t(e, env, out)
        else:
            val = _eval_nt(e, env, out)
        if _is_true(val):
            return val
    return False


def _eval_let(form, env, out, tail):
    rest = _list_from_pair(form.cdr)
    if not rest:
        raise SchemeError("let: missing bindings")
    # Check for named let
    if isinstance(rest[0], Symbol):
        return _eval_named_let(rest, env, out, tail)
    # Regular let
    bindings = rest[0]
    if not isinstance(bindings, Pair) and bindings is not EMPTY:
        raise SchemeError("let: bindings must be a list")
    body = rest[1:]
    if not body:
        raise SchemeError("let: body must be non-empty")
    # Evaluate inits in outer scope
    vals = []
    if bindings is not EMPTY:
        for b in _list_from_pair(bindings):
            if not isinstance(b, Pair):
                raise SchemeError("let: invalid binding")
            b_list = _list_from_pair(b)
            if len(b_list) != 2:
                raise SchemeError("let: binding must have exactly 2 elements")
            v = b_list[0]
            if not isinstance(v, Symbol):
                raise SchemeError("let: binding variable must be a symbol")
            init_val = _eval_nt(b_list[1], env, out)
            vals.append((v, init_val))
    new_env = Env(dict(vals), env)
    return _eval_body(body, new_env, out, tail)


def _eval_let_star(form, env, out, tail):
    rest = _list_from_pair(form.cdr)
    if not rest:
        raise SchemeError("let*: missing bindings")
    bindings = rest[0]
    body = rest[1:]
    if not body:
        raise SchemeError("let*: body must be non-empty")
    cur_env = env
    if bindings is not EMPTY:
        for b in _list_from_pair(bindings):
            if not isinstance(b, Pair):
                raise SchemeError("let*: invalid binding")
            b_list = _list_from_pair(b)
            if len(b_list) != 2:
                raise SchemeError("let*: binding must have exactly 2 elements")
            v = b_list[0]
            if not isinstance(v, Symbol):
                raise SchemeError("let*: binding variable must be a symbol")
            init_val = _eval_nt(b_list[1], cur_env, out)
            cur_env = Env({v: init_val}, cur_env)
    return _eval_body(body, cur_env, out, tail)


def _eval_letrec(form, env, out, tail):
    rest = _list_from_pair(form.cdr)
    if not rest:
        raise SchemeError("letrec: missing bindings")
    bindings = rest[0]
    body = rest[1:]
    if not body:
        raise SchemeError("letrec: body must be non-empty")
    # Pre-bind all variables
    new_env = Env({}, env)
    if bindings is not EMPTY:
        for b in _list_from_pair(bindings):
            if not isinstance(b, Pair):
                raise SchemeError("letrec: invalid binding")
            b_list = _list_from_pair(b)
            if len(b_list) != 2:
                raise SchemeError("letrec: binding must have exactly 2 elements")
            v = b_list[0]
            if not isinstance(v, Symbol):
                raise SchemeError("letrec: binding variable must be a symbol")
            new_env.bindings[v] = UNINITIALIZED
        # Evaluate inits in order
        for b in _list_from_pair(bindings):
            b_list = _list_from_pair(b)
            v = b_list[0]
            val = _eval_nt(b_list[1], new_env, out)
            new_env.bindings[v] = val
    return _eval_body(body, new_env, out, tail)


def _eval_named_let(rest, env, out, tail):
    name_sym = rest[0]
    bindings = rest[1]
    body = rest[2:]
    if not body:
        raise SchemeError("named let: body must be non-empty")
    # Parse bindings
    param_syms = []
    init_forms = []
    if bindings is not EMPTY:
        for b in _list_from_pair(bindings):
            if not isinstance(b, Pair):
                raise SchemeError("named let: invalid binding")
            b_list = _list_from_pair(b)
            if len(b_list) != 2:
                raise SchemeError("named let: binding must have exactly 2 elements")
            v = b_list[0]
            if not isinstance(v, Symbol):
                raise SchemeError("named let: binding variable must be a symbol")
            param_syms.append(v)
            init_forms.append(b_list[1])
    # Evaluate inits in outer scope
    init_vals = [_eval_nt(f, env, out) for f in init_forms]
    # Create closure
    formals_pair = _make_pair_list(param_syms) if param_syms else EMPTY
    closure = Closure(formals_pair, body, None)
    new_env = Env({name_sym: closure}, env)
    closure.env = new_env
    # Call the closure
    if tail:
        return _call_proc_tail(closure, init_vals, out)
    else:
        return _call_proc_nt(closure, init_vals, out)


def _eval_lambda(form, env):
    rest = _list_from_pair(form.cdr)
    if len(rest) < 2:
        raise SchemeError("lambda: requires formals and at least one body form")
    formals = rest[0]
    body = rest[1:]
    if not body:
        raise SchemeError("lambda: body must be non-empty")
    return Closure(formals, body, env)


def _eval_body(body, env, out, tail):
    """Evaluate a body, handling internal definitions."""
    # Check for top-level define forms
    internal_names = []
    for f in body:
        if isinstance(f, Pair) and _is_proper_list(f):
            head = f.car
            if isinstance(head, Symbol) and head.name == 'define':
                name_sym = _extract_define_name(f)
                if name_sym is not None:
                    internal_names.append(name_sym)
    if internal_names:
        new_env = Env({n: UNINITIALIZED for n in internal_names}, env)
    else:
        new_env = env
    for f in body[:-1]:
        _eval_nt(f, new_env, out)
    if tail:
        return _eval_t(body[-1], new_env, out)
    else:
        return _eval_nt(body[-1], new_env, out)


def _extract_define_name(form):
    """Extract the name symbol from a define form. Returns None if malformed."""
    rest = form.cdr
    if not isinstance(rest, Pair):
        return None
    first = rest.car
    if isinstance(first, Pair):
        # (define (name ...) ...)
        if isinstance(first.car, Symbol):
            return first.car
        return None
    elif isinstance(first, Symbol):
        return first
    return None


# ---------- Apply builtin (special TCO) ----------

def _builtin_apply(args, out):
    if len(args) < 2:
        raise SchemeError("apply: requires at least 2 arguments")
    f = args[0]
    if not isinstance(f, (Closure, Builtin)):
        raise SchemeError("apply: first argument must be a procedure")
    lst = args[-1]
    if not _is_proper_list(lst):
        raise SchemeError("apply: last argument must be a proper list")
    all_args = args[1:-1] + _list_from_pair(lst)
    return f.func(all_args, out) if isinstance(f, Builtin) else None


# ---------- Global environment ----------

def _make_global_env():
    env = Env({})
    builtins = {
        '+': Builtin('+', _builtin_add),
        '*': Builtin('*', _builtin_mul),
        '-': Builtin('-', _builtin_sub),
        'quotient': Builtin('quotient', _builtin_quotient),
        'remainder': Builtin('remainder', _builtin_remainder),
        'modulo': Builtin('modulo', _builtin_modulo),
        '=': Builtin('=', lambda a, o: _builtin_compare('=', a)),
        '<': Builtin('<', lambda a, o: _builtin_compare('<', a)),
        '>': Builtin('>', lambda a, o: _builtin_compare('>', a)),
        '<=': Builtin('<=', lambda a, o: _builtin_compare('<=', a)),
        '>=': Builtin('>=', lambda a, o: _builtin_compare('>=', a)),
        'number->string': Builtin('number->string', _builtin_number_to_string),
        'cons': Builtin('cons', _builtin_cons),
        'car': Builtin('car', _builtin_car),
        'cdr': Builtin('cdr', _builtin_cdr),
        'list': Builtin('list', _builtin_list),
        'null?': Builtin('null?', _builtin_null_p),
        'pair?': Builtin('pair?', _builtin_pair_p),
        'list?': Builtin('list?', _builtin_list_p),
        'length': Builtin('length', _builtin_length),
        'append': Builtin('append', _builtin_append),
        'reverse': Builtin('reverse', _builtin_reverse),
        'apply': Builtin('apply', _builtin_apply),
        'eq?': Builtin('eq?', _builtin_eq),
        'equal?': Builtin('equal?', _builtin_equal),
        'not': Builtin('not', _builtin_not),
        'number?': Builtin('number?', _builtin_number_p),
        'symbol?': Builtin('symbol?', _builtin_symbol_p),
        'string?': Builtin('string?', _builtin_string_p),
        'procedure?': Builtin('procedure?', _builtin_procedure_p),
        'string-append': Builtin('string-append', _builtin_string_append),
        'display': Builtin('display', _builtin_display),
        'newline': Builtin('newline', _builtin_newline),
        'error': Builtin('error', _builtin_error),
    }
    env.bindings.update({Symbol(k): v for k, v in builtins.items()})
    return env


# ---------- Apply TCO handling ----------

# We need to detect when apply is called in tail position.
# The builtin apply object is stored in the global env.
# We'll handle it in _call_proc_tail and _call_proc_nt by checking identity.

# Actually, let's handle apply TCO in _eval_tail_step:
# When the operator evaluates to the apply builtin, we handle it specially.

# Let me restructure: in _eval_tail_step, after evaluating op and args,
# check if op is the apply builtin.

# I'll store a reference to the apply builtin.

_apply_builtin_ref = [None]  # will be set in _make_global_env


def _make_global_env_v2():
    env = _make_global_env()
    _apply_builtin_ref[0] = env.bindings[Symbol('apply')]
    return env


# Override _call_proc_tail to handle apply TCO
def _call_proc_tail_v2(op, args, out):
    if not isinstance(op, (Closure, Builtin)):
        raise SchemeError("attempt to apply non-procedure")
    if isinstance(op, Builtin):
        # Check if it's the apply builtin for TCO
        if _apply_builtin_ref[0] is not None and op is _apply_builtin_ref[0]:
            if len(args) < 2:
                raise SchemeError("apply: requires at least 2 arguments")
            f = args[0]
            if not isinstance(f, (Closure, Builtin)):
                raise SchemeError("apply: first argument must be a procedure")
            lst = args[-1]
            if not _is_proper_list(lst):
                raise SchemeError("apply: last argument must be a proper list")
            all_args = args[1:-1] + _list_from_pair(lst)
            return _call_proc_tail_v2(f, all_args, out)
        return op.func(args, out)
    # Closure
    new_env = _make_closure_env(op, args)
    body = op.body
    for f in body[:-1]:
        _eval_nt(f, new_env, out)
    return (_TAIL, body[-1], new_env)


def _call_proc_nt_v2(op, args, out):
    if not isinstance(op, (Closure, Builtin)):
        raise SchemeError("attempt to apply non-procedure")
    if isinstance(op, Builtin):
        if _apply_builtin_ref[0] is not None and op is _apply_builtin_ref[0]:
            if len(args) < 2:
                raise SchemeError("apply: requires at least 2 arguments")
            f = args[0]
            if not isinstance(f, (Closure, Builtin)):
                raise SchemeError("apply: first argument must be a procedure")
            lst = args[-1]
            if not _is_proper_list(lst):
                raise SchemeError("apply: last argument must be a proper list")
            all_args = args[1:-1] + _list_from_pair(lst)
            return _call_proc_nt_v2(f, all_args, out)
        return op.func(args, out)
    # Closure
    new_env = _make_closure_env(op, args)
    body = op.body
    for f in body[:-1]:
        _eval_nt(f, new_env, out)
    return _eval_t(body[-1], new_env, out)


# Patch the functions to use v2
_call_proc_tail = _call_proc_tail_v2
_call_proc_nt = _call_proc_nt_v2


# ---------- Public API ----------

def run(source):
    out = []
    try:
        forms = _read_all(source)
        env = _make_global_env_v2()
        for form in forms:
            _eval_t(form, env, out)
        return ''.join(out)
    except SchemeError as e:
        e.output = ''.join(out)
        raise
    except RecursionError:
        raise SchemeError("maximum recursion depth exceeded", output=''.join(out))
    except Exception as e:
        raise SchemeError(str(e), output=''.join(out))