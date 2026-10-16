"""A Scheme interpreter for a small, precisely specified subset."""

import sys
import re
import threading

try:
    sys.set_int_max_str_digits(0)
except AttributeError:
    pass

sys.setrecursionlimit(500000)
try:
    threading.stack_size(256 * 1024 * 1024)
except (ValueError, RuntimeError):
    pass


# ─── Data Types ───────────────────────────────────────────────────────────────

class Symbol:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name
    def __repr__(self):
        return f"Sym({self.name})"
    def __eq__(self, other):
        return isinstance(other, Symbol) and self.name == other.name
    def __hash__(self):
        return hash(('sym', self.name))


class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr


class _EmptyList:
    def __repr__(self):
        return '()'
EMPTY = _EmptyList()


class _Unspecified:
    def __repr__(self):
        return '<unspecified>'
UNSPECIFIED = _Unspecified()


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


# ─── Exception ────────────────────────────────────────────────────────────────

class SchemeError(Exception):
    def __init__(self, message, output=''):
        super().__init__(message)
        self.output = output


# ─── Environment ──────────────────────────────────────────────────────────────

class Frame:
    __slots__ = ('vars', 'parent', 'uninitialized')
    def __init__(self, parent=None):
        self.vars = {}
        self.parent = parent
        self.uninitialized = set()

    def lookup(self, sym):
        name = sym.name
        if name in self.uninitialized:
            raise SchemeError(f"uninitialized variable: {name}")
        if name in self.vars:
            return self.vars[name]
        if self.parent:
            return self.parent.lookup(sym)
        raise SchemeError(f"unbound variable: {name}")

    def set(self, sym, value):
        name = sym.name
        if name in self.uninitialized:
            raise SchemeError(f"uninitialized variable: {name}")
        if name in self.vars:
            self.vars[name] = value
            return
        if self.parent:
            self.parent.set(sym, value)
            return
        raise SchemeError(f"unbound variable: {name}")

    def define(self, sym, value):
        self.vars[sym.name] = value
        self.uninitialized.discard(sym.name)


# ─── Body pseudo-expression (for tail-call loop) ─────────────────────────────

class BodyExpr:
    __slots__ = ('forms', 'env')
    def __init__(self, forms, env):
        self.forms = forms
        self.env = env


# ─── Reader ───────────────────────────────────────────────────────────────────

_INT_RE = re.compile(r'^[+-]?[0-9]+$')


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
            tokens.append('(')
            i += 1
        elif c == ')':
            tokens.append(')')
            i += 1
        elif c == "'":
            tokens.append("'")
            i += 1
        elif c == '"':
            i += 1
            parts = []
            while i < n and source[i] != '"':
                if source[i] == '\\':
                    i += 1
                    if i >= n:
                        raise SchemeError("unterminated string")
                    nc = source[i]
                    if nc == '"':
                        parts.append('"')
                    elif nc == '\\':
                        parts.append('\\')
                    elif nc == 'n':
                        parts.append('\n')
                    else:
                        raise SchemeError(f"bad escape: \\{nc}")
                    i += 1
                else:
                    parts.append(source[i])
                    i += 1
            if i >= n:
                raise SchemeError("unterminated string")
            i += 1
            tokens.append(('str', ''.join(parts)))
        else:
            start = i
            while i < n and source[i] not in ' \t\n\r()";\'':
                i += 1
            tokens.append(('tok', source[start:i]))
    return tokens


def _parse_all(source):
    tokens = _tokenize(source)
    pos = [0]
    result = []
    while pos[0] < len(tokens):
        result.append(_read_datum(tokens, pos))
    return result


def _read_datum(tokens, pos):
    if pos[0] >= len(tokens):
        raise SchemeError("unexpected end of input")
    tok = tokens[pos[0]]
    if tok == '(':
        pos[0] += 1
        return _read_list(tokens, pos)
    elif tok == ')':
        raise SchemeError("unexpected )")
    elif tok == "'":
        pos[0] += 1
        datum = _read_datum(tokens, pos)
        return Pair(Symbol('quote'), Pair(datum, EMPTY))
    elif isinstance(tok, tuple) and tok[0] == 'str':
        pos[0] += 1
        return tok[1]
    elif isinstance(tok, tuple) and tok[0] == 'tok':
        pos[0] += 1
        return _parse_atom(tok[1])
    else:
        raise SchemeError(f"unexpected token: {tok}")


def _read_list(tokens, pos):
    elements = []
    while True:
        if pos[0] >= len(tokens):
            raise SchemeError("unbalanced (")
        tok = tokens[pos[0]]
        if tok == ')':
            pos[0] += 1
            result = EMPTY
            for e in reversed(elements):
                result = Pair(e, result)
            return result
        if isinstance(tok, tuple) and tok[0] == 'tok' and tok[1] == '.':
            if not elements:
                raise SchemeError("dot without preceding element")
            pos[0] += 1
            cdr = _read_datum(tokens, pos)
            if pos[0] >= len(tokens) or tokens[pos[0]] != ')':
                raise SchemeError("expected ) after dotted pair")
            pos[0] += 1
            result = cdr
            for e in reversed(elements):
                result = Pair(e, result)
            return result
        elements.append(_read_datum(tokens, pos))


def _parse_atom(s):
    if s == '#t':
        return True
    if s == '#f':
        return False
    if s.startswith('#'):
        raise SchemeError(f"invalid # token: {s}")
    if _INT_RE.match(s):
        return int(s)
    return Symbol(s)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _is_proper_list(x):
    while isinstance(x, Pair):
        x = x.cdr
    return isinstance(x, _EmptyList)


def _to_list(x):
    result = []
    while isinstance(x, Pair):
        result.append(x.car)
        x = x.cdr
    return result


def _list_to_pair(lst, cdr=EMPTY):
    result = cdr
    for item in reversed(lst):
        result = Pair(item, result)
    return result


# ─── Interpreter ──────────────────────────────────────────────────────────────

class _Interpreter:
    def __init__(self):
        self.output_parts = []
        self.global_frame = Frame()
        self._setup_builtins()

    def write_output(self, s):
        self.output_parts.append(s)

    def get_output(self):
        return ''.join(self.output_parts)

    # ── Display / Write ──

    def display_repr(self, x):
        if isinstance(x, bool):
            return '#t' if x else '#f'
        if isinstance(x, int):
            return self._int_to_str(x)
        if isinstance(x, str):
            return x
        if isinstance(x, Symbol):
            return x.name
        if isinstance(x, _EmptyList):
            return '()'
        if isinstance(x, Pair):
            return self._display_pair(x)
        if isinstance(x, (Closure, Builtin)):
            return '#<procedure>'
        if isinstance(x, _Unspecified):
            return ''
        return str(x)

    def _display_pair(self, p):
        parts = ['(']
        first = True
        while isinstance(p, Pair):
            if not first:
                parts.append(' ')
            parts.append(self.display_repr(p.car))
            first = False
            p = p.cdr
        if not isinstance(p, _EmptyList):
            parts.append(' . ')
            parts.append(self.display_repr(p))
        parts.append(')')
        return ''.join(parts)

    def write_repr(self, x):
        if isinstance(x, str):
            escaped = x.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
            return '"' + escaped + '"'
        if isinstance(x, Pair):
            return self._write_pair(x)
        return self.display_repr(x)

    def _write_pair(self, p):
        parts = ['(']
        first = True
        while isinstance(p, Pair):
            if not first:
                parts.append(' ')
            parts.append(self.write_repr(p.car))
            first = False
            p = p.cdr
        if not isinstance(p, _EmptyList):
            parts.append(' . ')
            parts.append(self.write_repr(p))
        parts.append(')')
        return ''.join(parts)

    def _int_to_str(self, n):
        if n == 0:
            return '0'
        negative = n < 0
        n = abs(n)
        digits = []
        while n > 0:
            digits.append(chr(48 + n % 10))
            n //= 10
        if negative:
            return '-' + ''.join(reversed(digits))
        return ''.join(reversed(digits))

    # ── Core evaluator (tail-call loop) ──

    def eval(self, expr, env):
        while True:
            # Body pseudo-expression
            if isinstance(expr, BodyExpr):
                forms = expr.forms
                env = expr.env
                for form in forms:
                    if self._is_define(form):
                        nm = self._define_name(form)
                        env.uninitialized.add(nm)
                for form in forms[:-1]:
                    if self._is_define(form):
                        ns, ve = self._parse_define(form)
                        val = self.eval(ve, env)
                        env.define(ns, val)
                    else:
                        self.eval(form, env)
                last = forms[-1]
                if self._is_define(last):
                    ns, ve = self._parse_define(last)
                    val = self.eval(ve, env)
                    env.define(ns, val)
                    return UNSPECIFIED
                expr = last
                continue

            # Self-evaluating
            if isinstance(expr, bool):
                return expr
            if isinstance(expr, int):
                return expr
            if isinstance(expr, str):
                return expr
            if isinstance(expr, _EmptyList):
                raise SchemeError("cannot evaluate ()")
            if isinstance(expr, _Unspecified):
                return expr

            # Symbol lookup
            if isinstance(expr, Symbol):
                return env.lookup(expr)

            # Must be Pair
            if not isinstance(expr, Pair):
                return expr

            # Dotted form as application
            if not _is_proper_list(expr.cdr):
                raise SchemeError("dotted form used as application")

            op = expr.car

            if isinstance(op, Symbol):
                name = op.name

                if name == 'quote':
                    if not isinstance(expr.cdr, Pair) or isinstance(expr.cdr.cdr, Pair):
                        raise SchemeError("malformed quote")
                    return expr.cdr.car

                if name == 'if':
                    args = _to_list(expr.cdr)
                    if len(args) < 2 or len(args) > 3:
                        raise SchemeError("malformed if")
                    tv = self.eval(args[0], env)
                    if tv is not False:
                        expr = args[1]
                        continue
                    elif len(args) == 3:
                        expr = args[2]
                        continue
                    else:
                        return UNSPECIFIED

                if name == 'lambda':
                    if not isinstance(expr.cdr, Pair):
                        raise SchemeError("malformed lambda")
                    formals = expr.cdr.car
                    body = expr.cdr.cdr
                    if isinstance(body, _EmptyList):
                        raise SchemeError("empty lambda body")
                    return Closure(formals, _to_list(body), env)

                if name == 'define':
                    ns, ve = self._parse_define(expr)
                    val = self.eval(ve, env)
                    env.define(ns, val)
                    return UNSPECIFIED

                if name == 'set!':
                    args = _to_list(expr.cdr)
                    if len(args) != 2 or not isinstance(args[0], Symbol):
                        raise SchemeError("malformed set!")
                    val = self.eval(args[1], env)
                    env.set(args[0], val)
                    return UNSPECIFIED

                if name == 'begin':
                    forms = _to_list(expr.cdr)
                    if not forms:
                        raise SchemeError("empty begin")
                    for f in forms[:-1]:
                        self.eval(f, env)
                    expr = forms[-1]
                    continue

                if name == 'cond':
                    clauses = _to_list(expr.cdr)
                    matched = False
                    body = []
                    for clause in clauses:
                        if not isinstance(clause, Pair):
                            raise SchemeError("malformed cond clause")
                        test = clause.car
                        body = _to_list(clause.cdr)
                        if isinstance(test, Symbol) and test.name == 'else':
                            matched = True
                            break
                        val = self.eval(test, env)
                        if val is not False:
                            matched = True
                            if not body:
                                return val
                            break
                    if not matched:
                        return UNSPECIFIED
                    if not body:
                        return UNSPECIFIED
                    for f in body[:-1]:
                        self.eval(f, env)
                    expr = body[-1]
                    continue

                if name == 'and':
                    args = _to_list(expr.cdr)
                    if not args:
                        return True
                    for a in args[:-1]:
                        val = self.eval(a, env)
                        if val is False:
                            return False
                    expr = args[-1]
                    continue

                if name == 'or':
                    args = _to_list(expr.cdr)
                    if not args:
                        return False
                    for a in args[:-1]:
                        val = self.eval(a, env)
                        if val is not False:
                            return val
                    expr = args[-1]
                    continue

                if name == 'let':
                    if not isinstance(expr.cdr, Pair):
                        raise SchemeError("malformed let")
                    bon = expr.cdr.car
                    if isinstance(bon, Symbol):
                        be = self._eval_named_let(expr, env, bon)
                    else:
                        be = self._eval_let(expr, env, bon)
                    expr = be
                    continue

                if name == 'let*':
                    if not isinstance(expr.cdr, Pair):
                        raise SchemeError("malformed let*")
                    be = self._eval_letstar(expr, env)
                    expr = be
                    continue

                if name == 'letrec':
                    if not isinstance(expr.cdr, Pair):
                        raise SchemeError("malformed letrec")
                    be = self._eval_letrec(expr, env)
                    expr = be
                    continue

                if name == 'apply':
                    args = _to_list(expr.cdr)
                    if len(args) < 2:
                        raise SchemeError("apply requires at least 2 arguments")
                    proc = self.eval(args[0], env)
                    mid = []
                    for a in args[1:-1]:
                        mid.append(self.eval(a, env))
                    last = self.eval(args[-1], env)
                    if not _is_proper_list(last):
                        raise SchemeError("apply: last argument not a proper list")
                    all_args = mid + _to_list(last)
                    if isinstance(proc, Closure):
                        frame = self._bind_formals(proc.formals, all_args)
                        frame.parent = proc.env
                        expr = BodyExpr(proc.body, frame)
                        continue
                    elif isinstance(proc, Builtin):
                        self._check_arity(proc, all_args)
                        return proc.func(all_args)
                    else:
                        raise SchemeError(f"not a procedure: {self.display_repr(proc)}")

            # General application
            proc = self.eval(op, env)
            arg_exprs = _to_list(expr.cdr)
            evaluated = []
            for a in arg_exprs:
                evaluated.append(self.eval(a, env))

            if isinstance(proc, Closure):
                frame = self._bind_formals(proc.formals, evaluated)
                frame.parent = proc.env
                expr = BodyExpr(proc.body, frame)
                continue
            elif isinstance(proc, Builtin):
                self._check_arity(proc, evaluated)
                return proc.func(evaluated)
            else:
                raise SchemeError(f"not a procedure: {self.display_repr(proc)}")

    # ── Formals binding ──

    def _bind_formals(self, formals, args):
        frame = Frame()
        if isinstance(formals, Symbol):
            frame.vars[formals.name] = _list_to_pair(args)
        elif isinstance(formals, _EmptyList):
            if args:
                raise SchemeError("too many arguments")
        elif isinstance(formals, Pair):
            fixed = []
            rest = None
            f = formals
            while isinstance(f, Pair):
                if not isinstance(f.car, Symbol):
                    raise SchemeError("malformed formals")
                fixed.append(f.car)
                f = f.cdr
            if isinstance(f, Symbol):
                rest = f
            elif not isinstance(f, _EmptyList):
                raise SchemeError("malformed formals")
            if rest is None:
                if len(args) != len(fixed):
                    raise SchemeError("wrong number of arguments")
                for i, p in enumerate(fixed):
                    frame.vars[p.name] = args[i]
            else:
                if len(args) < len(fixed):
                    raise SchemeError("too few arguments")
                for i, p in enumerate(fixed):
                    frame.vars[p.name] = args[i]
                frame.vars[rest.name] = _list_to_pair(args[len(fixed):])
        else:
            raise SchemeError("malformed formals")
        return frame

    def _check_arity(self, proc, args):
        n = len(args)
        if n < proc.min_args:
            raise SchemeError(f"too few arguments to {proc.name}")
        if proc.max_args is not None and n > proc.max_args:
            raise SchemeError(f"too many arguments to {proc.name}")

    # ── Define helpers ──

    def _is_define(self, form):
        return (isinstance(form, Pair) and isinstance(form.car, Symbol)
                and form.car.name == 'define')

    def _define_name(self, form):
        cdr = form.cdr
        if not isinstance(cdr, Pair):
            raise SchemeError("malformed define")
        target = cdr.car
        if isinstance(target, Symbol):
            return target.name
        if isinstance(target, Pair) and isinstance(target.car, Symbol):
            return target.car.name
        raise SchemeError("malformed define")

    def _parse_define(self, form):
        cdr = form.cdr
        if not isinstance(cdr, Pair):
            raise SchemeError("malformed define")
        target = cdr.car
        if isinstance(target, Symbol):
            rest = cdr.cdr
            if not isinstance(rest, Pair) or isinstance(rest.cdr, Pair):
                raise SchemeError("malformed define")
            return target, rest.car
        if isinstance(target, Pair):
            nm = target.car
            if not isinstance(nm, Symbol):
                raise SchemeError("malformed define")
            formals = target.cdr
            body = cdr.cdr
            if isinstance(body, _EmptyList):
                raise SchemeError("empty define body")
            lam = Pair(Symbol('lambda'), Pair(formals, body))
            return nm, lam
        raise SchemeError("malformed define")

    # ── Let forms ──

    def _eval_let(self, expr, env, bindings):
        body = expr.cdr.cdr
        if isinstance(body, _EmptyList):
            raise SchemeError("empty let body")
        body_forms = _to_list(body)
        names = []
        values = []
        b = bindings
        while isinstance(b, Pair):
            binding = b.car
            if not isinstance(binding, Pair):
                raise SchemeError("malformed let binding")
            var = binding.car
            if not isinstance(var, Symbol):
                raise SchemeError("malformed let binding")
            init = binding.cdr
            if not isinstance(init, Pair) or isinstance(init.cdr, Pair):
                raise SchemeError("malformed let binding")
            names.append(var)
            values.append(self.eval(init.car, env))
            b = b.cdr
        if not isinstance(b, _EmptyList):
            raise SchemeError("malformed let bindings")
        frame = Frame(env)
        for i, var in enumerate(names):
            frame.vars[var.name] = values[i]
        return BodyExpr(body_forms, frame)

    def _eval_named_let(self, expr, env, name):
        if not isinstance(expr.cdr.cdr, Pair):
            raise SchemeError("malformed named let")
        bindings = expr.cdr.cdr.car
        body = expr.cdr.cdr.cdr
        if isinstance(body, _EmptyList):
            raise SchemeError("empty let body")
        body_forms = _to_list(body)
        vars_list = []
        init_vals = []
        b = bindings
        while isinstance(b, Pair):
            binding = b.car
            if not isinstance(binding, Pair):
                raise SchemeError("malformed let binding")
            var = binding.car
            if not isinstance(var, Symbol):
                raise SchemeError("malformed let binding")
            init = binding.cdr
            if not isinstance(init, Pair) or isinstance(init.cdr, Pair):
                raise SchemeError("malformed let binding")
            vars_list.append(var)
            init_vals.append(self.eval(init.car, env))
            b = b.cdr
        if not isinstance(b, _EmptyList):
            raise SchemeError("malformed let bindings")
        frame = Frame(env)
        frame.uninitialized.add(name.name)
        formals = _list_to_pair(vars_list)
        closure = Closure(formals, body_forms, frame)
        frame.vars[name.name] = closure
        frame.uninitialized.discard(name.name)
        new_frame = self._bind_formals(formals, init_vals)
        new_frame.parent = frame
        return BodyExpr(body_forms, new_frame)

    def _eval_letstar(self, expr, env):
        bindings = expr.cdr.car
        body = expr.cdr.cdr
        if isinstance(body, _EmptyList):
            raise SchemeError("empty let* body")
        body_forms = _to_list(body)
        frame = Frame(env)
        b = bindings
        while isinstance(b, Pair):
            binding = b.car
            if not isinstance(binding, Pair):
                raise SchemeError("malformed let* binding")
            var = binding.car
            if not isinstance(var, Symbol):
                raise SchemeError("malformed let* binding")
            init = binding.cdr
            if not isinstance(init, Pair) or isinstance(init.cdr, Pair):
                raise SchemeError("malformed let* binding")
            val = self.eval(init.car, frame)
            frame.vars[var.name] = val
            b = b.cdr
        if not isinstance(b, _EmptyList):
            raise SchemeError("malformed let* bindings")
        return BodyExpr(body_forms, frame)

    def _eval_letrec(self, expr, env):
        bindings = expr.cdr.car
        body = expr.cdr.cdr
        if isinstance(body, _EmptyList):
            raise SchemeError("empty letrec body")
        body_forms = _to_list(body)
        frame = Frame(env)
        names = []
        inits = []
        b = bindings
        while isinstance(b, Pair):
            binding = b.car
            if not isinstance(binding, Pair):
                raise SchemeError("malformed letrec binding")
            var = binding.car
            if not isinstance(var, Symbol):
                raise SchemeError("malformed letrec binding")
            init = binding.cdr
            if not isinstance(init, Pair) or isinstance(init.cdr, Pair):
                raise SchemeError("malformed letrec binding")
            names.append(var)
            inits.append(init.car)
            frame.uninitialized.add(var.name)
            b = b.cdr
        if not isinstance(b, _EmptyList):
            raise SchemeError("malformed letrec bindings")
        for i, var in enumerate(names):
            val = self.eval(inits[i], frame)
            frame.define(var, val)
        return BodyExpr(body_forms, frame)

    # ── Builtins ──

    def _setup_builtins(self):
        g = self.global_frame

        def add(name, func, mn=0, mx=None):
            g.vars[name] = Builtin(name, func, mn, mx)

        add('+', self._b_add, 0)
        add('*', self._b_mul, 0)
        add('-', self._b_sub, 1)
        add('quotient', self._b_quotient, 2, 2)
        add('remainder', self._b_remainder, 2, 2)
        add('modulo', self._b_modulo, 2, 2)
        add('=', self._b_eq, 1)
        add('<', self._b_lt, 1)
        add('>', self._b_gt, 1)
        add('<=', self._b_le, 1)
        add('>=', self._b_ge, 1)
        add('number->string', self._b_number_to_string, 1, 2)
        add('cons', self._b_cons, 2, 2)
        add('car', self._b_car, 1, 1)
        add('cdr', self._b_cdr, 1, 1)
        add('list', self._b_list, 0)
        add('null?', self._b_null, 1, 1)
        add('pair?', self._b_pair, 1, 1)
        add('list?', self._b_listp, 1, 1)
        add('length', self._b_length, 1, 1)
        add('append', self._b_append, 0)
        add('reverse', self._b_reverse, 1, 1)
        add('apply', self._b_apply, 2)
        add('eq?', self._b_eqq, 2, 2)
        add('equal?', self._b_equal, 2, 2)
        add('not', self._b_not, 1, 1)
        add('number?', self._b_number, 1, 1)
        add('symbol?', self._b_symbol, 1, 1)
        add('string?', self._b_string, 1, 1)
        add('procedure?', self._b_procedure, 1, 1)
        add('string-append', self._b_string_append, 0)
        add('display', self._b_display, 1, 1)
        add('newline', self._b_newline, 0, 0)
        add('error', self._b_error, 1)

    def _check_num(self, x, fname):
        if isinstance(x, bool) or not isinstance(x, int):
            raise SchemeError(f"{fname}: not a number")

    def _b_add(self, args):
        r = 0
        for a in args:
            self._check_num(a, '+')
            r += a
        return r

    def _b_mul(self, args):
        r = 1
        for a in args:
            self._check_num(a, '*')
            r *= a
        return r

    def _b_sub(self, args):
        for a in args:
            self._check_num(a, '-')
        if len(args) == 1:
            return -args[0]
        r = args[0]
        for a in args[1:]:
            r -= a
        return r

    def _b_quotient(self, args):
        a, b = args
        self._check_num(a, 'quotient')
        self._check_num(b, 'quotient')
        if b == 0:
            raise SchemeError("division by zero")
        q = abs(a) // abs(b)
        if (a < 0) != (b < 0):
            q = -q
        return q

    def _b_remainder(self, args):
        a, b = args
        self._check_num(a, 'remainder')
        self._check_num(b, 'remainder')
        if b == 0:
            raise SchemeError("division by zero")
        q = abs(a) // abs(b)
        if (a < 0) != (b < 0):
            q = -q
        return a - b * q

    def _b_modulo(self, args):
        a, b = args
        self._check_num(a, 'modulo')
        self._check_num(b, 'modulo')
        if b == 0:
            raise SchemeError("division by zero")
        return a % b

    def _b_eq(self, args):
        for a in args:
            self._check_num(a, '=')
        for i in range(len(args) - 1):
            if args[i] != args[i + 1]:
                return False
        return True

    def _b_lt(self, args):
        for a in args:
            self._check_num(a, '<')
        for i in range(len(args) - 1):
            if not (args[i] < args[i + 1]):
                return False
        return True

    def _b_gt(self, args):
        for a in args:
            self._check_num(a, '>')
        for i in range(len(args) - 1):
            if not (args[i] > args[i + 1]):
                return False
        return True

    def _b_le(self, args):
        for a in args:
            self._check_num(a, '<=')
        for i in range(len(args) - 1):
            if not (args[i] <= args[i + 1]):
                return False
        return True

    def _b_ge(self, args):
        for a in args:
            self._check_num(a, '>=')
        for i in range(len(args) - 1):
            if not (args[i] >= args[i + 1]):
                return False
        return True

    def _b_number_to_string(self, args):
        n = args[0]
        self._check_num(n, 'number->string')
        if len(args) == 1:
            return self._int_to_str(n)
        radix = args[1]
        self._check_num(radix, 'number->string')
        if radix not in (2, 8, 10, 16):
            raise SchemeError("number->string: invalid radix")
        if n == 0:
            return '0'
        negative = n < 0
        n = abs(n)
        digits = []
        while n > 0:
            digits.append('0123456789abcdef'[n % radix])
            n //= radix
        if negative:
            return '-' + ''.join(reversed(digits))
        return ''.join(reversed(digits))

    def _b_cons(self, args):
        return Pair(args[0], args[1])

    def _b_car(self, args):
        p = args[0]
        if not isinstance(p, Pair):
            raise SchemeError("car: not a pair")
        return p.car

    def _b_cdr(self, args):
        p = args[0]
        if not isinstance(p, Pair):
            raise SchemeError("cdr: not a pair")
        return p.cdr

    def _b_list(self, args):
        return _list_to_pair(args)

    def _b_null(self, args):
        return isinstance(args[0], _EmptyList)

    def _b_pair(self, args):
        return isinstance(args[0], Pair)

    def _b_listp(self, args):
        return _is_proper_list(args[0])

    def _b_length(self, args):
        l = args[0]
        n = 0
        while isinstance(l, Pair):
            n += 1
            l = l.cdr
        if not isinstance(l, _EmptyList):
            raise SchemeError("length: not a proper list")
        return n

    def _b_append(self, args):
        if not args:
            return EMPTY
        for arg in args[:-1]:
            if not _is_proper_list(arg):
                raise SchemeError("append: argument not a proper list")
        result = args[-1]
        for arg in reversed(args[:-1]):
            items = _to_list(arg)
            for item in reversed(items):
                result = Pair(item, result)
        return result

    def _b_reverse(self, args):
        l = args[0]
        if not _is_proper_list(l):
            raise SchemeError("reverse: not a proper list")
        result = EMPTY
        while isinstance(l, Pair):
            result = Pair(l.car, result)
            l = l.cdr
        return result

    def _b_apply(self, args):
        proc = args[0]
        mid = list(args[1:-1])
        last = args[-1]
        if not _is_proper_list(last):
            raise SchemeError("apply: last argument not a proper list")
        all_args = mid + _to_list(last)
        if isinstance(proc, Closure):
            frame = self._bind_formals(proc.formals, all_args)
            frame.parent = proc.env
            return self._eval_body_simple(proc.body, frame)
        elif isinstance(proc, Builtin):
            self._check_arity(proc, all_args)
            return proc.func(all_args)
        else:
            raise SchemeError("apply: not a procedure")

    def _eval_body_simple(self, forms, env):
        for form in forms[:-1]:
            if self._is_define(form):
                ns, ve = self._parse_define(form)
                val = self.eval(ve, env)
                env.define(ns, val)
            else:
                self.eval(form, env)
        last = forms[-1]
        if self._is_define(last):
            ns, ve = self._parse_define(last)
            val = self.eval(ve, env)
            env.define(ns, val)
            return UNSPECIFIED
        return self.eval(last, env)

    def _b_eqq(self, args):
        a, b = args
        if isinstance(a, bool) or isinstance(b, bool):
            return a is b
        if isinstance(a, int) and isinstance(b, int):
            return a == b
        if isinstance(a, Symbol) and isinstance(b, Symbol):
            return a.name == b.name
        if isinstance(a, _EmptyList) and isinstance(b, _EmptyList):
            return True
        return a is b

    def _b_equal(self, args):
        return self._scheme_equal(args[0], args[1])

    def _scheme_equal(self, a, b):
        if isinstance(a, bool) or isinstance(b, bool):
            return a is b
        if isinstance(a, int) and isinstance(b, int):
            return a == b
        if isinstance(a, str) and isinstance(b, str):
            return a == b
        if isinstance(a, Symbol) and isinstance(b, Symbol):
            return a.name == b.name
        if isinstance(a, _EmptyList) and isinstance(b, _EmptyList):
            return True
        if isinstance(a, Pair) and isinstance(b, Pair):
            while True:
                if not self._scheme_equal(a.car, b.car):
                    return False
                a = a.cdr
                b = b.cdr
                if isinstance(a, _EmptyList) and isinstance(b, _EmptyList):
                    return True
                if not (isinstance(a, Pair) and isinstance(b, Pair)):
                    return self._scheme_equal(a, b)
        return a is b

    def _b_not(self, args):
        return args[0] is False

    def _b_number(self, args):
        x = args[0]
        return isinstance(x, int) and not isinstance(x, bool)

    def _b_symbol(self, args):
        return isinstance(args[0], Symbol)

    def _b_string(self, args):
        return isinstance(args[0], str)

    def _b_procedure(self, args):
        return isinstance(args[0], (Closure, Builtin))

    def _b_string_append(self, args):
        parts = []
        for s in args:
            if not isinstance(s, str):
                raise SchemeError("string-append: not a string")
            parts.append(s)
        return ''.join(parts)

    def _b_display(self, args):
        self.write_output(self.display_repr(args[0]))
        return UNSPECIFIED

    def _b_newline(self, args):
        self.write_output('\n')
        return UNSPECIFIED

    def _b_error(self, args):
        msg = args[0]
        if not isinstance(msg, str):
            raise SchemeError("error: first argument must be a string")
        parts = [msg]
        for irritant in args[1:]:
            parts.append(' ')
            parts.append(self.write_repr(irritant))
        raise SchemeError(''.join(parts))


# ─── Public API ───────────────────────────────────────────────────────────────

def run(source):
    result = [None]
    error = [None]

    def _target():
        try:
            result[0] = _run_inner(source)
        except Exception as e:
            error[0] = e

    t = threading.Thread(target=_target)
    t.start()
    t.join()

    if error[0] is not None:
        raise error[0]
    return result[0]


def _run_inner(source):
    interp = _Interpreter()
    try:
        forms = _parse_all(source)
    except SchemeError:
        raise
    except Exception as e:
        raise SchemeError(str(e))

    try:
        for form in forms:
            interp.eval(form, interp.global_frame)
    except SchemeError as e:
        e.output = interp.get_output()
        raise
    except RecursionError:
        err = SchemeError("stack overflow")
        err.output = interp.get_output()
        raise err
    except Exception as e:
        err = SchemeError(str(e))
        err.output = interp.get_output()
        raise err

    return interp.get_output()
