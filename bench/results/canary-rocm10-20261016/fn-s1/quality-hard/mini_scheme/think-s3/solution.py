"""A Scheme subset interpreter."""

import sys
import threading

if hasattr(sys, 'set_int_max_str_digits'):
    sys.set_int_max_str_digits(0)

sys.setrecursionlimit(300000)


class SchemeError(Exception):
    def __init__(self, message, output=''):
        super().__init__(message)
        self.output = output


# ─── Data types ───────────────────────────────────────────────────────────────

class Symbol:
    __slots__ = ('name',)
    _intern = {}

    def __new__(cls, name):
        if name in cls._intern:
            return cls._intern[name]
        obj = super().__new__(cls)
        obj.name = name
        cls._intern[name] = obj
        return obj

    def __repr__(self):
        return self.name

    def __eq__(self, other):
        return isinstance(other, Symbol) and self.name == other.name

    def __hash__(self):
        return hash(('S', self.name))


class Pair:
    __slots__ = ('car', 'cdr')

    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr


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


class _Uninit:
    _inst = None

    def __new__(cls):
        if cls._inst is None:
            cls._inst = super().__new__(cls)
        return cls._inst


UNINITIALIZED = _Uninit()


class SchemeBool:
    __slots__ = ('value',)

    def __init__(self, v):
        self.value = v

    def __repr__(self):
        return '#t' if self.value else '#f'


TRUE = SchemeBool(True)
FALSE = SchemeBool(False)


# ─── Environment ──────────────────────────────────────────────────────────────

class Frame:
    __slots__ = ('bindings', 'parent')

    def __init__(self, bindings=None, parent=None):
        self.bindings = bindings if bindings is not None else {}
        self.parent = parent

    def lookup(self, sym):
        f = self
        while f is not None:
            if sym in f.bindings:
                v = f.bindings[sym]
                if isinstance(v, _Uninit):
                    raise SchemeError(f"uninitialized variable: {sym.name}")
                return v
            f = f.parent
        raise SchemeError(f"unbound variable: {sym.name}")

    def set(self, sym, val):
        f = self
        while f is not None:
            if sym in f.bindings:
                f.bindings[sym] = val
                return
            f = f.parent
        raise SchemeError(f"set!: unbound variable: {sym.name}")


# ─── Procedures ───────────────────────────────────────────────────────────────

class Closure:
    __slots__ = ('params', 'var_args', 'body', 'env')

    def __init__(self, params, var_args, body, env):
        self.params = params
        self.var_args = var_args
        self.body = body
        self.env = env


class Builtin:
    __slots__ = ('func', 'name')

    def __init__(self, func, name):
        self.func = func
        self.name = name


class TailCall:
    __slots__ = ('proc', 'args')

    def __init__(self, proc, args):
        self.proc = proc
        self.args = args


# ─── Reader ───────────────────────────────────────────────────────────────────

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


def _tokenize(source):
    tokens = []
    i = 0
    n = len(source)
    while i < n:
        c = source[i]
        if c in ' \t\n\r':
            i += 1
            continue
        if c == ';':
            while i < n and source[i] != '\n':
                i += 1
            continue
        if c == '(':
            tokens.append('(')
            i += 1
            continue
        if c == ')':
            tokens.append(')')
            i += 1
            continue
        if c == "'":
            tokens.append("'")
            i += 1
            continue
        if c == '"':
            i += 1
            parts = []
            while i < n:
                if source[i] == '\\':
                    i += 1
                    if i >= n:
                        raise SchemeError("unterminated string")
                    ch = source[i]
                    if ch == '"':
                        parts.append('"')
                    elif ch == '\\':
                        parts.append('\\')
                    elif ch == 'n':
                        parts.append('\n')
                    else:
                        raise SchemeError(f"invalid escape \\{ch}")
                    i += 1
                elif source[i] == '"':
                    i += 1
                    break
                else:
                    parts.append(source[i])
                    i += 1
            else:
                raise SchemeError("unterminated string")
            tokens.append(('str', ''.join(parts)))
            continue
        # general token
        j = i
        while j < n and source[j] not in ' \t\n\r()";\'':
            j += 1
        tokens.append(source[i:j])
        i = j
    return tokens


def _parse_all(tokens):
    pos = [0]

    def peek():
        return tokens[pos[0]] if pos[0] < len(tokens) else None

    def advance():
        t = tokens[pos[0]]
        pos[0] += 1
        return t

    def parse_datum():
        if pos[0] >= len(tokens):
            raise SchemeError("unexpected end of input")
        tok = tokens[pos[0]]
        if tok == '(':
            pos[0] += 1
            return parse_list()
        if tok == ')':
            raise SchemeError("unexpected )")
        if tok == "'":
            pos[0] += 1
            d = parse_datum()
            return Pair(Symbol('quote'), Pair(d, EMPTY))
        if isinstance(tok, tuple) and tok[0] == 'str':
            pos[0] += 1
            return tok[1]
        pos[0] += 1
        return _atom(tok)

    def parse_list():
        elems = []
        dot_val = None
        has_dot = False
        while True:
            if pos[0] >= len(tokens):
                raise SchemeError("unexpected end of input (unclosed paren)")
            tok = tokens[pos[0]]
            if tok == ')':
                pos[0] += 1
                break
            if tok == '.' and not has_dot:
                if len(elems) == 0:
                    raise SchemeError("dot with no preceding element")
                pos[0] += 1
                has_dot = True
                dot_val = parse_datum()
                if pos[0] >= len(tokens) or tokens[pos[0]] != ')':
                    raise SchemeError("expected ) after dot value")
                pos[0] += 1
                break
            if tok == ')':
                pos[0] += 1
                break
            elems.append(parse_datum())
        if has_dot:
            result = dot_val
            for e in reversed(elems):
                result = Pair(e, result)
            return result
        result = EMPTY
        for e in reversed(elems):
            result = Pair(e, result)
        return result

    forms = []
    while pos[0] < len(tokens):
        forms.append(parse_datum())
    return forms


def _atom(tok):
    if tok == '#t':
        return TRUE
    if tok == '#f':
        return FALSE
    if tok.startswith('#'):
        raise SchemeError(f"invalid syntax: {tok}")
    if _is_int_token(tok):
        return int(tok)
    return Symbol(tok)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def is_true(v):
    return not (isinstance(v, SchemeBool) and not v.value)


def is_proper_list(v):
    while isinstance(v, Pair):
        v = v.cdr
    return isinstance(v, _EmptyList)


def to_list(p):
    """Convert a proper list (Pair chain) to a Python list."""
    result = []
    while isinstance(p, Pair):
        result.append(p.car)
        p = p.cdr
    return result


def from_list(lst):
    """Convert a Python list to a Scheme proper list."""
    result = EMPTY
    for x in reversed(lst):
        result = Pair(x, result)
    return result


def list_length(p):
    n = 0
    while isinstance(p, Pair):
        n += 1
        p = p.cdr
    return n


# ─── Display / Write ──────────────────────────────────────────────────────────

def display_repr(val, write_mode=False):
    parts = []
    _display_into(val, parts, write_mode)
    return ''.join(parts)


def _display_into(val, buf, wm):
    if isinstance(val, int):
        buf.append(_int_to_str(val))
    elif isinstance(val, SchemeBool):
        buf.append('#t' if val.value else '#f')
    elif isinstance(val, str):
        if wm:
            buf.append('"')
            for ch in val:
                if ch == '"':
                    buf.append('\\"')
                elif ch == '\\':
                    buf.append('\\\\')
                elif ch == '\n':
                    buf.append('\\n')
                else:
                    buf.append(ch)
            buf.append('"')
        else:
            buf.append(val)
    elif isinstance(val, Symbol):
        buf.append(val.name)
    elif isinstance(val, _EmptyList):
        buf.append('()')
    elif isinstance(val, _Unspecified):
        pass
    elif isinstance(val, (Closure, Builtin)):
        buf.append('#<procedure>')
    elif isinstance(val, Pair):
        buf.append('(')
        items = []
        cur = val
        while isinstance(cur, Pair):
            items.append(cur.car)
            cur = cur.cdr
        for i, item in enumerate(items):
            if i > 0:
                buf.append(' ')
            _display_into(item, buf, wm)
        if not isinstance(cur, _EmptyList):
            buf.append(' . ')
            _display_into(cur, buf, wm)
        buf.append(')')
    else:
        buf.append(str(val))


def _int_to_str(n):
    if n == 0:
        return "0"
    neg = n < 0
    n = abs(n)
    digits = []
    while n > 0:
        digits.append(chr(48 + n % 10))
        n //= 10
    if neg:
        digits.append('-')
    return ''.join(reversed(digits))


# ─── Evaluator ────────────────────────────────────────────────────────────────

SYM_QUOTE = Symbol('quote')
SYM_IF = Symbol('if')
SYM_LAMBDA = Symbol('lambda')
SYM_DEFINE = Symbol('define')
SYM_SET = Symbol('set!')
SYM_BEGIN = Symbol('begin')
SYM_COND = Symbol('cond')
SYM_AND = Symbol('and')
SYM_OR = Symbol('or')
SYM_LET = Symbol('let')
SYM_LETSTAR = Symbol('let*')
SYM_LETREC = Symbol('letrec')
SYM_APPLY = Symbol('apply')
SYM_ELSE = Symbol('else')


def scan_internal_defs(body):
    names = []
    for form in body:
        if isinstance(form, Pair) and isinstance(form.car, Symbol) and form.car == SYM_DEFINE:
            n = _define_name(form)
            if n is not None:
                names.append(n)
    return names


def _define_name(form):
    inner = form.cdr.car
    if isinstance(inner, Symbol):
        return inner
    if isinstance(inner, Pair) and isinstance(inner.car, Symbol):
        return inner.car
    return None


def parse_formals(formals):
    if isinstance(formals, Symbol):
        return ([], formals)
    if isinstance(formals, _EmptyList):
        return ([], None)
    if isinstance(formals, Pair):
        params = []
        cur = formals
        while isinstance(cur, Pair):
            p = cur.car
            if not isinstance(p, Symbol):
                raise SchemeError("malformed lambda formals")
            params.append(p)
            cur = cur.cdr
        if isinstance(cur, _EmptyList):
            return (params, None)
        if isinstance(cur, Symbol):
            return (params, cur)
        raise SchemeError("malformed lambda formals")
    raise SchemeError("malformed lambda formals")


def make_closure(formals, body, env):
    params, var_args = parse_formals(formals)
    return Closure(params, var_args, body, env)


def make_closure_env(closure, args):
    pf = Frame({}, closure.env)
    params = closure.params
    va = closure.var_args
    if va is None:
        for i, p in enumerate(params):
            pf.bindings[p] = args[i]
    else:
        for i, p in enumerate(params):
            pf.bindings[p] = args[i]
        pf.bindings[va] = from_list(args[len(params):])
    internal = scan_internal_defs(closure.body)
    if internal:
        return Frame({n: UNINITIALIZED for n in internal}, pf)
    return pf


def check_arity(proc, nargs):
    if isinstance(proc, Closure):
        if proc.var_args is None:
            if nargs != len(proc.params):
                raise SchemeError("wrong number of arguments")
        else:
            if nargs < len(proc.params):
                raise SchemeError("too few arguments")


def apply_proc(proc, args):
    if isinstance(proc, Builtin):
        return proc.func(args)
    if isinstance(proc, Closure):
        env = make_closure_env(proc, args)
        body = proc.body
        for form in body[:-1]:
            eval_expr(form, env, False)
        return eval_expr(body[-1], env, False)
    raise SchemeError("not a procedure")


def eval_body(body, env, tail):
    if not body:
        raise SchemeError("empty body")
    internal = scan_internal_defs(body)
    if internal:
        env = Frame({n: UNINITIALIZED for n in internal}, env)
    for form in body[:-1]:
        eval_expr(form, env, False)
    return eval_expr(body[-1], env, tail)


def eval_expr(expr, env, tail=False):
    # Self-evaluating
    if isinstance(expr, int):
        return expr
    if isinstance(expr, SchemeBool):
        return expr
    if isinstance(expr, str):
        return expr
    if isinstance(expr, _Unspecified):
        return expr
    if isinstance(expr, _EmptyList):
        raise SchemeError("cannot evaluate ()")
    if isinstance(expr, Symbol):
        return env.lookup(expr)

    if not isinstance(expr, Pair):
        raise SchemeError("cannot evaluate")

    head = expr.car

    if isinstance(head, Symbol):
        hn = head.name

        if hn == 'quote':
            return eval_quote(expr)
        if hn == 'if':
            return eval_if(expr, env, tail)
        if hn == 'lambda':
            return eval_lambda(expr, env)
        if hn == 'define':
            return eval_define(expr, env)
        if hn == 'set!':
            return eval_set(expr, env)
        if hn == 'begin':
            return eval_begin(expr, env, tail)
        if hn == 'cond':
            return eval_cond(expr, env, tail)
        if hn == 'and':
            return eval_and(expr, env, tail)
        if hn == 'or':
            return eval_or(expr, env, tail)
        if hn == 'let':
            return eval_let(expr, env, tail)
        if hn == 'let*':
            return eval_letstar(expr, env, tail)
        if hn == 'letrec':
            return eval_letrec(expr, env, tail)
        if hn == 'apply':
            return eval_apply(expr, env, tail)

    # Application
    return eval_application(expr, env, tail)


def eval_quote(expr):
    if expr.cdr is EMPTY:
        raise SchemeError("malformed quote")
    return expr.cdr.car


def eval_if(expr, env, tail):
    rest = to_list(expr.cdr)
    if len(rest) < 2 or len(rest) > 3:
        raise SchemeError("malformed if")
    test_val = eval_expr(rest[0], env, False)
    if is_true(test_val):
        return eval_expr(rest[1], env, tail)
    if len(rest) == 3:
        return eval_expr(rest[2], env, tail)
    return UNSPECIFIED


def eval_lambda(expr, env):
    rest = expr.cdr
    if rest is EMPTY:
        raise SchemeError("malformed lambda")
    formals = rest.car
    body = to_list(rest.cdr)
    if not body:
        raise SchemeError("empty lambda body")
    return make_closure(formals, body, env)


def eval_define(expr, env):
    rest = expr.cdr
    if rest is EMPTY:
        raise SchemeError("malformed define")
    inner = rest.car
    if isinstance(inner, Symbol):
        # (define name expr)
        exprs = to_list(rest.cdr)
        if len(exprs) != 1:
            raise SchemeError("malformed define")
        val = eval_expr(exprs[0], env, False)
        env.bindings[inner] = val
        return UNSPECIFIED
    if isinstance(inner, Pair):
        # (define (name . formals) body...)
        if not isinstance(inner.car, Symbol):
            raise SchemeError("malformed define")
        name = inner.car
        formals = inner.cdr
        body = to_list(rest.cdr)
        if not body:
            raise SchemeError("empty define body")
        closure = make_closure(formals, body, env)
        env.bindings[name] = closure
        return UNSPECIFIED
    raise SchemeError("malformed define")


def eval_set(expr, env):
    rest = expr.cdr
    if rest is EMPTY:
        raise SchemeError("malformed set!")
    name = rest.car
    if not isinstance(name, Symbol):
        raise SchemeError("set!: not a symbol")
    exprs = to_list(rest.cdr)
    if len(exprs) != 1:
        raise SchemeError("malformed set!")
    val = eval_expr(exprs[0], env, False)
    env.set(name, val)
    return UNSPECIFIED


def eval_begin(expr, env, tail):
    exprs = to_list(expr.cdr)
    if not exprs:
        raise SchemeError("empty begin")
    for e in exprs[:-1]:
        eval_expr(e, env, False)
    return eval_expr(exprs[-1], env, tail)


def eval_cond(expr, env, tail):
    clauses = to_list(expr.cdr)
    if not clauses:
        return UNSPECIFIED
    for i, clause in enumerate(clauses):
        if not isinstance(clause, Pair):
            raise SchemeError("malformed cond clause")
        test = clause.car
        body = to_list(clause.cdr)
        if isinstance(test, Symbol) and test.name == 'else':
            if i != len(clauses) - 1:
                raise SchemeError("else not last clause")
            if not body:
                return UNSPECIFIED
            for e in body[:-1]:
                eval_expr(e, env, False)
            return eval_expr(body[-1], env, tail)
        else:
            tv = eval_expr(test, env, False)
            if is_true(tv):
                if not body:
                    return tv
                for e in body[:-1]:
                    eval_expr(e, env, False)
                return eval_expr(body[-1], env, tail)
    return UNSPECIFIED


def eval_and(expr, env, tail):
    exprs = to_list(expr.cdr)
    if not exprs:
        return TRUE
    for e in exprs[:-1]:
        v = eval_expr(e, env, False)
        if not is_true(v):
            return FALSE
    return eval_expr(exprs[-1], env, tail)


def eval_or(expr, env, tail):
    exprs = to_list(expr.cdr)
    if not exprs:
        return FALSE
    for e in exprs[:-1]:
        v = eval_expr(e, env, False)
        if is_true(v):
            return v
    return eval_expr(exprs[-1], env, tail)


def eval_let(expr, env, tail):
    rest = expr.cdr
    if rest is EMPTY:
        raise SchemeError("malformed let")
    bindings_node = rest.car
    body = to_list(rest.cdr)
    if not body:
        raise SchemeError("empty let body")
    # Named let?
    if isinstance(bindings_node, Symbol):
        name = bindings_node
        bindings_node = rest.cdr.car if isinstance(rest.cdr, Pair) else EMPTY
        body = to_list(rest.cdr.cdr) if isinstance(rest.cdr, Pair) else []
        if not body:
            raise SchemeError("empty named let body")
        return eval_named_let(name, bindings_node, body, env, tail)
    # Regular let
    bindings = _parse_bindings(bindings_node)
    frame = Frame({}, env)
    for var, init in bindings:
        frame.bindings[var] = eval_expr(init, env, False)
    return eval_body(body, frame, tail)


def eval_named_let(name, bindings_node, body, outer_env, tail):
    bindings = _parse_bindings(bindings_node)
    values = [eval_expr(init, outer_env, False) for _, init in bindings]
    frame = Frame({name: UNINITIALIZED}, outer_env)
    params = [v for v, _ in bindings]
    closure = Closure(params, None, body, frame)
    frame.bindings[name] = closure
    if tail:
        return TailCall(closure, values)
    return apply_proc(closure, values)


def eval_letstar(expr, env, tail):
    rest = expr.cdr
    if rest is EMPTY:
        raise SchemeError("malformed let*")
    bindings_node = rest.car
    body = to_list(rest.cdr)
    if not body:
        raise SchemeError("empty let* body")
    bindings = _parse_bindings(bindings_node)
    frame = Frame({}, env)
    for var, init in bindings:
        frame.bindings[var] = eval_expr(init, frame, False)
    return eval_body(body, frame, tail)


def eval_letrec(expr, env, tail):
    rest = expr.cdr
    if rest is EMPTY:
        raise SchemeError("malformed letrec")
    bindings_node = rest.car
    body = to_list(rest.cdr)
    if not body:
        raise SchemeError("empty letrec body")
    bindings = _parse_bindings(bindings_node)
    names = [v for v, _ in bindings]
    frame = Frame({n: UNINITIALIZED for n in names}, env)
    for var, init in bindings:
        frame.bindings[var] = eval_expr(init, frame, False)
    return eval_body(body, frame, tail)


def _parse_bindings(node):
    result = []
    while isinstance(node, Pair):
        b = node.car
        if not isinstance(b, Pair):
            raise SchemeError("malformed binding")
        var = b.car
        if not isinstance(var, Symbol):
            raise SchemeError("malformed binding variable")
        init = b.cdr
        if init is EMPTY:
            raise SchemeError("malformed binding: missing init")
        result.append((var, init.car))
        node = node.cdr
    if not isinstance(node, _EmptyList):
        raise SchemeError("malformed bindings")
    return result


def eval_apply(expr, env, tail):
    args = to_list(expr.cdr)
    if len(args) < 2:
        raise SchemeError("apply requires at least 2 arguments")
    vals = [eval_expr(a, env, False) for a in args]
    f = vals[0]
    if not isinstance(f, (Closure, Builtin)):
        raise SchemeError("apply: not a procedure")
    lst = vals[-1]
    if not is_proper_list(lst):
        raise SchemeError("apply: last argument must be a proper list")
    final_args = vals[1:-1] + to_list(lst)
    check_arity(f, len(final_args))
    if tail:
        return TailCall(f, final_args)
    return apply_proc(f, final_args)


def eval_application(expr, env, tail):
    proc = eval_expr(expr.car, env, False)
    args = []
    cur = expr.cdr
    while isinstance(cur, Pair):
        args.append(eval_expr(cur.car, env, False))
        cur = cur.cdr
    if not isinstance(cur, _EmptyList):
        raise SchemeError("dotted form in application")
    if not isinstance(proc, (Closure, Builtin)):
        raise SchemeError("not a procedure")
    check_arity(proc, len(args))
    if tail:
        return TailCall(proc, args)
    return apply_proc(proc, args)


def trampoline(expr, env):
    while True:
        result = eval_expr(expr, env, True)
        if isinstance(result, TailCall):
            proc = result.proc
            args = result.args
            if isinstance(proc, Builtin):
                return proc.func(args)
            if isinstance(proc, Closure):
                env = make_closure_env(proc, args)
                body = proc.body
                for form in body[:-1]:
                    eval_expr(form, env, False)
                expr = body[-1]
            else:
                raise SchemeError("not a procedure")
        else:
            return result


# ─── Builtins ─────────────────────────────────────────────────────────────────

def _make_builtins(output):
    env = Frame({}, None)

    def _int(x, name):
        if isinstance(x, int):
            return x
        raise SchemeError(f"{name}: expected integer")

    def _ints(args, name):
        for a in args:
            if not isinstance(a, int):
                raise SchemeError(f"{name}: expected integer")
        return args

    def _pair(x, name):
        if isinstance(x, Pair):
            return x
        raise SchemeError(f"{name}: expected pair")

    def _proper_list(x, name):
        if is_proper_list(x):
            return x
        raise SchemeError(f"{name}: expected proper list")

    def _string(x, name):
        if isinstance(x, str):
            return x
        raise SchemeError(f"{name}: expected string")

    # Arithmetic
    def bi_add(args):
        _ints(args, '+')
        return sum(args)

    def bi_mul(args):
        _ints(args, '*')
        r = 1
        for a in args:
            r *= a
        return r

    def bi_sub(args):
        _ints(args, '-')
        if len(args) < 1:
            raise SchemeError("-: at least 1 argument")
        r = args[0]
        for a in args[1:]:
            r -= a
        return r

    def _quotient(a, b):
        q = a // b
        if a % b != 0 and (a < 0) != (b < 0):
            q += 1
        return q

    def bi_quotient(args):
        if len(args) != 2:
            raise SchemeError("quotient: 2 arguments")
        a, b = _int(args[0], 'quotient'), _int(args[1], 'quotient')
        if b == 0:
            raise SchemeError("quotient: division by zero")
        return _quotient(a, b)

    def bi_remainder(args):
        if len(args) != 2:
            raise SchemeError("remainder: 2 arguments")
        a, b = _int(args[0], 'remainder'), _int(args[1], 'remainder')
        if b == 0:
            raise SchemeError("remainder: division by zero")
        return a - _quotient(a, b) * b

    def bi_modulo(args):
        if len(args) != 2:
            raise SchemeError("modulo: 2 arguments")
        a, b = _int(args[0], 'modulo'), _int(args[1], 'modulo')
        if b == 0:
            raise SchemeError("modulo: division by zero")
        return a % b

    def _make_cmp(op, name):
        def f(args):
            if len(args) < 1:
                raise SchemeError(f"{name}: at least 1 argument")
            _ints(args, name)
            for i in range(len(args) - 1):
                if not op(args[i], args[i + 1]):
                    return FALSE
            return TRUE
        return f

    # List ops
    def bi_cons(args):
        if len(args) != 2:
            raise SchemeError("cons: 2 arguments")
        return Pair(args[0], args[1])

    def bi_car(args):
        if len(args) != 1:
            raise SchemeError("car: 1 argument")
        return _pair(args[0], 'car').car

    def bi_cdr(args):
        if len(args) != 1:
            raise SchemeError("cdr: 1 argument")
        return _pair(args[0], 'cdr').cdr

    def bi_list(args):
        return from_list(args)

    def bi_null(args):
        if len(args) != 1:
            raise SchemeError("null?: 1 argument")
        return TRUE if isinstance(args[0], _EmptyList) else FALSE

    def bi_pair(args):
        if len(args) != 1:
            raise SchemeError("pair?: 1 argument")
        return TRUE if isinstance(args[0], Pair) else FALSE

    def bi_listp(args):
        if len(args) != 1:
            raise SchemeError("list?: 1 argument")
        return TRUE if is_proper_list(args[0]) else FALSE

    def bi_length(args):
        if len(args) != 1:
            raise SchemeError("length: 1 argument")
        _proper_list(args[0], 'length')
        return list_length(args[0])

    def bi_append(args):
        if not args:
            return EMPTY
        for a in args[:-1]:
            _proper_list(a, 'append')
        result = args[-1]
        for a in reversed(args[:-1]):
            items = to_list(a)
            for x in reversed(items):
                result = Pair(x, result)
        return result

    def bi_reverse(args):
        if len(args) != 1:
            raise SchemeError("reverse: 1 argument")
        _proper_list(args[0], 'reverse')
        result = EMPTY
        cur = args[0]
        while isinstance(cur, Pair):
            result = Pair(cur.car, result)
            cur = cur.cdr
        return result

    # Equality
    def bi_eq(args):
        if len(args) != 2:
            raise SchemeError("eq?: 2 arguments")
        a, b = args
        if isinstance(a, int) and isinstance(b, int):
            return TRUE if a == b else FALSE
        if isinstance(a, SchemeBool) and isinstance(b, SchemeBool):
            return TRUE if a is b else FALSE
        if isinstance(a, Symbol) and isinstance(b, Symbol):
            return TRUE if a is b else FALSE
        if isinstance(a, _EmptyList) and isinstance(b, _EmptyList):
            return TRUE
        if isinstance(a, (Closure, Builtin)) or isinstance(b, (Closure, Builtin)):
            return TRUE if a is b else FALSE
        return TRUE if a is b else FALSE

    def bi_equal(args):
        if len(args) != 2:
            raise SchemeError("equal?: 2 arguments")
        return TRUE if _equal(args[0], args[1]) else FALSE

    def _equal(a, b):
        stack = [(a, b)]
        while stack:
            a, b = stack.pop()
            if a is b:
                continue
            if isinstance(a, int) and isinstance(b, int):
                if a != b:
                    return False
                continue
            if isinstance(a, SchemeBool) and isinstance(b, SchemeBool):
                if a.value != b.value:
                    return False
                continue
            if isinstance(a, Symbol) and isinstance(b, Symbol):
                if a.name != b.name:
                    return False
                continue
            if isinstance(a, str) and isinstance(b, str):
                if a != b:
                    return False
                continue
            if isinstance(a, _EmptyList) and isinstance(b, _EmptyList):
                continue
            if isinstance(a, Pair) and isinstance(b, Pair):
                stack.append((a.cdr, b.cdr))
                stack.append((a.car, b.car))
                continue
            if isinstance(a, (Closure, Builtin)) or isinstance(b, (Closure, Builtin)):
                return False
            if isinstance(a, _Unspecified) and isinstance(b, _Unspecified):
                continue
            return False
        return True

    def bi_not(args):
        if len(args) != 1:
            raise SchemeError("not: 1 argument")
        return TRUE if not is_true(args[0]) else FALSE

    def bi_number_p(args):
        if len(args) != 1:
            raise SchemeError("number?: 1 argument")
        return TRUE if isinstance(args[0], int) else FALSE

    def bi_symbol_p(args):
        if len(args) != 1:
            raise SchemeError("symbol?: 1 argument")
        return TRUE if isinstance(args[0], Symbol) else FALSE

    def bi_string_p(args):
        if len(args) != 1:
            raise SchemeError("string?: 1 argument")
        return TRUE if isinstance(args[0], str) else FALSE

    def bi_procedure_p(args):
        if len(args) != 1:
            raise SchemeError("procedure?: 1 argument")
        return TRUE if isinstance(args[0], (Closure, Builtin)) else FALSE

    def bi_string_append(args):
        for a in args:
            _string(a, 'string-append')
        return ''.join(args)

    # Output
    def bi_display(args):
        if len(args) != 1:
            raise SchemeError("display: 1 argument")
        output.append(display_repr(args[0], False))
        return UNSPECIFIED

    def bi_newline(args):
        if len(args) != 0:
            raise SchemeError("newline: 0 arguments")
        output.append('\n')
        return UNSPECIFIED

    def bi_error(args):
        if len(args) < 1:
            raise SchemeError("error: at least 1 argument")
        msg = args[0]
        if not isinstance(msg, str):
            raise SchemeError("error: first argument must be a string")
        parts = [msg]
        for irr in args[1:]:
            parts.append(' ')
            parts.append(display_repr(irr, True))
        raise SchemeError(''.join(parts))

    # number->string
    def bi_num2str(args):
        if len(args) < 1 or len(args) > 2:
            raise SchemeError("number->string: 1 or 2 arguments")
        n = _int(args[0], 'number->string')
        radix = 10
        if len(args) == 2:
            radix = _int(args[1], 'number->string')
            if radix not in (2, 8, 10, 16):
                raise SchemeError("number->string: invalid radix")
        if n == 0:
            return "0"
        neg = n < 0
        n = abs(n)
        digits = "0123456789abcdef"
        parts = []
        while n > 0:
            parts.append(digits[n % radix])
            n //= radix
        if neg:
            parts.append('-')
        return ''.join(reversed(parts))

    # Register all builtins
    builtins = {
        '+': bi_add, '*': bi_mul, '-': bi_sub,
        'quotient': bi_quotient, 'remainder': bi_remainder, 'modulo': bi_modulo,
        '=': _make_cmp(lambda a, b: a == b, '='),
        '<': _make_cmp(lambda a, b: a < b, '<'),
        '>': _make_cmp(lambda a, b: a > b, '>'),
        '<=': _make_cmp(lambda a, b: a <= b, '<='),
        '>=': _make_cmp(lambda a, b: a >= b, '>='),
        'cons': bi_cons, 'car': bi_car, 'cdr': bi_cdr, 'list': bi_list,
        'null?': bi_null, 'pair?': bi_pair, 'list?': bi_listp,
        'length': bi_length, 'append': bi_append, 'reverse': bi_reverse,
        'eq?': bi_eq, 'equal?': bi_equal, 'not': bi_not,
        'number?': bi_number_p, 'symbol?': bi_symbol_p,
        'string?': bi_string_p, 'procedure?': bi_procedure_p,
        'string-append': bi_string_append,
        'display': bi_display, 'newline': bi_newline,
        'error': bi_error,
        'number->string': bi_num2str,
    }

    for name, func in builtins.items():
        env.bindings[Symbol(name)] = Builtin(func, name)

    return env


# ─── Public API ───────────────────────────────────────────────────────────────

def run(source: str) -> str:
    output = []
    try:
        tokens = _tokenize(source)
        forms = _parse_all(tokens)
        global_env = _make_builtins(output)
        for form in forms:
            trampoline(form, global_env)
        return ''.join(output)
    except SchemeError as e:
        e.output = ''.join(output)
        raise
    except RecursionError:
        raise SchemeError("stack overflow", ''.join(output))
    except Exception as e:
        raise SchemeError(str(e), ''.join(output))
