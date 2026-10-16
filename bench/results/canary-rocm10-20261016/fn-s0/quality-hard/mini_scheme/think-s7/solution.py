import sys
import re
import threading

try:
    sys.set_int_max_str_digits(0)
except (AttributeError, ValueError):
    pass

# ─── Exception ────────────────────────────────────────────────────────────────

class SchemeError(Exception):
    def __init__(self, message, output=''):
        super().__init__(message)
        self.output = output

# ─── Data Types ───────────────────────────────────────────────────────────────

class Symbol:
    __slots__ = ('name',)
    def __init__(self, name): self.name = name
    def __repr__(self): return self.name
    def __eq__(self, other): return isinstance(other, Symbol) and self.name == other.name
    def __hash__(self): return hash(('Sym', self.name))

class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr): self.car = car; self.cdr = cdr

class _Nil: pass
NIL = _Nil()

class _Unspecified: pass
UNSPECIFIED = _Unspecified()

class _Uninitialized: pass
UNINITIALIZED = _Uninitialized()

class Closure:
    __slots__ = ('params', 'rest', 'body', 'env')
    def __init__(self, params, rest, body, env):
        self.params = params; self.rest = rest; self.body = body; self.env = env

class Builtin:
    __slots__ = ('func', 'name')
    def __init__(self, func, name): self.func = func; self.name = name

# ─── Environment ──────────────────────────────────────────────────────────────

class Frame:
    __slots__ = ('vars', 'parent')
    def __init__(self, parent=None):
        self.vars = {}; self.parent = parent
    def lookup(self, name):
        f = self
        while f is not None:
            if name in f.vars:
                v = f.vars[name]
                if v is UNINITIALIZED:
                    raise SchemeError("uninitialized variable: " + name.name)
                return v
            f = f.parent
        raise SchemeError("unbound variable: " + name.name)
    def define(self, name, val): self.vars[name] = val
    def assign(self, name, val):
        f = self
        while f is not None:
            if name in f.vars: f.vars[name] = val; return
            f = f.parent
        raise SchemeError("set!: unbound variable: " + name.name)

# ─── Reader ───────────────────────────────────────────────────────────────────

_INT_RE = re.compile(r'^[+-]?[0-9]+$')

def _tokenize(src):
    tokens = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c in ' \t\n\r':
            i += 1
        elif c == ';':
            while i < n and src[i] != '\n': i += 1
        elif c == '(':
            tokens.append('('); i += 1
        elif c == ')':
            tokens.append(')'); i += 1
        elif c == '"':
            i += 1; parts = []
            while i < n and src[i] != '"':
                if src[i] == '\\':
                    i += 1
                    if i >= n: raise SchemeError("unterminated string")
                    ec = src[i]
                    if ec == '"': parts.append('"')
                    elif ec == '\\': parts.append('\\')
                    elif ec == 'n': parts.append('\n')
                    else: raise SchemeError("bad escape: \\" + ec)
                    i += 1
                else:
                    parts.append(src[i]); i += 1
            if i >= n: raise SchemeError("unterminated string")
            i += 1
            tokens.append(('str', ''.join(parts)))
        elif c == "'":
            tokens.append("'"); i += 1
        else:
            start = i
            while i < n and src[i] not in ' \t\n\r()";\'': i += 1
            tokens.append(src[start:i])
    return tokens

def _parse_all(tokens):
    pos = [0]
    forms = []
    while pos[0] < len(tokens):
        forms.append(_parse_form(tokens, pos))
    return forms

def _parse_form(tokens, pos):
    if pos[0] >= len(tokens): raise SchemeError("unexpected end of input")
    tok = tokens[pos[0]]
    if tok == '(':
        pos[0] += 1
        return _parse_list(tokens, pos)
    if tok == ')': raise SchemeError("unexpected )")
    if tok == "'":
        pos[0] += 1
        datum = _parse_form(tokens, pos)
        return Pair(Symbol('quote'), Pair(datum, NIL))
    if isinstance(tok, tuple):
        pos[0] += 1
        return tok[1]
    pos[0] += 1
    return _parse_atom(tok)

def _parse_list(tokens, pos):
    items = []; dot_cdr = None; has_dot = False
    while True:
        if pos[0] >= len(tokens): raise SchemeError("unbalanced (")
        tok = tokens[pos[0]]
        if tok == ')':
            pos[0] += 1; break
        if tok == '.' and not has_dot:
            pos[0] += 1; has_dot = True
            if pos[0] >= len(tokens) or tokens[pos[0]] == ')':
                raise SchemeError("bad dotted pair")
            dot_cdr = _parse_form(tokens, pos)
            if pos[0] >= len(tokens) or tokens[pos[0]] != ')':
                raise SchemeError("bad dotted pair")
            pos[0] += 1; break
        items.append(_parse_form(tokens, pos))
    if has_dot:
        if not items: raise SchemeError("dot without preceding elements")
        result = dot_cdr
        for it in reversed(items): result = Pair(it, result)
        return result
    result = NIL
    for it in reversed(items): result = Pair(it, result)
    return result

def _parse_atom(tok):
    if tok == '#t': return True
    if tok == '#f': return False
    if tok.startswith('#'): raise SchemeError("bad token: " + tok)
    if _INT_RE.match(tok):
        return int(tok)
    return Symbol(tok)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _to_list(s):
    r = []; cur = s
    while isinstance(cur, Pair): r.append(cur.car); cur = cur.cdr
    if cur is not NIL: raise SchemeError("improper list")
    return r

def _to_list_opt(s):
    r = []; cur = s
    while isinstance(cur, Pair): r.append(cur.car); cur = cur.cdr
    return r if cur is NIL else None

def _list_to_scheme(items):
    r = NIL
    for it in reversed(items): r = Pair(it, r)
    return r

def _is_true(v): return v is not False

def _is_proper_list(v):
    while isinstance(v, Pair): v = v.cdr
    return v is NIL

def _is_number(v): return isinstance(v, int) and not isinstance(v, bool)

def _int_to_str(n):
    if n == 0: return "0"
    neg = n < 0; n = -n if neg else n
    digits = []
    while n: digits.append(chr(48 + n % 10)); n //= 10
    return ('-' if neg else '') + ''.join(reversed(digits))

def _int_to_radix(n, radix):
    if n == 0: return "0"
    neg = n < 0; n = -n if neg else n
    digits = []
    while n: digits.append("0123456789abcdef"[n % radix]); n //= radix
    return ('-' if neg else '') + ''.join(reversed(digits))

# ─── Display / Write ──────────────────────────────────────────────────────────

def _display_repr(x):
    return _repr_val(x, False)

def _write_repr(x):
    return _repr_val(x, True)

def _repr_val(x, wr):
    if isinstance(x, bool): return "#t" if x else "#f"
    if isinstance(x, int): return _int_to_str(x)
    if isinstance(x, str):
        if wr:
            return '"' + x.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'
        return x
    if isinstance(x, Symbol): return x.name
    if x is NIL: return "()"
    if isinstance(x, _Unspecified): return ""
    if isinstance(x, (Closure, Builtin)): return "#<procedure>"
    if isinstance(x, Pair): return _repr_pair(x, wr)
    return ""

def _repr_pair(p, wr):
    parts = []; cur = p
    while isinstance(cur, Pair):
        parts.append(_repr_val(cur.car, wr)); cur = cur.cdr
    if cur is NIL:
        return "(" + " ".join(parts) + ")"
    parts.append(". " + _repr_val(cur, wr))
    return "(" + " ".join(parts) + ")"

# ─── Output buffer ────────────────────────────────────────────────────────────

_output_buf = []

# ─── Evaluator ────────────────────────────────────────────────────────────────

class _TailCall:
    __slots__ = ('expr', 'env')
    def __init__(self, expr, env): self.expr = expr; self.env = env

def eval_expr(expr, env):
    while True:
        r = _eval(expr, env)
        if isinstance(r, _TailCall): expr, env = r.expr, r.env
        else: return r

def _eval(expr, env):
    # Self-evaluating
    if isinstance(expr, bool): return expr
    if isinstance(expr, int): return expr
    if isinstance(expr, str): return expr
    if isinstance(expr, Symbol): return env.lookup(expr)
    if x is NIL: raise SchemeError("empty form")
    if isinstance(expr, _Unspecified): return expr
    if isinstance(expr, (Closure, Builtin)): return expr
    if not isinstance(expr, Pair): return expr

    head = expr.car
    if isinstance(head, Symbol):
        hn = head.name
        if hn == 'quote': return _do_quote(expr)
        if hn == 'if': return _do_if(expr, env)
        if hn == 'lambda': return _do_lambda(expr, env)
        if hn == 'define': return _do_define(expr, env)
        if hn == 'set!': return _do_set(expr, env)
        if hn == 'begin': return _do_begin(expr, env)
        if hn == 'cond': return _do_cond(expr, env)
        if hn == 'and': return _do_and(expr, env)
        if hn == 'or': return _do_or(expr, env)
        if hn == 'let': return _do_let(expr, env)
        if hn == 'let*': return _do_let_star(expr, env)
        if hn == 'letrec': return _do_letrec(expr, env)
        if hn == 'apply': return _do_apply(expr, env)

    # Application
    return _do_apply_general(expr, env)

def _do_quote(expr):
    if expr.cdr is NIL: raise SchemeError("malformed quote")
    return expr.cdr.car

def _do_if(expr, env):
    rest = expr.cdr
    if rest is NIL or rest.cdr is NIL: raise SchemeError("malformed if")
    test_v = eval_expr(rest.car, env)
    if _is_true(test_v):
        return _eval(rest.cdr.car, env)
    else:
        alt = rest.cdr.cdr
        if alt is NIL: return UNSPECIFIED
        return _eval(alt.car, env)

def _do_lambda(expr, env):
    if expr.cdr is NIL: raise SchemeError("malformed lambda")
    formals = expr.cdr.car
    body = _to_list(expr.cdr.cdr)
    if not body: raise SchemeError("empty body")
    params, rest = _parse_formals(formals)
    return Closure(params, rest, body, env)

def _parse_formals(formals):
    if isinstance(formals, Symbol): return None, formals
    params = []; cur = formals
    while isinstance(cur, Pair):
        if not isinstance(cur.car, Symbol): raise SchemeError("bad formals")
        params.append(cur.car); cur = cur.cdr
    if cur is NIL: return params, None
    if isinstance(cur, Symbol): return params, cur
    raise SchemeError("bad formals")

def _do_define(expr, env):
    if expr.cdr is NIL: raise SchemeError("malformed define")
    target = expr.cdr.car
    if isinstance(target, Symbol):
        rest = expr.cdr.cdr
        if rest is NIL: raise SchemeError("malformed define")
        val = eval_expr(rest.car, env)
        env.define(target, val)
        return UNSPECIFIED
    elif isinstance(target, Pair):
        name = target.car
        if not isinstance(name, Symbol): raise SchemeError("malformed define")
        formals = target.cdr
        body = _to_list(expr.cdr.cdr)
        if not body: raise SchemeError("empty body")
        params, rest = _parse_formals(formals)
        env.define(name, Closure(params, rest, body, env))
        return UNSPECIFIED
    raise SchemeError("malformed define")

def _do_set(expr, env):
    if expr.cdr is NIL or expr.cdr.cdr is NIL: raise SchemeError("malformed set!")
    name = expr.cdr.car
    if not isinstance(name, Symbol): raise SchemeError("malformed set!")
    val = eval_expr(expr.cdr.cdr.car, env)
    env.assign(name, val)
    return UNSPECIFIED

def _do_begin(expr, env):
    forms = _to_list(expr.cdr)
    if not forms: raise SchemeError("malformed begin")
    for f in forms[:-1]: eval_expr(f, env)
    return _eval(forms[-1], env)

def _do_cond(expr, env):
    clauses = _to_list(expr.cdr)
    for clause in clauses:
        if not isinstance(clause, Pair): raise SchemeError("malformed cond clause")
        test = clause.car
        if isinstance(test, Symbol) and test.name == 'else':
            body = _to_list(clause.cdr)
            if not body: return UNSPECIFIED
            for f in body[:-1]: eval_expr(f, env)
            return _eval(body[-1], env)
        tv = eval_expr(test, env)
        if _is_true(tv):
            body = _to_list(clause.cdr)
            if not body: return tv
            for f in body[:-1]: eval_expr(f, env)
            return _eval(body[-1], env)
    return UNSPECIFIED

def _do_and(expr, env):
    exprs = _to_list(expr.cdr)
    if not exprs: return True
    for e in exprs[:-1]:
        v = eval_expr(e, env)
        if not _is_true(v): return False
    return _eval(exprs[-1], env)

def _do_or(expr, env):
    exprs = _to_list(expr.cdr)
    if not exprs: return False
    for e in exprs[:-1]:
        v = eval_expr(e, env)
        if _is_true(v): return v
    return _eval(exprs[-1], env)

def _do_let(expr, env):
    if expr.cdr is NIL: raise SchemeError("malformed let")
    second = expr.cdr.car
    if isinstance(second, Symbol):
        # Named let
        return _do_named_let(second, expr.cdr.cdr, env)
    else:
        bindings_f = second
        body = _to_list(expr.cdr.cdr)
        if not body: raise SchemeError("empty body")
        bindings = _to_list(bindings_f)
        for b in bindings:
            if not isinstance(b, Pair) or b.cdr is NIL:
                raise SchemeError("malformed let binding")
        inits = [eval_expr(b.cdr.car, env) for b in bindings]
        nf = Frame(parent=env)
        for b, v in zip(bindings, inits): nf.vars[b.car] = v
        nf, body = _process_internal(body, nf)
        for f in body[:-1]: eval_expr(f, nf)
        return _eval(body[-1], nf)

def _do_named_let(name, rest, env):
    if rest is NIL: raise SchemeError("malformed named let")
    bindings_f = rest.car
    body = _to_list(rest.cdr)
    if not body: raise SchemeError("empty body")
    bindings = _to_list(bindings_f)
    for b in bindings:
        if not isinstance(b, Pair) or b.cdr is NIL:
            raise SchemeError("malformed let binding")
    inits = [eval_expr(b.cdr.car, env) for b in bindings]
    params = [b.car for b in bindings]
    frame = Frame(parent=env)
    frame.vars[name] = UNINITIALIZED
    proc = Closure(params, None, body, frame)
    frame.vars[name] = proc
    nf = _make_call_env(proc, inits)
    nf, b = _process_internal(proc.body, nf)
    for f in b[:-1]: eval_expr(f, nf)
    return _eval(b[-1], nf)

def _do_let_star(expr, env):
    if expr.cdr is NIL: raise SchemeError("malformed let*")
    bindings_f = expr.cdr.car
    body = _to_list(expr.cdr.cdr)
    if not body: raise SchemeError("empty body")
    bindings = _to_list(bindings_f)
    for b in bindings:
        if not isinstance(b, Pair) or b.cdr is NIL:
            raise SchemeError("malformed let* binding")
    cur_env = env
    for b in bindings:
        v = eval_expr(b.cdr.car, cur_env)
        nf = Frame(parent=cur_env)
        nf.vars[b.car] = v
        cur_env = nf
    cur_env, body = _process_internal(body, cur_env)
    for f in body[:-1]: eval_expr(f, cur_env)
    return _eval(body[-1], cur_env)

def _do_letrec(expr, env):
    if expr.cdr is NIL: raise SchemeError("malformed letrec")
    bindings_f = expr.cdr.car
    body = _to_list(expr.cdr.cdr)
    if not body: raise SchemeError("empty body")
    bindings = _to_list(bindings_f)
    for b in bindings:
        if not isinstance(b, Pair) or b.cdr is NIL:
            raise SchemeError("malformed letrec binding")
    nf = Frame(parent=env)
    for b in bindings: nf.vars[b.car] = UNINITIALIZED
    for b in bindings:
        v = eval_expr(b.cdr.car, nf)
        nf.vars[b.car] = v
    nf, body = _process_internal(body, nf)
    for f in body[:-1]: eval_expr(f, nf)
    return _eval(body[-1], nf)

def _process_internal(body, env):
    names = []
    for form in body:
        if isinstance(form, Pair) and isinstance(form.car, Symbol) and form.car.name == 'define':
            n = _define_name(form)
            if n is not None: names.append(n)
    if not names: return env, body
    nf = Frame(parent=env)
    for n in names: nf.vars[n] = UNINITIALIZED
    return nf, body

def _define_name(form):
    if form.cdr is NIL: return None
    t = form.cdr.car
    if isinstance(t, Symbol): return t
    if isinstance(t, Pair) and isinstance(t.car, Symbol): return t.car
    return None

def _make_call_env(closure, args):
    nf = Frame(parent=closure.env)
    params, rest = closure.params, closure.rest
    if params is None:
        nf.vars[rest] = _list_to_scheme(args)
    elif rest is None:
        if len(args) != len(params):
            raise SchemeError("wrong number of arguments")
        for p, a in zip(params, args): nf.vars[p] = a
    else:
        if len(args) < len(params):
            raise SchemeError("too few arguments")
        for p, a in zip(params, args): nf.vars[p] = a
        nf.vars[rest] = _list_to_scheme(args[len(params):])
    return nf

def _call_closure_tail(closure, args):
    nf = _make_call_env(closure, args)
    nf, body = _process_internal(closure.body, nf)
    for f in body[:-1]: eval_expr(f, nf)
    return _eval(body[-1], nf)

def _do_apply(expr, env):
    args_f = _to_list(expr.cdr)
    if len(args_f) < 2: raise SchemeError("apply: too few arguments")
    f = eval_expr(args_f[0], env)
    if not isinstance(f, (Closure, Builtin)): raise SchemeError("apply: not a procedure")
    regular = [eval_expr(a, env) for a in args_f[1:-1]]
    last = eval_expr(args_f[-1], env)
    if not _is_proper_list(last): raise SchemeError("apply: last arg not a proper list")
    all_args = regular + _to_list(last)
    if isinstance(f, Builtin): return f.func(all_args)
    return _call_closure_tail(f, all_args)

def _do_apply_general(expr, env):
    proc = eval_expr(expr.car, env)
    args = []
    cur = expr.cdr
    while isinstance(cur, Pair):
        args.append(eval_expr(cur.car, env)); cur = cur.cdr
    if cur is not NIL: raise SchemeError("dotted form in application")
    if not isinstance(proc, (Closure, Builtin)):
        raise SchemeError("not a procedure: " + _display_repr(proc))
    if isinstance(proc, Builtin): return proc.func(args)
    return _call_closure_tail(proc, args)

# ─── Builtins ─────────────────────────────────────────────────────────────────

def _make_global_env():
    g = Frame()
    def def_b(name, func):
        g.vars[Symbol(name)] = Builtin(func, name)

    # Arithmetic
    def b_add(args):
        for a in args:
            if not _is_number(a): raise SchemeError("+: not a number")
        return sum(args) if args else 0
    def b_mul(args):
        for a in args:
            if not _is_number(a): raise SchemeError("*: not a number")
        r = 1
        for a in args: r *= a
        return r
    def b_sub(args):
        if len(args) < 1: raise SchemeError("-: too few arguments")
        for a in args:
            if not _is_number(a): raise SchemeError("-: not a number")
        r = args[0]
        for a in args[1:]: r -= a
        return r
    def b_quotient(args):
        if len(args) != 2: raise SchemeError("quotient: need 2 args")
        a, b = args
        if not _is_number(a) or not _is_number(b): raise SchemeError("quotient: not a number")
        if b == 0: raise SchemeError("division by zero")
        q = abs(a) // abs(b)
        if (a < 0) != (b < 0): q = -q
        return q
    def b_remainder(args):
        if len(args) != 2: raise SchemeError("remainder: need 2 args")
        a, b = args
        if not _is_number(a) or not _is_number(b): raise SchemeError("remainder: not a number")
        if b == 0: raise SchemeError("division by zero")
        return a - b * b_quotient([a, b])
    def b_modulo(args):
        if len(args) != 2: raise SchemeError("modulo: need 2 args")
        a, b = args
        if not _is_number(a) or not _is_number(b): raise SchemeError("modulo: not a number")
        if b == 0: raise SchemeError("division by zero")
        r = a % b
        if r != 0 and (r < 0) != (b < 0): r += b
        return r
    def _make_cmp(op):
        def f(args):
            if not args: raise SchemeError("comparison: no arguments")
            for a in args:
                if not _is_number(a): raise SchemeError("comparison: not a number")
            for i in range(len(args) - 1):
                if not op(args[i], args[i+1]): return False
            return True
        return f

    def_b('+', b_add); def_b('*', b_mul); def_b('-', b_sub)
    def_b('quotient', b_quotient); def_b('remainder', b_remainder); def_b('modulo', b_modulo)
    def_b('=', _make_cmp(lambda a, b: a == b))
    def_b('<', _make_cmp(lambda a, b: a < b))
    def_b('>', _make_cmp(lambda a, b: a > b))
    def_b('<=', _make_cmp(lambda a, b: a <= b))
    def_b('>=', _make_cmp(lambda a, b: a >= b))

    def b_n2s(args):
        if len(args) < 1 or len(args) > 2: raise SchemeError("number->string: bad arity")
        n = args[0]
        if not _is_number(n): raise SchemeError("number->string: not a number")
        radix = 10
        if len(args) == 2:
            radix = args[1]
            if not _is_number(radix) or radix not in (2, 8, 10, 16):
                raise SchemeError("number->string: bad radix")
        return _int_to_radix(n, radix)
    def_b('number->string', b_n2s)

    # Pairs and lists
    def b_cons(args):
        if len(args) != 2: raise SchemeError("cons: need 2 args")
        return Pair(args[0], args[1])
    def b_car(args):
        if len(args) != 1: raise SchemeError("car: need 1 arg")
        if not isinstance(args[0], Pair): raise SchemeError("car: not a pair")
        return args[0].car
    def b_cdr(args):
        if len(args) != 1: raise SchemeError("cdr: need 1 arg")
        if not isinstance(args[0], Pair): raise SchemeError("cdr: not a pair")
        return args[0].cdr
    def b_list(args): return _list_to_scheme(args)
    def b_null(args):
        if len(args) != 1: raise SchemeError("null?: need 1 arg")
        return args[0] is NIL
    def b_pair(args):
        if len(args) != 1: raise SchemeError("pair?: need 1 arg")
        return isinstance(args[0], Pair)
    def b_listp(args):
        if len(args) != 1: raise SchemeError("list?: need 1 arg")
        return _is_proper_list(args[0])
    def b_length(args):
        if len(args) != 1: raise SchemeError("length: need 1 arg")
        n = 0; cur = args[0]
        while isinstance(cur, Pair): n += 1; cur = cur.cdr
        if cur is not NIL: raise SchemeError("length: not a proper list")
        return n
    def b_append(args):
        if not args: return NIL
        if len(args) == 1:
            if not _is_proper_list(args[0]): raise SchemeError("append: not a proper list")
            return args[0]
        for a in args[:-1]:
            if not _is_proper_list(a): raise SchemeError("append: not a proper list")
        result = args[-1]
        for a in reversed(args[:-1]):
            items = _to_list(a)
            for it in reversed(items): result = Pair(it, result)
        return result
    def b_reverse(args):
        if len(args) != 1: raise SchemeError("reverse: need 1 arg")
        items = _to_list(args[0])
        return _list_to_scheme(list(reversed(items)))
    def b_apply(args):
        if len(args) < 2: raise SchemeError("apply: too few arguments")
        f = args[0]
        if not isinstance(f, (Closure, Builtin)): raise SchemeError("apply: not a procedure")
        regular = args[1:-1]
        last = args[-1]
        if not _is_proper_list(last): raise SchemeError("apply: last arg not a proper list")
        all_args = list(regular) + _to_list(last)
        if isinstance(f, Builtin): return f.func(all_args)
        return _call_closure_tail(f, all_args)

    def_b('cons', b_cons); def_b('car', b_car); def_b('cdr', b_cdr)
    def_b('list', b_list); def_b('null?', b_null); def_b('pair?', b_pair)
    def_b('list?', b_listp); def_b('length', b_length)
    def_b('append', b_append); def_b('reverse', b_reverse); def_b('apply', b_apply)

    # Equality / predicates
    def b_eq(args):
        if len(args) != 2: raise SchemeError("eq?: need 2 args")
        a, b = args
        if isinstance(a, bool) or isinstance(b, bool): return a is b
        if isinstance(a, int) and isinstance(b, int): return a == b
        if a is NIL and b is NIL: return True
        if isinstance(a, Symbol) and isinstance(b, Symbol): return a.name == b.name
        return a is b
    def b_equal(args):
        if len(args) != 2: raise SchemeError("equal?: need 2 args")
        return _equal(args[0], args[1])
    def b_not(args):
        if len(args) != 1: raise SchemeError("not: need 1 arg")
        return not _is_true(args[0])
    def b_numberp(args):
        if len(args) != 1: raise SchemeError("number?: need 1 arg")
        return _is_number(args[0])
    def b_symbolp(args):
        if len(args) != 1: raise SchemeError("symbol?: need 1 arg")
        return isinstance(args[0], Symbol)
    def b_stringp(args):
        if len(args) != 1: raise SchemeError("string?: need 1 arg")
        return isinstance(args[0], str)
    def b_procp(args):
        if len(args) != 1: raise SchemeError("procedure?: need 1 arg")
        return isinstance(args[0], (Closure, Builtin))
    def b_str_append(args):
        for a in args:
            if not isinstance(a, str): raise SchemeError("string-append: not a string")
        return ''.join(args)

    def_b('eq?', b_eq); def_b('equal?', b_equal); def_b('not', b_not)
    def_b('number?', b_numberp); def_b('symbol?', b_symbolp)
    def_b('string?', b_stringp); def_b('procedure?', b_procp)
    def_b('string-append', b_str_append)

    # Output
    def b_display(args):
        if len(args) != 1: raise SchemeError("display: need 1 arg")
        _output_buf.append(_display_repr(args[0]))
        return UNSPECIFIED
    def b_newline(args):
        if len(args) != 0: raise SchemeError("newline: 0 args expected")
        _output_buf.append("\n")
        return UNSPECIFIED
    def b_error(args):
        if not args: raise SchemeError("error: no arguments")
        msg = args[0]
        if not isinstance(msg, str):
            raise SchemeError(str(msg))
        parts = [msg]
        for irr in args[1:]:
            parts.append(" "); parts.append(_write_repr(irr))
        raise SchemeError("".join(parts))

    def_b('display', b_display); def_b('newline', b_newline); def_b('error', b_error)

    return g

def _equal(a, b):
    stack = [(a, b)]
    while stack:
        x, y = stack.pop()
        if isinstance(x, Pair) and isinstance(y, Pair):
            stack.append((x.cdr, y.cdr)); stack.append((x.car, y.car))
        elif isinstance(x, bool) or isinstance(y, bool):
            if x is not y: return False
        elif isinstance(x, int) and isinstance(y, int):
            if x != y: return False
        elif isinstance(x, str) and isinstance(y, str):
            if x != y: return False
        elif isinstance(x, Symbol) and isinstance(y, Symbol):
            if x.name != y.name: return False
        elif x is NIL and y is NIL:
            pass
        elif x is y:
            pass
        else:
            return False
    return True

# ─── Main API ─────────────────────────────────────────────────────────────────

def run(source):
    global _output_buf
    result = [None]
    error = [None]

    def target():
        global _output_buf
        _output_buf = []
        try:
            tokens = _tokenize(source)
            forms = _parse_all(tokens)
        except SchemeError as e:
            e.output = ''
            error[0] = e; return
        except Exception as e:
            error[0] = SchemeError(str(e)); error[0].output = ''; return

        env = _make_global_env()
        try:
            for form in forms:
                eval_expr(form, env)
            result[0] = ''.join(_output_buf)
        except SchemeError as e:
            e.output = ''.join(_output_buf)
            error[0] = e
        except RecursionError:
            e = SchemeError("stack overflow"); e.output = ''.join(_output_buf); error[0] = e
        except Exception as e:
            err = SchemeError(str(e)); err.output = ''.join(_output_buf); error[0] = err

    old_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(1000000)
    try:
        old_ss = threading.stack_size(256 * 1024 * 1024)
    except Exception:
        old_ss = None
    t = threading.Thread(target=target)
    t.start()
    t.join()
    sys.setrecursionlimit(old_limit)
    if old_ss is not None:
        try: threading.stack_size(old_ss)
        except Exception: pass

    if error[0] is not None:
        raise error[0]
    return result[0]
