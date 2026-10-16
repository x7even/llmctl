"""A Scheme interpreter for a small, precisely specified subset."""

import sys
import re
import threading

if hasattr(sys, 'set_int_max_str_digits'):
    sys.set_int_max_str_digits(0)

sys.setrecursionlimit(500000)

# ─── Exception ────────────────────────────────────────────────────────────────

class SchemeError(Exception):
    def __init__(self, msg, output=''):
        super().__init__(msg)
        self.output = output

# ─── Data Types ───────────────────────────────────────────────────────────────

class Symbol:
    __slots__ = ('name',)
    def __init__(self, name): self.name = name
    def __repr__(self): return self.name

class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr): self.car = car; self.cdr = cdr

class _Nil:
    def __repr__(self): return '()'
NIL = _Nil()

class _Unspecified:
    def __repr__(self): return ''
UNSPECIFIED = _Unspecified()

class _Uninitialized:
    pass
UNINITIALIZED = _Uninitialized()

class Closure:
    __slots__ = ('formals', 'body', 'env')
    def __init__(self, formals, body, env):
        self.formals = formals; self.body = body; self.env = env

class Builtin:
    __slots__ = ('name', 'func')
    def __init__(self, name, func): self.name = name; self.func = func

class TailCall:
    __slots__ = ('proc', 'args')
    def __init__(self, proc, args): self.proc = proc; self.args = args

# ─── Environment ──────────────────────────────────────────────────────────────

class Env:
    __slots__ = ('vars', 'parent')
    def __init__(self, parent=None):
        self.vars = {}; self.parent = parent

    def lookup(self, name):
        env = self
        while env is not None:
            if name in env.vars:
                val = env.vars[name]
                if isinstance(val, _Uninitialized):
                    raise SchemeError(f"uninitialized variable: {name}")
                return val
            env = env.parent
        raise SchemeError(f"unbound variable: {name}")

    def define(self, name, value):
        self.vars[name] = value

    def set(self, name, value):
        env = self
        while env is not None:
            if name in env.vars:
                env.vars[name] = value; return
            env = env.parent
        raise SchemeError(f"set!: unbound variable: {name}")

# ─── Reader ───────────────────────────────────────────────────────────────────

_INT_RE = re.compile(r'^[+-]?[0-9]+$')

def _tokenize(source):
    tokens = []; i = 0; n = len(source)
    while i < n:
        c = source[i]
        if c in ' \t\n\r':
            i += 1
        elif c == ';':
            while i < n and source[i] != '\n': i += 1
        elif c == '(':
            tokens.append(('(', None)); i += 1
        elif c == ')':
            tokens.append((')', None)); i += 1
        elif c == '"':
            i += 1; s = []
            while i < n and source[i] != '"':
                if source[i] == '\\':
                    i += 1
                    if i >= n: raise SchemeError("unterminated string escape")
                    nc = source[i]
                    if nc == '"': s.append('"')
                    elif nc == '\\': s.append('\\')
                    elif nc == 'n': s.append('\n')
                    else: raise SchemeError(f"invalid escape: \\{nc}")
                else:
                    s.append(source[i])
                i += 1
            if i >= n: raise SchemeError("unterminated string")
            i += 1
            tokens.append(('string', ''.join(s)))
        elif c == "'":
            tokens.append(("'", None)); i += 1
        else:
            start = i
            while i < n and source[i] not in ' \t\n\r()";\'': i += 1
            tokens.append(('word', source[start:i]))
    return tokens

def _parse_all(tokens):
    forms = []; pos = [0]
    while pos[0] < len(tokens):
        forms.append(_parse_form(tokens, pos))
    return forms

def _parse_form(tokens, pos):
    if pos[0] >= len(tokens): raise SchemeError("unexpected end of input")
    tt, tv = tokens[pos[0]]
    if tt == '(':
        pos[0] += 1; return _parse_list(tokens, pos)
    elif tt == ')':
        raise SchemeError("unexpected )")
    elif tt == "'":
        pos[0] += 1; datum = _parse_form(tokens, pos)
        return Pair(Symbol('quote'), Pair(datum, NIL))
    elif tt == 'string':
        pos[0] += 1; return tv
    elif tt == 'word':
        pos[0] += 1; return _parse_word(tv)
    raise SchemeError("unexpected token")

def _parse_list(tokens, pos):
    elements = []
    while True:
        if pos[0] >= len(tokens): raise SchemeError("unbalanced (")
        tt, tv = tokens[pos[0]]
        if tt == ')':
            pos[0] += 1; break
        elif tt == 'word' and tv == '.':
            if not elements: raise SchemeError("dot without preceding element")
            pos[0] += 1
            dot_val = _parse_form(tokens, pos)
            if pos[0] >= len(tokens) or tokens[pos[0]][0] != ')':
                raise SchemeError("expected ) after dotted value")
            pos[0] += 1
            result = dot_val
            for e in reversed(elements): result = Pair(e, result)
            return result
        else:
            elements.append(_parse_form(tokens, pos))
    result = NIL
    for e in reversed(elements): result = Pair(e, result)
    return result

def _parse_word(word):
    if word == '#t': return True
    if word == '#f': return False
    if word.startswith('#'): raise SchemeError(f"invalid token: {word}")
    if _INT_RE.match(word): return int(word)
    return Symbol(word)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _is_true(x): return x is not False
def _is_int(x): return isinstance(x, int) and not isinstance(x, bool)

def _cdr_to_list(p):
    r = []
    while isinstance(p, Pair): r.append(p.car); p = p.cdr
    if not isinstance(p, _Nil): raise SchemeError("improper list")
    return r

def _to_python_list(x):
    r = []
    while isinstance(x, Pair): r.append(x.car); x = x.cdr
    if not isinstance(x, _Nil): raise SchemeError("not a proper list")
    return r

def _list_to_scheme(items):
    r = NIL
    for it in reversed(items): r = Pair(it, r)
    return r

def _analyze_formals(formals):
    if isinstance(formals, Symbol): return None, formals
    required = []; rest = None; cur = formals
    while isinstance(cur, Pair):
        if isinstance(cur.cdr, _Nil): required.append(cur.car); break
        elif isinstance(cur.cdr, Symbol): required.append(cur.car); rest = cur.cdr; break
        else: required.append(cur.car); cur = cur.cdr
    return required, rest

def _check_arity(formals, args):
    if isinstance(formals, Symbol): return
    required, rest = _analyze_formals(formals)
    if rest is None:
        if len(args) != len(required):
            raise SchemeError(f"wrong number of arguments: expected {len(required)}, got {len(args)}")
    else:
        if len(args) < len(required):
            raise SchemeError(f"wrong number of arguments: expected at least {len(required)}, got {len(args)}")

def _make_call_env(formals, args, parent):
    env = Env(parent)
    if isinstance(formals, Symbol):
        env.define(formals.name, _list_to_scheme(args))
    else:
        required, rest = _analyze_formals(formals)
        for i, s in enumerate(required): env.define(s.name, args[i])
        if rest is not None: env.define(rest.name, _list_to_scheme(args[len(required):]))
    return env

def _is_define(form):
    return isinstance(form, Pair) and isinstance(form.car, Symbol) and form.car.name == 'define'

def _define_name(form):
    t = form.cdr.car
    if isinstance(t, Symbol): return t.name
    if isinstance(t, Pair) and isinstance(t.car, Symbol): return t.car.name
    raise SchemeError("invalid define form")

# ─── Display / Write ──────────────────────────────────────────────────────────

def _display_repr(x):
    if isinstance(x, bool): return '#t' if x else '#f'
    if isinstance(x, int): return str(x)
    if isinstance(x, str): return x
    if isinstance(x, Symbol): return x.name
    if isinstance(x, _Nil): return '()'
    if isinstance(x, _Unspecified): return ''
    if isinstance(x, Pair): return _display_pair(x)
    if isinstance(x, (Closure, Builtin)): return '#<procedure>'
    return ''

def _display_pair(p):
    parts = []; cur = p
    while isinstance(cur, Pair): parts.append(_display_repr(cur.car)); cur = cur.cdr
    if isinstance(cur, _Nil): return '(' + ' '.join(parts) + ')'
    return '(' + ' '.join(parts) + ' . ' + _display_repr(cur) + ')'

def _write_repr(x):
    if isinstance(x, str):
        return '"' + x.replace('\\','\\\\').replace('"','\\"').replace('\n','\\n') + '"'
    if isinstance(x, Pair): return _write_pair(x)
    return _display_repr(x)

def _write_pair(p):
    parts = []; cur = p
    while isinstance(cur, Pair): parts.append(_write_repr(cur.car)); cur = cur.cdr
    if isinstance(cur, _Nil): return '(' + ' '.join(parts) + ')'
    return '(' + ' '.join(parts) + ' . ' + _write_repr(cur) + ')'

# ─── Evaluator ────────────────────────────────────────────────────────────────

def _eval_body(forms, env, tail):
    if not forms: raise SchemeError("empty body")
    dnames = [_define_name(f) for f in forms if _is_define(f)]
    benv = Env(env)
    for n in dnames: benv.define(n, UNINITIALIZED)
    for i, form in enumerate(forms):
        last = (i == len(forms) - 1)
        if _is_define(form):
            _eval_internal_define(form, benv)
            if last: return UNSPECIFIED
        else:
            if last and tail: return _eval(form, benv, True)
            else: _eval(form, benv, False)
    return UNSPECIFIED

def _eval_internal_define(expr, benv):
    target = expr.cdr.car
    if isinstance(target, Symbol):
        if not isinstance(expr.cdr.cdr, Pair): raise SchemeError("define: missing expression")
        val = _eval(expr.cdr.cdr.car, benv, False)
        benv.set(target.name, val)
    elif isinstance(target, Pair):
        if not isinstance(target.car, Symbol): raise SchemeError("define: invalid name")
        formals = target.cdr
        body = _cdr_to_list(expr.cdr.cdr)
        if not body: raise SchemeError("define: empty body")
        benv.set(target.car.name, Closure(formals, body, benv))
    else:
        raise SchemeError("define: invalid form")
    return UNSPECIFIED

def _eval(expr, env, tail):
    if isinstance(expr, bool): return expr
    if isinstance(expr, int): return expr
    if isinstance(expr, str): return expr
    if isinstance(expr, (_Nil, _Unspecified)): return expr
    if isinstance(expr, Symbol): return env.lookup(expr.name)
    if isinstance(expr, Pair):
        head = expr.car
        if isinstance(head, Symbol):
            n = head.name
            if n == 'quote':
                if not isinstance(expr.cdr, Pair): raise SchemeError("quote: missing datum")
                return expr.cdr.car
            if n == 'if': return _eval_if(expr, env, tail)
            if n == 'lambda': return _eval_lambda(expr, env)
            if n == 'define': return _eval_define(expr, env)
            if n == 'set!': return _eval_set(expr, env)
            if n == 'begin': return _eval_begin(expr, env, tail)
            if n == 'cond': return _eval_cond(expr, env, tail)
            if n == 'and': return _eval_and(expr, env, tail)
            if n == 'or': return _eval_or(expr, env, tail)
            if n == 'let': return _eval_let(expr, env, tail)
            if n == 'let*': return _eval_let_star(expr, env, tail)
            if n == 'letrec': return _eval_letrec(expr, env, tail)
            if n == 'apply': return _eval_apply(expr, env, tail)
        return _eval_application(expr, env, tail)
    raise SchemeError("malformed expression")

def _eval_if(expr, env, tail):
    rest = expr.cdr
    if not isinstance(rest, Pair): raise SchemeError("if: malformed")
    test = _eval(rest.car, env, False)
    br = rest.cdr
    if not isinstance(br, Pair): raise SchemeError("if: malformed")
    if _is_true(test): return _eval(br.car, env, tail)
    if isinstance(br.cdr, _Nil): return UNSPECIFIED
    return _eval(br.cdr.car, env, tail)

def _eval_lambda(expr, env):
    if not isinstance(expr.cdr, Pair): raise SchemeError("lambda: malformed")
    body = _cdr_to_list(expr.cdr.cdr)
    if not body: raise SchemeError("lambda: empty body")
    return Closure(expr.cdr.car, body, env)

def _eval_define(expr, env):
    if not isinstance(expr.cdr, Pair): raise SchemeError("define: malformed")
    target = expr.cdr.car
    if isinstance(target, Symbol):
        if not isinstance(expr.cdr.cdr, Pair): raise SchemeError("define: missing expression")
        env.define(target.name, _eval(expr.cdr.cdr.car, env, False))
    elif isinstance(target, Pair):
        if not isinstance(target.car, Symbol): raise SchemeError("define: invalid name")
        body = _cdr_to_list(expr.cdr.cdr)
        if not body: raise SchemeError("define: empty body")
        env.define(target.car.name, Closure(target.cdr, body, env))
    else:
        raise SchemeError("define: invalid form")
    return UNSPECIFIED

def _eval_set(expr, env):
    if not isinstance(expr.cdr, Pair): raise SchemeError("set!: malformed")
    name = expr.cdr.car
    if not isinstance(name, Symbol): raise SchemeError("set!: name must be a symbol")
    if not isinstance(expr.cdr.cdr, Pair): raise SchemeError("set!: missing expression")
    val = _eval(expr.cdr.cdr.car, env, False)
    env.set(name.name, val)
    return UNSPECIFIED

def _eval_begin(expr, env, tail):
    forms = _cdr_to_list(expr.cdr)
    if not forms: raise SchemeError("begin: empty")
    for f in forms[:-1]: _eval(f, env, False)
    return _eval(forms[-1], env, tail)

def _eval_cond(expr, env, tail):
    clauses = _cdr_to_list(expr.cdr)
    for clause in clauses:
        if not isinstance(clause, Pair): raise SchemeError("cond: malformed clause")
        test = clause.car
        body = _cdr_to_list(clause.cdr)
        if isinstance(test, Symbol) and test.name == 'else':
            if not body: raise SchemeError("cond: else without expressions")
            for f in body[:-1]: _eval(f, env, False)
            return _eval(body[-1], env, tail)
        val = _eval(test, env, False)
        if _is_true(val):
            if not body: return val
            for f in body[:-1]: _eval(f, env, False)
            return _eval(body[-1], env, tail)
    return UNSPECIFIED

def _eval_and(expr, env, tail):
    forms = _cdr_to_list(expr.cdr)
    if not forms: return True
    for f in forms[:-1]:
        v = _eval(f, env, False)
        if not _is_true(v): return False
    return _eval(forms[-1], env, tail)

def _eval_or(expr, env, tail):
    forms = _cdr_to_list(expr.cdr)
    if not forms: return False
    for f in forms[:-1]:
        v = _eval(f, env, False)
        if _is_true(v): return v
    return _eval(forms[-1], env, tail)

def _eval_let(expr, env, tail):
    if not isinstance(expr.cdr, Pair): raise SchemeError("let: malformed")
    first = expr.cdr.car
    if isinstance(first, Symbol):
        # named let
        name = first
        if not isinstance(expr.cdr.cdr, Pair): raise SchemeError("named let: malformed")
        bindings = expr.cdr.cdr.car
        body = _cdr_to_list(expr.cdr.cdr.cdr)
        if not body: raise SchemeError("named let: empty body")
        vnames = []; ivals = []
        cur = bindings
        while isinstance(cur, Pair):
            b = cur.car
            if not isinstance(b, Pair) or not isinstance(b.car, Symbol):
                raise SchemeError("named let: invalid binding")
            if not isinstance(b.cdr, Pair): raise SchemeError("named let: missing init")
            vnames.append(b.car); ivals.append(_eval(b.cdr.car, env, False))
            cur = cur.cdr
        formals = NIL
        for vn in reversed(vnames): formals = Pair(vn, formals)
        lenv = Env(env)
        clo = Closure(formals, body, lenv)
        lenv.define(name.name, clo)
        if tail: return TailCall(clo, ivals)
        cenv = _make_call_env(formals, ivals, lenv)
        return _eval_body(body, cenv, False)
    else:
        # regular let
        bindings = first
        if not isinstance(bindings, (Pair, _Nil)): raise SchemeError("let: invalid bindings")
        body = _cdr_to_list(expr.cdr.cdr)
        if not body: raise SchemeError("let: empty body")
        vnames = []; ivals = []
        cur = bindings
        while isinstance(cur, Pair):
            b = cur.car
            if not isinstance(b, Pair) or not isinstance(b.car, Symbol):
                raise SchemeError("let: invalid binding")
            if not isinstance(b.cdr, Pair): raise SchemeError("let: missing init")
            vnames.append(b.car.name); ivals.append(_eval(b.cdr.car, env, False))
            cur = cur.cdr
        lenv = Env(env)
        for vn, iv in zip(vnames, ivals): lenv.define(vn, iv)
        return _eval_body(body, lenv, tail)

def _eval_let_star(expr, env, tail):
    if not isinstance(expr.cdr, Pair): raise SchemeError("let*: malformed")
    bindings = expr.cdr.car
    if not isinstance(bindings, (Pair, _Nil)): raise SchemeError("let*: invalid bindings")
    body = _cdr_to_list(expr.cdr.cdr)
    if not body: raise SchemeError("let*: empty body")
    senv = Env(env)
    cur = bindings
    while isinstance(cur, Pair):
        b = cur.car
        if not isinstance(b, Pair) or not isinstance(b.car, Symbol):
            raise SchemeError("let*: invalid binding")
        if not isinstance(b.cdr, Pair): raise SchemeError("let*: missing init")
        senv.define(b.car.name, _eval(b.cdr.car, senv, False))
        cur = cur.cdr
    return _eval_body(body, senv, tail)

def _eval_letrec(expr, env, tail):
    if not isinstance(expr.cdr, Pair): raise SchemeError("letrec: malformed")
    bindings = expr.cdr.car
    if not isinstance(bindings, (Pair, _Nil)): raise SchemeError("letrec: invalid bindings")
    body = _cdr_to_list(expr.cdr.cdr)
    if not body: raise SchemeError("letrec: empty body")
    renv = Env(env)
    names = []; inits = []
    cur = bindings
    while isinstance(cur, Pair):
        b = cur.car
        if not isinstance(b, Pair) or not isinstance(b.car, Symbol):
            raise SchemeError("letrec: invalid binding")
        if not isinstance(b.cdr, Pair): raise SchemeError("letrec: missing init")
        names.append(b.car.name); inits.append(b.cdr.car)
        renv.define(b.car.name, UNINITIALIZED)
        cur = cur.cdr
    for nm, init in zip(names, inits):
        renv.set(nm, _eval(init, renv, False))
    return _eval_body(body, renv, tail)

def _eval_apply(expr, env, tail):
    args_list = _cdr_to_list(expr.cdr)
    if len(args_list) < 2: raise SchemeError("apply: requires at least 2 arguments")
    proc = _eval(args_list[0], env, False)
    reg = [_eval(a, env, False) for a in args_list[1:-1]]
    lst = _eval(args_list[-1], env, False)
    elems = _to_python_list(lst)
    all_args = reg + elems
    if isinstance(proc, Closure):
        _check_arity(proc.formals, all_args)
        if tail: return TailCall(proc, all_args)
        return _eval_body(proc.body, _make_call_env(proc.formals, all_args, proc.env), False)
    elif isinstance(proc, Builtin):
        return proc.func(all_args)
    raise SchemeError("apply: not a procedure")

def _eval_application(expr, env, tail):
    proc = _eval(expr.car, env, False)
    args = []; cur = expr.cdr
    while isinstance(cur, Pair): args.append(_eval(cur.car, env, False)); cur = cur.cdr
    if not isinstance(cur, _Nil): raise SchemeError("dotted form used as application")
    if isinstance(proc, Closure):
        _check_arity(proc.formals, args)
        if tail: return TailCall(proc, args)
        return _eval_body(proc.body, _make_call_env(proc.formals, args, proc.env), False)
    elif isinstance(proc, Builtin):
        return proc.func(args)
    raise SchemeError("not a procedure")

def _trampoline(expr, env):
    result = _eval(expr, env, True)
    while isinstance(result, TailCall):
        proc = result.proc; args = result.args
        if isinstance(proc, Closure):
            result = _eval_body(proc.body, _make_call_env(proc.formals, args, proc.env), True)
        elif isinstance(proc, Builtin):
            result = proc.func(args)
        else:
            raise SchemeError("not a procedure")
    return result

# ─── Builtins ─────────────────────────────────────────────────────────────────

def _make_global_env(output):
    env = Env()

    def _add(name, fn):
        env.define(name, Builtin(name, fn))

    def _num(x):
        if not _is_int(x): raise SchemeError("expected integer")

    # Arithmetic
    def _plus(args):
        r = 0
        for a in args: _num(a); r += a
        return r
    def _times(args):
        r = 1
        for a in args: _num(a); r *= a
        return r
    def _minus(args):
        if not args: raise SchemeError("-: requires at least 1 argument")
        for a in args: _num(a)
        r = args[0]
        for a in args[1:]: r -= a
        return r
    def _quotient(args):
        if len(args) != 2: raise SchemeError("quotient: requires 2 arguments")
        a, b = args; _num(a); _num(b)
        if b == 0: raise SchemeError("division by zero")
        q = abs(a) // abs(b)
        return -q if (a < 0) ^ (b < 0) else q
    def _remainder(args):
        if len(args) != 2: raise SchemeError("remainder: requires 2 arguments")
        a, b = args; _num(a); _num(b)
        if b == 0: raise SchemeError("division by zero")
        q = abs(a) // abs(b)
        if (a < 0) ^ (b < 0): q = -q
        return a - q * b
    def _modulo(args):
        if len(args) != 2: raise SchemeError("modulo: requires 2 arguments")
        a, b = args; _num(a); _num(b)
        if b == 0: raise SchemeError("division by zero")
        return a % b
    def _cmp(op):
        def f(args):
            if not args: raise SchemeError("comparison: requires at least 1 argument")
            for a in args: _num(a)
            for i in range(len(args)-1):
                if not op(args[i], args[i+1]): return False
            return True
        return f

    # Pairs / Lists
    def _cons(args):
        if len(args) != 2: raise SchemeError("cons: requires 2 arguments")
        return Pair(args[0], args[1])
    def _car(args):
        if len(args) != 1: raise SchemeError("car: requires 1 argument")
        if not isinstance(args[0], Pair): raise SchemeError("car: not a pair")
        return args[0].car
    def _cdr(args):
        if len(args) != 1: raise SchemeError("cdr: requires 1 argument")
        if not isinstance(args[0], Pair): raise SchemeError("cdr: not a pair")
        return args[0].cdr
    def _list(args): return _list_to_scheme(args)
    def _null_p(args):
        if len(args) != 1: raise SchemeError("null?: requires 1 argument")
        return isinstance(args[0], _Nil)
    def _pair_p(args):
        if len(args) != 1: raise SchemeError("pair?: requires 1 argument")
        return isinstance(args[0], Pair)
    def _list_p(args):
        if len(args) != 1: raise SchemeError("list?: requires 1 argument")
        x = args[0]
        while isinstance(x, Pair): x = x.cdr
        return isinstance(x, _Nil)
    def _length(args):
        if len(args) != 1: raise SchemeError("length: requires 1 argument")
        x = args[0]; c = 0
        while isinstance(x, Pair): c += 1; x = x.cdr
        if not isinstance(x, _Nil): raise SchemeError("length: not a proper list")
        return c
    def _append(args):
        if not args: return NIL
        if len(args) == 1: return args[0]
        items = []
        for i in range(len(args)-1):
            x = args[i]
            while isinstance(x, Pair): items.append(x.car); x = x.cdr
            if not isinstance(x, _Nil): raise SchemeError("append: not a proper list")
        r = args[-1]
        for e in reversed(items): r = Pair(e, r)
        return r
    def _reverse(args):
        if len(args) != 1: raise SchemeError("reverse: requires 1 argument")
        x = args[0]; r = NIL
        while isinstance(x, Pair): r = Pair(x.car, r); x = x.cdr
        if not isinstance(x, _Nil): raise SchemeError("reverse: not a proper list")
        return r
    def _apply_builtin(args):
        if len(args) < 2: raise SchemeError("apply: requires at least 2 arguments")
        proc = args[0]; reg = args[1:-1]; lst = args[-1]
        elems = _to_python_list(lst)
        all_args = list(reg) + elems
        if isinstance(proc, Closure):
            _check_arity(proc.formals, all_args)
            return _eval_body(proc.body, _make_call_env(proc.formals, all_args, proc.env), False)
        elif isinstance(proc, Builtin):
            return proc.func(all_args)
        raise SchemeError("apply: not a procedure")

    # Equality / Predicates
    def _eq(args):
        if len(args) != 2: raise SchemeError("eq?: requires 2 arguments")
        a, b = args
        if isinstance(a, bool) and isinstance(b, bool): return a is b
        if _is_int(a) and _is_int(b): return a == b
        if isinstance(a, Symbol) and isinstance(b, Symbol): return a.name == b.name
        if isinstance(a, _Nil) and isinstance(b, _Nil): return True
        return a is b
    def _equal(args):
        if len(args) != 2: raise SchemeError("equal?: requires 2 arguments")
        return _equal_impl(args[0], args[1])
    def _equal_impl(a, b):
        while True:
            if isinstance(a, Pair) and isinstance(b, Pair):
                if not _equal_impl(a.car, b.car): return False
                a = a.cdr; b = b.cdr
            elif isinstance(a, _Nil) and isinstance(b, _Nil): return True
            elif isinstance(a, str) and isinstance(b, str): return a == b
            elif isinstance(a, Symbol) and isinstance(b, Symbol): return a.name == b.name
            elif _is_int(a) and _is_int(b): return a == b
            elif isinstance(a, bool) and isinstance(b, bool): return a is b
            elif isinstance(a, _Nil) or isinstance(b, _Nil): return False
            else: return a is b
    def _not(args):
        if len(args) != 1: raise SchemeError("not: requires 1 argument")
        return args[0] is False
    def _number_p(args):
        if len(args) != 1: raise SchemeError("number?: requires 1 argument")
        return _is_int(args[0])
    def _symbol_p(args):
        if len(args) != 1: raise SchemeError("symbol?: requires 1 argument")
        return isinstance(args[0], Symbol)
    def _string_p(args):
        if len(args) != 1: raise SchemeError("string?: requires 1 argument")
        return isinstance(args[0], str)
    def _procedure_p(args):
        if len(args) != 1: raise SchemeError("procedure?: requires 1 argument")
        return isinstance(args[0], (Closure, Builtin))

    # Strings
    def _string_append(args):
        for s in args:
            if not isinstance(s, str): raise SchemeError("string-append: not a string")
        return ''.join(args)

    # Number->String
    def _int_to_base(n, radix):
        if n == 0: return '0'
        neg = n < 0; n = abs(n); digits = []
        while n > 0:
            d = n % radix
            digits.append(chr(ord('0')+d) if d < 10 else chr(ord('a')+d-10))
            n //= radix
        r = ''.join(reversed(digits))
        return ('-' + r) if neg else r
    def _number_to_string(args):
        if len(args) == 1:
            n = args[0]; _num(n); return str(n)
        elif len(args) == 2:
            n = args[0]; radix = args[1]; _num(n); _num(radix)
            if radix not in (2, 8, 10, 16): raise SchemeError("number->string: invalid radix")
            return _int_to_base(n, radix)
        raise SchemeError("number->string: wrong number of arguments")

    # Output
    def _display(args):
        if len(args) != 1: raise SchemeError("display: requires 1 argument")
        output.append(_display_repr(args[0]))
        return UNSPECIFIED
    def _newline(args):
        if len(args) != 0: raise SchemeError("newline: requires 0 arguments")
        output.append('\n')
        return UNSPECIFIED

    # Error
    def _error(args):
        if not args: raise SchemeError("error: no arguments")
        msg = args[0]
        if not isinstance(msg, str): raise SchemeError(str(msg))
        parts = [msg]
        for irr in args[1:]:
            parts.append(' '); parts.append(_write_repr(irr))
        raise SchemeError(''.join(parts))

    _add('+', _plus); _add('*', _times); _add('-', _minus)
    _add('quotient', _quotient); _add('remainder', _remainder); _add('modulo', _modulo)
    _add('=', _cmp(lambda a,b: a==b)); _add('<', _cmp(lambda a,b: a<b))
    _add('>', _cmp(lambda a,b: a>b)); _add('<=', _cmp(lambda a,b: a<=b))
    _add('>=', _cmp(lambda a,b: a>=b))
    _add('cons', _cons); _add('car', _car); _add('cdr', _cdr); _add('list', _list)
    _add('null?', _null_p); _add('pair?', _pair_p); _add('list?', _list_p)
    _add('length', _length); _add('append', _append); _add('reverse', _reverse)
    _add('apply', _apply_builtin)
    _add('eq?', _eq); _add('equal?', _equal); _add('not', _not)
    _add('number?', _number_p); _add('symbol?', _symbol_p)
    _add('string?', _string_p); _add('procedure?', _procedure_p)
    _add('string-append', _string_append); _add('number->string', _number_to_string)
    _add('display', _display); _add('newline', _newline); _add('error', _error)
    return env

# ─── Public API ───────────────────────────────────────────────────────────────

def run(source: str) -> str:
    output = []
    result = [None]
    error = [None]

    def _worker():
        try:
            tokens = _tokenize(source)
            forms = _parse_all(tokens)
            env = _make_global_env(output)
            for form in forms:
                _trampoline(form, env)
            result[0] = ''.join(output)
        except SchemeError as e:
            e.output = ''.join(output)
            error[0] = e
        except Exception as e:
            error[0] = SchemeError(str(e), ''.join(output))

    try:
        threading.stack_size(256 * 1024 * 1024)
    except (ValueError, RuntimeError):
        pass
    t = threading.Thread(target=_worker)
    t.start()
    t.join()

    if error[0] is not None:
        raise error[0]
    return result[0]
