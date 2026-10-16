import sys
sys.set_int_max_str_digits(0)
sys.setrecursionlimit(200000)


class SchemeError(Exception):
    def __init__(self, msg, output=''):
        super().__init__(msg)
        self.output = output


# ─── Data Types ───────────────────────────────────────────────────────────────

class Sym:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name

class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr

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

class _EmptyList: pass
class _Unspecified: pass

EMPTY = _EmptyList()
UNDEFINED = _Unspecified()
_UNINITIALIZED = object()

_sym_table = {}
def sym(name):
    if name not in _sym_table:
        _sym_table[name] = Sym(name)
    return _sym_table[name]

def is_num(x):
    return isinstance(x, int) and not isinstance(x, bool)

def is_pair(x):
    return isinstance(x, Pair)

def is_proper_list(x):
    while is_pair(x):
        x = x.cdr
    return x is EMPTY

def is_procedure(x):
    return isinstance(x, (Closure, Builtin))

def make_list(elems):
    r = EMPTY
    for e in reversed(elems):
        r = Pair(e, r)
    return r

def list_to_py(x):
    r = []
    while is_pair(x):
        r.append(x.car)
        x = x.cdr
    return r

def pair_length(x):
    n = 0
    while is_pair(x):
        n += 1
        x = x.cdr
    return n

# ─── Environment ──────────────────────────────────────────────────────────────

class Env:
    __slots__ = ('bindings', 'parent')
    def __init__(self, bindings, parent=None):
        self.bindings = bindings
        self.parent = parent

# ─── Reader ───────────────────────────────────────────────────────────────────

def _tokenize(src):
    toks = []
    i = 0
    n = len(src)
    while i < n:
        c = src[i]
        if c in ' \t\n\r':
            i += 1
        elif c == ';':
            while i < n and src[i] != '\n':
                i += 1
        elif c == '(':
            toks.append(('lp',)); i += 1
        elif c == ')':
            toks.append(('rp',)); i += 1
        elif c == "'":
            toks.append(('qt',)); i += 1
        elif c == '"':
            i += 1
            parts = []
            while i < n:
                if src[i] == '\\':
                    if i + 1 >= n:
                        raise SchemeError("unterminated string escape")
                    e = src[i+1]
                    if e == '"': parts.append('"')
                    elif e == '\\': parts.append('\\')
                    elif e == 'n': parts.append('\n')
                    else: raise SchemeError(f"invalid escape \\{e}")
                    i += 2
                elif src[i] == '"':
                    i += 1; break
                else:
                    parts.append(src[i]); i += 1
            else:
                raise SchemeError("unterminated string")
            toks.append(('str', ''.join(parts)))
        else:
            s = i
            while i < n and src[i] not in ' \t\n\r()";\'':
                i += 1
            toks.append(('at', src[s:i]))
    return toks

def _is_int(s):
    if not s: return False
    st = 0
    if s[0] in '+-': st = 1
    if st >= len(s): return False
    for c in s[st:]:
        if c < '0' or c > '9': return False
    return True

def _read_all(src):
    toks = _tokenize(src)
    pos = [0]
    n = len(toks)

    def peek():
        return toks[pos[0]] if pos[0] < n else None

    def adv():
        t = toks[pos[0]]; pos[0] += 1; return t

    def read_datum():
        t = peek()
        if t is None: raise SchemeError("unexpected end of input")
        if t[0] == 'rp': raise SchemeError("unexpected )")
        adv()
        if t[0] == 'lp': return read_list()
        if t[0] == 'qt':
            d = read_datum()
            return Pair(sym('quote'), Pair(d, EMPTY))
        if t[0] == 'str': return t[1]
        s = t[1]
        if s == '#t': return True
        if s == '#f': return False
        if s.startswith('#'): raise SchemeError(f"invalid token {s}")
        if _is_int(s): return int(s)
        return sym(s)

    def read_list():
        elems = []
        dot = False
        while True:
            t = peek()
            if t is None: raise SchemeError("unbalanced (")
            if t[0] == 'rp':
                adv()
                if dot: raise SchemeError("syntax error")
                if not elems: return EMPTY
                return make_list(elems)
            if t[0] == 'at' and t[1] == '.' and not dot:
                if not elems: raise SchemeError("dot must be preceded by element")
                adv(); dot = True
                d = read_datum()
                t2 = peek()
                if t2 is None or t2[0] != 'rp':
                    raise SchemeError("expected ) after dotted list")
                adv()
                r = d
                for e in reversed(elems):
                    r = Pair(e, r)
                return r
            if dot: raise SchemeError("expected ) after dotted list")
            elems.append(read_datum())

    forms = []
    while pos[0] < n:
        if toks[pos[0]][0] == 'rp':
            raise SchemeError("unbalanced )")
        forms.append(read_datum())
    return forms

# ─── Display / Write ──────────────────────────────────────────────────────────

def _repr(x, write=False):
    if x is EMPTY: return '()'
    if x is UNDEFINED: return ''
    if x is True: return '#t'
    if x is False: return '#f'
    if is_num(x): return str(x)
    if isinstance(x, str):
        if write:
            return '"' + x.replace('\\','\\\\').replace('"','\\"').replace('\n','\\n') + '"'
        return x
    if isinstance(x, Sym): return x.name
    if isinstance(x, (Closure, Builtin)): return '#<procedure>'
    if isinstance(x, Pair):
        parts = []
        p = x
        while is_pair(p):
            parts.append(_repr(p.car, write))
            p = p.cdr
        if p is not EMPTY:
            parts.append('. ' + _repr(p, write))
        return '(' + ' '.join(parts) + ')'
    return str(x)

# ─── Evaluator ────────────────────────────────────────────────────────────────

class _TailCall:
    __slots__ = ('body', 'env')
    def __init__(self, body, env):
        self.body = body
        self.env = env

class _Continue:
    __slots__ = ('form', 'env')
    def __init__(self, form, env):
        self.form = form
        self.env = env

_output = []

def _lookup(env, name):
    e = env
    while e is not None:
        if name in e.bindings:
            v = e.bindings[name]
            if v is _UNINITIALIZED:
                raise SchemeError(f"uninitialized variable: {name}")
            return v
        e = e.parent
    raise SchemeError(f"unbound variable: {name}")

def _parse_formals(f):
    if isinstance(f, Sym):
        return ('variadic', f)
    if is_proper_list(f):
        syms = list_to_py(f)
        for s in syms:
            if not isinstance(s, Sym):
                raise SchemeError("formals must be symbols")
        return ('fixed', syms)
    if is_pair(f):
        named = []
        p = f
        while is_pair(p):
            if not isinstance(p.car, Sym):
                raise SchemeError("formals must be symbols")
            named.append(p.car)
            p = p.cdr
        if not isinstance(p, Sym):
            raise SchemeError("malformed formals")
        return ('dotted', named, p)
    raise SchemeError("malformed formals")

def _make_closure_env(cl, args):
    f = cl.formals
    if f[0] == 'fixed':
        if len(args) != len(f[1]):
            raise SchemeError("wrong number of arguments")
        b = {s.name: v for s, v in zip(f[1], args)}
    elif f[0] == 'dotted':
        named, rest_s = f[1], f[2]
        if len(args) < len(named):
            raise SchemeError("wrong number of arguments")
        b = {s.name: v for s, v in zip(named, args[:len(named)])}
        b[rest_s.name] = make_list(args[len(named):])
    else:
        b = {f[1].name: make_list(args)}
    return Env(b, cl.env)

def _call_proc(proc, args):
    if isinstance(proc, Closure):
        env = _make_closure_env(proc, args)
        return _eval_body(proc.body, env, False)
    else:
        return proc.func(args)

def _is_internal_define(f):
    if not is_pair(f): return False
    if f.cdr is EMPTY: return False
    if not isinstance(f.car, Sym): return False
    if f.car.name != 'define': return False
    r = f.cdr
    if r is EMPTY: return False
    second = r.car
    if isinstance(second, Sym): return True
    if is_pair(second) and is_proper_list(second) and pair_length(second) >= 1:
        return isinstance(second.car, Sym)
    return False

def _setup_internal_defs(body, env):
    names = []
    for f in body:
        if _is_internal_define(f):
            r = f.cdr
            second = r.car
            if isinstance(second, Sym):
                names.append(second.name)
            else:
                names.append(second.car.name)
    if names:
        return Env({n: _UNINITIALIZED for n in names}, env)
    return env

def _eval_define_form(f, env):
    r = f.cdr
    second = r.car
    if isinstance(second, Sym):
        name = second.name
        expr = r.cdr
        if not is_proper_list(expr) or pair_length(expr) != 1:
            raise SchemeError("malformed define")
        val = _eval(expr.car, env, False)
        env.bindings[name] = val
    else:
        if not is_pair(second):
            raise SchemeError("malformed define")
        name_s = second.car
        if not isinstance(name_s, Sym):
            raise SchemeError("malformed define")
        formals = second.cdr
        body = r.cdr
        if not is_proper_list(body) or pair_length(body) == 0:
            raise SchemeError("malformed define")
        pf = _parse_formals(formals)
        cl = Closure(pf, list_to_py(body), env)
        env.bindings[name_s.name] = cl
    return UNDEFINED

def _eval_body(body, env, tail=False):
    new_env = _setup_internal_defs(body, env)
    for i in range(len(body)):
        last = (i == len(body) - 1)
        if _is_internal_define(body[i]):
            _eval_define_form(body[i], new_env)
        elif last and tail:
            return _eval(body[i], new_env, True)
        else:
            _eval(body[i], new_env, False)
    return UNDEFINED

def _eval_body_tail(body, env):
    new_env = _setup_internal_defs(body, env)
    for i in range(len(body) - 1):
        if _is_internal_define(body[i]):
            _eval_define_form(body[i], new_env)
        else:
            _eval(body[i], new_env, False)
    if _is_internal_define(body[-1]):
        _eval_define_form(body[-1], new_env)
        return UNDEFINED
    return _Continue(body[-1], new_env)

def _eval(form, env, tail=False):
    while True:
        result = _eval_once(form, env, tail)
        if isinstance(result, _TailCall):
            body = result.body
            env = result.env
            new_env = _setup_internal_defs(body, env)
            for i in range(len(body) - 1):
                if _is_internal_define(body[i]):
                    _eval_define_form(body[i], new_env)
                else:
                    _eval(body[i], new_env, False)
            if _is_internal_define(body[-1]):
                _eval_define_form(body[-1], new_env)
                return UNDEFINED
            form = body[-1]
            env = new_env
            tail = True
            continue
        elif isinstance(result, _Continue):
            form = result.form
            env = result.env
            tail = True
            continue
        else:
            return result

def _eval_once(form, env, tail):
    if is_num(form) or isinstance(form, str) or isinstance(form, bool):
        return form
    if form is EMPTY:
        return form
    if isinstance(form, Sym):
        return _lookup(env, form.name)
    if not is_pair(form):
        raise SchemeError("invalid form")

    head = form.car
    rest = form.cdr

    if isinstance(head, Sym):
        nm = head.name
        if nm in _SPECIALS:
            if not is_proper_list(rest):
                raise SchemeError(f"malformed {nm}")
            return _eval_special(nm, list_to_py(rest), env, tail)
        if nm == 'apply' and tail:
            if not is_proper_list(rest):
                raise SchemeError("dotted list used as application")
            return _eval_apply_tco(list_to_py(rest), env)

    # Application
    if not is_proper_list(rest):
        raise SchemeError("dotted list used as application")
    args_list = list_to_py(rest)
    op_val = _eval(head, env, False)
    args = [_eval(a, env, False) for a in args_list]
    if not is_procedure(op_val):
        raise SchemeError("not a procedure")
    if tail and isinstance(op_val, Closure):
        new_env = _make_closure_env(op_val, args)
        return _TailCall(op_val.body, new_env)
    return _call_proc(op_val, args)

def _eval_apply_tco(args_list, env):
    if len(args_list) < 2:
        raise SchemeError("apply: expected at least 2 arguments")
    f_val = _eval(args_list[0], env, False)
    mid = [_eval(a, env, False) for a in args_list[1:-1]]
    lst_val = _eval(args_list[-1], env, False)
    if not is_proper_list(lst_val):
        raise SchemeError("apply: last argument must be a proper list")
    all_args = mid + list_to_py(lst_val)
    if not is_procedure(f_val):
        raise SchemeError("apply: first argument must be a procedure")
    if isinstance(f_val, Closure):
        new_env = _make_closure_env(f_val, all_args)
        return _TailCall(f_val.body, new_env)
    return f_val.func(all_args)

_SPECIALS = frozenset({'quote','if','define','set!','begin','cond','and','or','let','let*','letrec','lambda'})

def _eval_special(nm, args, env, tail):
    if nm == 'quote':
        if len(args) != 1:
            raise SchemeError("malformed quote")
        return args[0]

    if nm == 'if':
        if len(args) not in (2, 3):
            raise SchemeError("malformed if")
        tv = _eval(args[0], env, False)
        if tv is not False:
            branch = args[1]
        else:
            branch = args[2] if len(args) == 3 else UNDEFINED
        if branch is UNDEFINED:
            return UNDEFINED
        if tail:
            return _Continue(branch, env)
        return _eval(branch, env, False)

    if nm == 'define':
        if len(args) != 2:
            raise SchemeError("malformed define")
        second = args[0]
        if isinstance(second, Sym):
            name = second.name
            val = _eval(args[1], env, False)
            env.bindings[name] = val
        else:
            if not is_pair(second):
                raise SchemeError("malformed define")
            name_s = second.car
            if not isinstance(name_s, Sym):
                raise SchemeError("malformed define")
            formals = second.cdr
            body = args[1]
            if not isinstance(body, list) or len(body) == 0:
                raise SchemeError("malformed define")
            pf = _parse_formals(formals)
            cl = Closure(pf, body, env)
            env.bindings[name_s.name] = cl
        return UNDEFINED

    if nm == 'set!':
        if len(args) != 2:
            raise SchemeError("malformed set!")
        name = args[0]
        if not isinstance(name, Sym):
            raise SchemeError("set! requires a symbol")
        val = _eval(args[1], env, False)
        e = env
        while e is not None:
            if name.name in e.bindings:
                if e.bindings[name.name] is _UNINITIALIZED:
                    raise SchemeError(f"uninitialized variable: {name.name}")
                e.bindings[name.name] = val
                return UNDEFINED
            e = e.parent
        raise SchemeError(f"unbound variable: {name.name}")

    if nm == 'begin':
        if not args:
            raise SchemeError("malformed begin")
        for i in range(len(args) - 1):
            _eval(args[i], env, False)
        last = args[-1]
        if tail:
            return _Continue(last, env)
        return _eval(last, env, False)

    if nm == 'cond':
        if not args:
            raise SchemeError("malformed cond")
        for i, clause in enumerate(args):
            if not isinstance(clause, list) or len(clause) < 1:
                raise SchemeError("malformed cond clause")
            test_expr = clause[0]
            if test_expr == sym('else'):
                if i != len(args) - 1:
                    raise SchemeError("else must be last clause")
                exprs = clause[1:]
                if not exprs:
                    raise SchemeError("malformed else clause")
                for j in range(len(exprs) - 1):
                    _eval(exprs[j], env, False)
                last_e = exprs[-1]
                if tail:
                    return _Continue(last_e, env)
                return _eval(last_e, env, False)
            else:
                tv = _eval(test_expr, env, False)
                if tv is not False:
                    exprs = clause[1:]
                    if not exprs:
                        return tv
                    for j in range(len(exprs) - 1):
                        _eval(exprs[j], env, False)
                    last_e = exprs[-1]
                    if tail:
                        return _Continue(last_e, env)
                    return _eval(last_e, env, False)
        return UNDEFINED

    if nm == 'and':
        for i in range(len(args)):
            if i == len(args) - 1 and tail:
                return _Continue(args[i], env)
            v = _eval(args[i], env, False)
            if v is False:
                return False
        return True

    if nm == 'or':
        for i in range(len(args)):
            if i == len(args) - 1 and tail:
                return _Continue(args[i], env)
            v = _eval(args[i], env, False)
            if v is not False:
                return v
        return False

    if nm == 'lambda':
        if len(args) < 2:
            raise SchemeError("malformed lambda")
        formals = args[0]
        body = args[1:]
        pf = _parse_formals(formals)
        return Closure(pf, body, env)

    if nm == 'let':
        if len(args) < 2:
            raise SchemeError("malformed let")
        # Check for named let
        if isinstance(args[0], Sym):
            return _eval_named_let(args[0], args[1], args[2:], env, tail)
        bindings = args[0]
        body = args[1:]
        return _eval_let(bindings, body, env, tail)

    if nm == 'let*':
        if len(args) < 2:
            raise SchemeError("malformed let*")
        bindings = args[0]
        body = args[1:]
        return _eval_letstar(bindings, body, env, tail)

    if nm == 'letrec':
        if len(args) < 2:
            raise SchemeError("malformed letrec")
        bindings = args[0]
        body = args[1:]
        return _eval_letrec(bindings, body, env, tail)

    raise SchemeError(f"unknown special form: {nm}")

def _eval_let(bindings, body, env, tail):
    if not is_proper_list(make_list(bindings)):
        pass
    # bindings is a Python list of [name, init] pairs
    names = []
    inits = []
    for b in bindings:
        if not isinstance(b, list) or len(b) != 2:
            raise SchemeError("malformed let binding")
        v, e = b
        if not isinstance(v, Sym):
            raise SchemeError("let: variable must be a symbol")
        names.append(v)
        inits.append(e)
    vals = [_eval(e, env, False) for e in inits]
    new_env = Env({v.name: val for v, val in zip(names, vals)}, env)
    if tail:
        return _eval_body_tail(body, new_env)
    return _eval_body(body, new_env, False)

def _eval_letstar(bindings, body, env, tail):
    new_env = env
    for b in bindings:
        if not isinstance(b, list) or len(b) != 2:
            raise SchemeError("malformed let* binding")
        v, e = b
        if not isinstance(v, Sym):
            raise SchemeError("let*: variable must be a symbol")
        val = _eval(e, new_env, False)
        new_env = Env({v.name: val}, new_env)
    if tail:
        return _eval_body_tail(body, new_env)
    return _eval_body(body, new_env, False)

def _eval_letrec(bindings, body, env, tail):
    names = []
    inits = []
    for b in bindings:
        if not isinstance(b, list) or len(b) != 2:
            raise SchemeError("malformed letrec binding")
        v, e = b
        if not isinstance(v, Sym):
            raise SchemeError("letrec: variable must be a symbol")
        names.append(v)
        inits.append(e)
    new_env = Env({v.name: _UNINITIALIZED for v in names}, env)
    for v, e in zip(names, inits):
        val = _eval(e, new_env, False)
        new_env.bindings[v.name] = val
    if tail:
        return _eval_body_tail(body, new_env)
    return _eval_body(body, new_env, False)

def _eval_named_let(name_sym, bindings, body, env, tail):
    names = []
    inits = []
    for b in bindings:
        if not isinstance(b, list) or len(b) != 2:
            raise SchemeError("malformed named let binding")
        v, e = b
        if not isinstance(v, Sym):
            raise SchemeError("named let: variable must be a symbol")
        names.append(v)
        inits.append(e)
    vals = [_eval(e, env, False) for e in inits]
    bd = {}
    new_env = Env(bd, env)
    cl = Closure(('fixed', names), body, new_env)
    bd[name_sym.name] = cl
    param_env = Env({v.name: val for v, val in zip(names, vals)}, new_env)
    if tail:
        return _eval_body_tail(body, param_env)
    return _eval_body(body, param_env, False)

# ─── Builtins ─────────────────────────────────────────────────────────────────

def _check_ints(args, name):
    for a in args:
        if not is_num(a):
            raise SchemeError(f"{name}: expected integer arguments")

def _b_plus(args):
    _check_ints(args, '+')
    return sum(args)

def _b_star(args):
    _check_ints(args, '*')
    r = 1
    for a in args: r *= a
    return r

def _b_minus(args):
    if not args: raise SchemeError("-: expected at least 1 argument")
    _check_ints(args, '-')
    if len(args) == 1: return -args[0]
    r = args[0]
    for a in args[1:]: r -= a
    return r

def _b_quotient(args):
    if len(args) != 2: raise SchemeError("quotient: expected 2 arguments")
    a, b = args
    _check_ints(args, 'quotient')
    if b == 0: raise SchemeError("division by zero")
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0): q = -q
    return q

def _b_remainder(args):
    if len(args) != 2: raise SchemeError("remainder: expected 2 arguments")
    a, b = args
    _check_ints(args, 'remainder')
    if b == 0: raise SchemeError("division by zero")
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0): q = -q
    return a - q * b

def _b_modulo(args):
    if len(args) != 2: raise SchemeError("modulo: expected 2 arguments")
    a, b = args
    _check_ints(args, 'modulo')
    if b == 0: raise SchemeError("division by zero")
    return a % b

def _make_cmp(op):
    def f(args):
        if not args: raise SchemeError("comparison: expected at least 1 argument")
        _check_ints(args, 'comparison')
        for i in range(len(args) - 1):
            if not op(args[i], args[i+1]):
                return False
        return True
    return f

def _b_number_to_string(args):
    if len(args) not in (1, 2):
        raise SchemeError("number->string: expected 1 or 2 arguments")
    n = args[0]
    if not is_num(n):
        raise SchemeError("number->string: expected integer")
    if len(args) == 1:
        return str(n)
    radix = args[1]
    if not is_num(radix) or radix not in (2, 8, 10, 16):
        raise SchemeError("number->string: invalid radix")
    if n < 0:
        return '-' + _to_radix(-n, radix)
    return _to_radix(n, radix)

def _to_radix(n, r):
    if n == 0: return '0'
    d = '0123456789abcdef'
    parts = []
    while n > 0:
        parts.append(d[n % r])
        n //= r
    return ''.join(reversed(parts))

def _b_cons(args):
    if len(args) != 2: raise SchemeError("cons: expected 2 arguments")
    return Pair(args[0], args[1])

def _b_car(args):
    if len(args) != 1: raise SchemeError("car: expected 1 argument")
    if not is_pair(args[0]): raise SchemeError("car: expected a pair")
    return args[0].car

def _b_cdr(args):
    if len(args) != 1: raise SchemeError("cdr: expected 1 argument")
    if not is_pair(args[0]): raise SchemeError("cdr: expected a pair")
    return args[0].cdr

def _b_list(args):
    return make_list(args)

def _b_null(args):
    if len(args) != 1: raise SchemeError("null?: expected 1 argument")
    return args[0] is EMPTY

def _b_pair(args):
    if len(args) != 1: raise SchemeError("pair?: expected 1 argument")
    return is_pair(args[0])

def _b_listp(args):
    if len(args) != 1: raise SchemeError("list?: expected 1 argument")
    return is_proper_list(args[0])

def _b_length(args):
    if len(args) != 1: raise SchemeError("length: expected 1 argument")
    if not is_proper_list(args[0]): raise SchemeError("length: expected a proper list")
    return pair_length(args[0])

def _b_append(args):
    for a in args[:-1]:
        if not is_proper_list(a):
            raise SchemeError("append: expected proper lists")
    if not args:
        return EMPTY
    last = args[-1]
    result = last
    for a in reversed(args[:-1]):
        p = a
        while is_pair(p):
            result = Pair(p.car, result)
            p = p.cdr
    return result

def _b_reverse(args):
    if len(args) != 1: raise SchemeError("reverse: expected 1 argument")
    if not is_proper_list(args[0]): raise SchemeError("reverse: expected a proper list")
    result = EMPTY
    p = args[0]
    while is_pair(p):
        result = Pair(p.car, result)
        p = p.cdr
    return result

def _b_apply(args):
    if len(args) < 2: raise SchemeError("apply: expected at least 2 arguments")
    f = args[0]
    if not is_procedure(f): raise SchemeError("apply: first argument must be a procedure")
    lst = args[-1]
    if not is_proper_list(lst): raise SchemeError("apply: last argument must be a proper list")
    all_args = args[1:-1] + list_to_py(lst)
    return _call_proc(f, all_args)

def _b_eq(args):
    if len(args) != 2: raise SchemeError("eq?: expected 2 arguments")
    a, b = args
    if a is b: return True
    if is_num(a) and is_num(b): return a == b
    return False

def _equal_impl(a, b):
    stack = [(a, b)]
    while stack:
        x, y = stack.pop()
        if x is y: continue
        if is_num(x) and is_num(y):
            if x != y: return False
        elif isinstance(x, str) and isinstance(y, str):
            if x != y: return False
        elif isinstance(x, Sym) and isinstance(y, Sym):
            if x.name != y.name: return False
        elif isinstance(x, Pair) and isinstance(y, Pair):
            stack.append((x.cdr, y.cdr))
            stack.append((x.car, y.car))
        else:
            return False
    return True

def _b_equal(args):
    if len(args) != 2: raise SchemeError("equal?: expected 2 arguments")
    return _equal_impl(args[0], args[1])

def _b_not(args):
    if len(args) != 1: raise SchemeError("not: expected 1 argument")
    return args[0] is False

def _b_numberp(args):
    if len(args) != 1: raise SchemeError("number?: expected 1 argument")
    return is_num(args[0])

def _b_symbolp(args):
    if len(args) != 1: raise SchemeError("symbol?: expected 1 argument")
    return isinstance(args[0], Sym)

def _b_stringp(args):
    if len(args) != 1: raise SchemeError("string?: expected 1 argument")
    return isinstance(args[0], str)

def _b_procedurep(args):
    if len(args) != 1: raise SchemeError("procedure?: expected 1 argument")
    return is_procedure(args[0])

def _b_string_append(args):
    for a in args:
        if not isinstance(a, str):
            raise SchemeError("string-append: expected string arguments")
    return ''.join(args)

def _b_display(args):
    if len(args) != 1: raise SchemeError("display: expected 1 argument")
    _output.append(_repr(args[0], False))
    return UNDEFINED

def _b_newline(args):
    if args: raise SchemeError("newline: expected 0 arguments")
    _output.append('\n')
    return UNDEFINED

def _b_error(args):
    if not args: raise SchemeError("error: expected at least 1 argument")
    msg = args[0]
    if not isinstance(msg, str):
        raise SchemeError("error: first argument must be a string")
    full = msg
    for irr in args[1:]:
        full += ' ' + _repr(irr, True)
    raise SchemeError(full)

def _make_global_env():
    b = {
        '+': Builtin('+', _b_plus),
        '*': Builtin('*', _b_star),
        '-': Builtin('-', _b_minus),
        'quotient': Builtin('quotient', _b_quotient),
        'remainder': Builtin('remainder', _b_remainder),
        'modulo': Builtin('modulo', _b_modulo),
        '=': Builtin('=', _make_cmp(lambda a,b: a==b)),
        '<': Builtin('<', _make_cmp(lambda a,b: a<b)),
        '>': Builtin('>', _make_cmp(lambda a,b: a>b)),
        '<=': Builtin('<=', _make_cmp(lambda a,b: a<=b)),
        '>=': Builtin('>=', _make_cmp(lambda a,b: a>=b)),
        'number->string': Builtin('number->string', _b_number_to_string),
        'cons': Builtin('cons', _b_cons),
        'car': Builtin('car', _b_car),
        'cdr': Builtin('cdr', _b_cdr),
        'list': Builtin('list', _b_list),
        'null?': Builtin('null?', _b_null),
        'pair?': Builtin('pair?', _b_pair),
        'list?': Builtin('list?', _b_listp),
        'length': Builtin('length', _b_length),
        'append': Builtin('append', _b_append),
        'reverse': Builtin('reverse', _b_reverse),
        'apply': Builtin('apply', _b_apply),
        'eq?': Builtin('eq?', _b_eq),
        'equal?': Builtin('equal?', _b_equal),
        'not': Builtin('not', _b_not),
        'number?': Builtin('number?', _b_numberp),
        'symbol?': Builtin('symbol?', _b_symbolp),
        'string?': Builtin('string?', _b_stringp),
        'procedure?': Builtin('procedure?', _b_procedurep),
        'string-append': Builtin('string-append', _b_string_append),
        'display': Builtin('display', _b_display),
        'newline': Builtin('newline', _b_newline),
        'error': Builtin('error', _b_error),
    }
    return Env(b)

# ─── Public API ───────────────────────────────────────────────────────────────

def run(source):
    global _output
    _output = []
    try:
        forms = _read_all(source)
    except SchemeError:
        raise
    except Exception as e:
        raise SchemeError(str(e), '')
    env = _make_global_env()
    try:
        for f in forms:
            _eval(f, env, False)
    except SchemeError as e:
        e.output = ''.join(_output)
        raise
    except Exception as e:
        raise SchemeError(str(e), ''.join(_output))
    return ''.join(_output)