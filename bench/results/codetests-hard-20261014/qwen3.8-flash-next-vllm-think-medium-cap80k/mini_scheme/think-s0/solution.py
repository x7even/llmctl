import sys

try:
    sys.set_int_max_str_digits(0)
except (AttributeError, ValueError):
    pass

sys.setrecursionlimit(500000)


class SchemeError(Exception):
    def __init__(self, message, output=''):
        super().__init__(message)
        self.output = output


class Symbol:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name
    def __repr__(self):
        return f'Symbol({self.name!r})'


class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr


class _Nil:
    def __repr__(self):
        return '()'

NIL = _Nil()


class _Unspecified:
    def __repr__(self):
        return '#<unspecified>'

UNSPECIFIED = _Unspecified()


class Box:
    UNBOUND = object()
    __slots__ = ('value',)
    def __init__(self, value=UNBOUND):
        self.value = value


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


class TailCall:
    __slots__ = ('proc', 'args')
    def __init__(self, proc, args):
        self.proc = proc
        self.args = args


# ─── Tokenizer ────────────────────────────────────────────────────────────────

class _Tok:
    LPAREN=0; RPAREN=1; QUOTE=2; STRING=3; NUMBER=4; SYMBOL=5; DOT=6; TRUE=7; FALSE=8

def _tokenize(source):
    tokens = []
    i = 0
    n = len(source)
    while i < n:
        c = source[i]
        if c in ' \t\n\r':
            i += 1; continue
        if c == ';':
            while i < n and source[i] != '\n':
                i += 1
            continue
        if c == '(':
            tokens.append((_Tok.LPAREN, None)); i += 1; continue
        if c == ')':
            tokens.append((_Tok.RPAREN, None)); i += 1; continue
        if c == "'":
            tokens.append((_Tok.QUOTE, None)); i += 1; continue
        if c == '"':
            i += 1
            buf = []
            terminated = False
            while i < n:
                ch = source[i]
                if ch == '"':
                    terminated = True; i += 1; break
                if ch == '\\':
                    i += 1
                    if i >= n:
                        raise SyntaxError("unterminated string escape")
                    ec = source[i]
                    if ec == '"': buf.append('"')
                    elif ec == '\\': buf.append('\\')
                    elif ec == 'n': buf.append('\n')
                    else: raise SyntaxError(f"invalid escape \\{ec}")
                    i += 1
                else:
                    buf.append(ch); i += 1
            if not terminated:
                raise SyntaxError("unterminated string")
            tokens.append((_Tok.STRING, ''.join(buf)))
            continue
        start = i
        while i < n and source[i] not in ' \t\n\r()";\'':
            i += 1
        tok = source[start:i]
        if tok == '.':
            tokens.append((_Tok.DOT, None))
        elif tok == '#t':
            tokens.append((_Tok.TRUE, None))
        elif tok == '#f':
            tokens.append((_Tok.FALSE, None))
        elif tok.startswith('#'):
            raise SyntaxError(f"invalid # token: {tok}")
        elif _is_int_tok(tok):
            tokens.append((_Tok.NUMBER, int(tok)))
        else:
            tokens.append((_Tok.SYMBOL, Symbol(tok)))
    return tokens


def _is_int_tok(s):
    if not s: return False
    idx = 0
    if s[0] in '+-':
        idx = 1
    if idx >= len(s): return False
    for c in s[idx:]:
        if c < '0' or c > '9': return False
    return True


# ─── Parser ───────────────────────────────────────────────────────────────────

def _parse(source):
    tokens = _tokenize(source)
    pos = [0]
    forms = []
    while pos[0] < len(tokens):
        if tokens[pos[0]][0] == _Tok.RPAREN:
            raise SyntaxError("unexpected )")
        forms.append(_parse_datum(tokens, pos))
    return forms


def _parse_datum(tokens, pos):
    if pos[0] >= len(tokens):
        raise SyntaxError("unexpected end of input")
    tt, tv = tokens[pos[0]]
    if tt == _Tok.LPAREN:
        return _parse_list(tokens, pos)
    if tt == _Tok.RPAREN:
        raise SyntaxError("unexpected )")
    if tt == _Tok.QUOTE:
        pos[0] += 1
        d = _parse_datum(tokens, pos)
        return Pair(Symbol('quote'), Pair(d, NIL))
    if tt == _Tok.STRING:
        pos[0] += 1; return tv
    if tt == _Tok.NUMBER:
        pos[0] += 1; return tv
    if tt == _Tok.TRUE:
        pos[0] += 1; return True
    if tt == _Tok.FALSE:
        pos[0] += 1; return False
    if tt == _Tok.SYMBOL:
        pos[0] += 1; return tv
    if tt == _Tok.DOT:
        raise SyntaxError("dot outside list")
    raise SyntaxError("unexpected token")


def _parse_list(tokens, pos):
    pos[0] += 1
    elems = []
    while True:
        if pos[0] >= len(tokens):
            raise SyntaxError("unbalanced (")
        tt, tv = tokens[pos[0]]
        if tt == _Tok.RPAREN:
            pos[0] += 1
            return _make_list(elems)
        if tt == _Tok.DOT:
            pos[0] += 1
            if len(elems) == 0:
                raise SyntaxError("dot with no preceding element")
            cdr = _parse_datum(tokens, pos)
            if pos[0] >= len(tokens) or tokens[pos[0]][0] != _Tok.RPAREN:
                raise SyntaxError("expected ) after dotted pair")
            pos[0] += 1
            result = cdr
            for e in reversed(elems):
                result = Pair(e, result)
            return result
        elems.append(_parse_datum(tokens, pos))


def _make_list(elems):
    r = NIL
    for e in reversed(elems):
        r = Pair(e, r)
    return r


# ─── Environment ──────────────────────────────────────────────────────────────

class Frame:
    __slots__ = ('bindings',)
    def __init__(self):
        self.bindings = {}


class Env:
    __slots__ = ('frame', 'parent', 'define_frame')
    def __init__(self, frame, parent=None, define_frame=None):
        self.frame = frame
        self.parent = parent
        self.define_frame = define_frame


def _lookup(env, name):
    e = env
    while e is not None:
        if name in e.frame.bindings:
            b = e.frame.bindings[name]
            if b.value is Box.UNBOUND:
                raise SchemeError(f"unbound variable: {name}")
            return b.value
        e = e.parent
    raise SchemeError(f"unbound variable: {name}")


def _define_var(env, name, value):
    if env.define_frame is not None:
        env.define_frame.bindings[name] = Box(value)
    else:
        env.frame.bindings[name] = Box(value)


def _set_var(env, name, value):
    e = env
    while e is not None:
        if name in e.frame.bindings:
            e.frame.bindings[name].value = value
            return
        e = e.parent
    raise SchemeError(f"set!: unbound variable: {name}")


# ─── Interpreter ──────────────────────────────────────────────────────────────

class Interpreter:
    def __init__(self):
        self.output = []
        self.globals = Frame()
        self._orig_apply = None
        self._setup_globals()

    # ── helpers ──

    def _to_list(self, datum):
        result = []
        cur = datum
        while isinstance(cur, Pair):
            result.append(cur.car)
            cur = cur.cdr
        if cur is not NIL:
            raise SchemeError("improper list")
        return result

    def _args_to_list(self, args):
        r = NIL
        for a in reversed(args):
            r = Pair(a, r)
        return r

    def _is_proper_list(self, obj):
        cur = obj
        while isinstance(cur, Pair):
            cur = cur.cdr
        return cur is NIL

    def _check_arity(self, proc, args):
        n = len(args)
        if isinstance(proc, Builtin):
            if n < proc.min_args:
                raise SchemeError(f"{proc.name}: too few arguments")
            if proc.max_args is not None and n > proc.max_args:
                raise SchemeError(f"{proc.name}: too many arguments")
        elif isinstance(proc, Closure):
            f = proc.formals
            if isinstance(f, Symbol):
                pass  # variadic, any count
            else:
                names, rest = f
                if rest is None:
                    if n != len(names):
                        raise SchemeError(f"wrong number of arguments: expected {len(names)}, got {n}")
                else:
                    if n < len(names):
                        raise SchemeError(f"wrong number of arguments: expected at least {len(names)}, got {n}")

    def _make_call_env(self, closure, args):
        pf = Frame()
        f = closure.formals
        if isinstance(f, Symbol):
            pf.bindings[f.name] = Box(self._args_to_list(args))
        else:
            names, rest = f
            if rest is None:
                if len(args) != len(names):
                    raise SchemeError(f"wrong number of arguments: expected {len(names)}, got {len(args)}")
                for i, nm in enumerate(names):
                    pf.bindings[nm] = Box(args[i])
            else:
                if len(args) < len(names):
                    raise SchemeError(f"wrong number of arguments: expected at least {len(names)}, got {len(args)}")
                for i, nm in enumerate(names):
                    pf.bindings[nm] = Box(args[i])
                pf.bindings[rest] = Box(self._args_to_list(args[len(names):]))
        param_env = Env(pf, parent=closure.env, define_frame=None)
        def_names = self._scan_defines(closure.body)
        df = Frame()
        for nm in def_names:
            df.bindings[nm] = Box(Box.UNBOUND)
        return Env(df, parent=param_env, define_frame=df)

    def _scan_defines(self, body):
        names = []
        for form in body:
            if isinstance(form, Pair) and isinstance(form.car, Symbol) and form.car.name == 'define':
                if isinstance(form.cdr, Pair):
                    t = form.cdr.car
                    if isinstance(t, Symbol):
                        names.append(t.name)
                    elif isinstance(t, Pair) and isinstance(t.car, Symbol):
                        names.append(t.car.name)
        return names

    def _parse_formals(self, datum):
        if isinstance(datum, Symbol):
            return datum
        if datum is NIL:
            return ([], None)
        if isinstance(datum, Pair):
            names = []
            cur = datum
            while isinstance(cur, Pair):
                if not isinstance(cur.car, Symbol):
                    raise SchemeError("malformed formals")
                names.append(cur.car.name)
                cur = cur.cdr
            if cur is NIL:
                return (names, None)
            if isinstance(cur, Symbol):
                return (names, cur.name)
            raise SchemeError("malformed formals")
        raise SchemeError("malformed formals")

    # ── run ──

    def run(self, source):
        try:
            forms = _parse(source)
        except SchemeError:
            raise
        except Exception as e:
            raise SchemeError(str(e))
        self.output = []
        env = Env(self.globals, parent=None, define_frame=self.globals)
        try:
            for form in forms:
                self.run_eval(form, env)
        except SchemeError as e:
            if not e.output:
                e.output = ''.join(self.output)
            raise
        except RecursionError:
            raise SchemeError("stack overflow")
        except Exception as e:
            raise SchemeError(str(e), output=''.join(self.output))
        return ''.join(self.output)

    # ── trampoline ──

    def run_eval(self, expr, env):
        result = self.eval_expr(expr, env)
        while isinstance(result, TailCall):
            proc = result.proc
            args = result.args
            if proc is self._orig_apply:
                f = args[0]
                extra = args[1:-1]
                lst = args[-1]
                lst_items = self._to_list(lst)
                all_args = extra + lst_items
                if not isinstance(f, (Closure, Builtin)):
                    raise SchemeError("apply: not a procedure")
                self._check_arity(f, all_args)
                result = TailCall(f, all_args)
                continue
            if not isinstance(proc, (Closure, Builtin)):
                raise SchemeError("not a procedure")
            self._check_arity(proc, args)
            if isinstance(proc, Builtin):
                result = proc.func(args)
            else:
                new_env = self._make_call_env(proc, args)
                body = proc.body
                for form in body[:-1]:
                    self.run_eval(form, new_env)
                result = self.eval_expr(body[-1], new_env)
        return result

    # ── eval ──

    def eval_expr(self, expr, env):
        if isinstance(expr, bool):
            return expr
        if isinstance(expr, int):
            return expr
        if isinstance(expr, str):
            return expr
        if isinstance(expr, Symbol):
            return _lookup(env, expr.name)
        if expr is NIL:
            raise SchemeError("cannot evaluate ()")
        if isinstance(expr, Pair):
            head = expr.car
            if isinstance(head, Symbol):
                nm = head.name
                if nm == 'quote': return self._eval_quote(expr)
                if nm == 'if': return self._eval_if(expr, env)
                if nm == 'define': return self._eval_define(expr, env)
                if nm == 'set!': return self._eval_set(expr, env)
                if nm == 'begin': return self._eval_begin(expr, env)
                if nm == 'cond': return self._eval_cond(expr, env)
                if nm == 'and': return self._eval_and(expr, env)
                if nm == 'or': return self._eval_or(expr, env)
                if nm == 'lambda': return self._eval_lambda(expr, env)
                if nm == 'let': return self._eval_let(expr, env)
                if nm == 'let*': return self._eval_letstar(expr, env)
                if nm == 'letrec': return self._eval_letrec(expr, env)
            return self._eval_application(expr, env)
        return expr

    def _eval_quote(self, expr):
        if not isinstance(expr.cdr, Pair):
            raise SchemeError("malformed quote")
        return expr.cdr.car

    def _eval_if(self, expr, env):
        rest = expr.cdr
        if not isinstance(rest, Pair):
            raise SchemeError("malformed if")
        test_val = self.run_eval(rest.car, env)
        if test_val is not False:
            if not isinstance(rest.cdr, Pair):
                raise SchemeError("malformed if")
            return self.eval_expr(rest.cdr.car, env)
        else:
            if not isinstance(rest.cdr, Pair):
                return UNSPECIFIED
            if not isinstance(rest.cdr.cdr, Pair):
                return UNSPECIFIED
            return self.eval_expr(rest.cdr.cdr.car, env)

    def _eval_define(self, expr, env):
        rest = expr.cdr
        if not isinstance(rest, Pair):
            raise SchemeError("malformed define")
        target = rest.car
        if isinstance(target, Symbol):
            if not isinstance(rest.cdr, Pair):
                raise SchemeError("malformed define")
            val = self.run_eval(rest.cdr.car, env)
            _define_var(env, target.name, val)
            return UNSPECIFIED
        elif isinstance(target, Pair):
            nm = target.car
            if not isinstance(nm, Symbol):
                raise SchemeError("malformed define")
            formals = self._parse_formals(target.cdr)
            body = self._to_list(rest.cdr)
            if not body:
                raise SchemeError("malformed define: empty body")
            closure = Closure(formals, body, env)
            _define_var(env, nm.name, closure)
            return UNSPECIFIED
        else:
            raise SchemeError("malformed define")

    def _eval_set(self, expr, env):
        rest = expr.cdr
        if not isinstance(rest, Pair):
            raise SchemeError("malformed set!")
        nm = rest.car
        if not isinstance(nm, Symbol):
            raise SchemeError("set!: name must be a symbol")
        if not isinstance(rest.cdr, Pair):
            raise SchemeError("malformed set!")
        val = self.run_eval(rest.cdr.car, env)
        _set_var(env, nm.name, val)
        return UNSPECIFIED

    def _eval_begin(self, expr, env):
        forms = self._to_list(expr.cdr)
        if not forms:
            raise SchemeError("malformed begin")
        for form in forms[:-1]:
            self.run_eval(form, env)
        return self.eval_expr(forms[-1], env)

    def _eval_cond(self, expr, env):
        clauses = self._to_list(expr.cdr)
        if not clauses:
            raise SchemeError("malformed cond")
        for i, clause in enumerate(clauses):
            if not isinstance(clause, Pair):
                raise SchemeError("malformed cond clause")
            test = clause.car
            body = self._to_list(clause.cdr)
            if isinstance(test, Symbol) and test.name == 'else':
                if i != len(clauses) - 1:
                    raise SchemeError("else must be last clause")
                if not body:
                    return UNSPECIFIED
                for form in body[:-1]:
                    self.run_eval(form, env)
                return self.eval_expr(body[-1], env)
            else:
                tv = self.run_eval(test, env)
                if tv is not False:
                    if not body:
                        return tv
                    for form in body[:-1]:
                        self.run_eval(form, env)
                    return self.eval_expr(body[-1], env)
        return UNSPECIFIED

    def _eval_and(self, expr, env):
        forms = self._to_list(expr.cdr)
        if not forms:
            return True
        for form in forms[:-1]:
            v = self.run_eval(form, env)
            if v is False:
                return False
        return self.eval_expr(forms[-1], env)

    def _eval_or(self, expr, env):
        forms = self._to_list(expr.cdr)
        if not forms:
            return False
        for form in forms[:-1]:
            v = self.run_eval(form, env)
            if v is not False:
                return v
        return self.eval_expr(forms[-1], env)

    def _eval_lambda(self, expr, env):
        rest = expr.cdr
        if not isinstance(rest, Pair):
            raise SchemeError("malformed lambda")
        formals = self._parse_formals(rest.car)
        body = self._to_list(rest.cdr)
        if not body:
            raise SchemeError("malformed lambda: empty body")
        return Closure(formals, body, env)

    def _eval_let(self, expr, env):
        rest = expr.cdr
        if not isinstance(rest, Pair):
            raise SchemeError("malformed let")
        second = rest.car
        if isinstance(second, Symbol):
            return self._eval_named_let(expr, env)
        bindings = self._to_list(second)
        inits = []
        for b in bindings:
            if not isinstance(b, Pair) or not isinstance(b.car, Symbol):
                raise SchemeError("malformed let binding")
            if not isinstance(b.cdr, Pair):
                raise SchemeError("malformed let binding")
            inits.append((b.car.name, self.run_eval(b.cdr.car, env)))
        f = Frame()
        for nm, val in inits:
            f.bindings[nm] = Box(val)
        let_env = Env(f, parent=env, define_frame=None)
        body = self._to_list(rest.cdr)
        if not body:
            raise SchemeError("malformed let: empty body")
        def_names = self._scan_defines(body)
        df = Frame()
        for nm in def_names:
            df.bindings[nm] = Box(Box.UNBOUND)
        body_env = Env(df, parent=let_env, define_frame=df)
        for form in body[:-1]:
            self.run_eval(form, body_env)
        return self.eval_expr(body[-1], body_env)

    def _eval_named_let(self, expr, env):
        rest = expr.cdr
        name = rest.car
        bindings_datum = rest.cdr.car
        body = self._to_list(rest.cdr.cdr)
        if not body:
            raise SchemeError("malformed named let: empty body")
        bindings = self._to_list(bindings_datum)
        inits = []
        names = []
        for b in bindings:
            if not isinstance(b, Pair) or not isinstance(b.car, Symbol):
                raise SchemeError("malformed let binding")
            if not isinstance(b.cdr, Pair):
                raise SchemeError("malformed let binding")
            names.append(b.car.name)
            inits.append(self.run_eval(b.cdr.car, env))
        f = Frame()
        let_env = Env(f, parent=env, define_frame=None)
        formals = (names, None)
        closure = Closure(formals, body, let_env)
        f.bindings[name.name] = Box(closure)
        return TailCall(closure, inits)

    def _eval_letstar(self, expr, env):
        rest = expr.cdr
        if not isinstance(rest, Pair):
            raise SchemeError("malformed let*")
        bindings = self._to_list(rest.car)
        cur_env = env
        for b in bindings:
            if not isinstance(b, Pair) or not isinstance(b.car, Symbol):
                raise SchemeError("malformed let* binding")
            if not isinstance(b.cdr, Pair):
                raise SchemeError("malformed let* binding")
            val = self.run_eval(b.cdr.car, cur_env)
            f = Frame()
            f.bindings[b.car.name] = Box(val)
            cur_env = Env(f, parent=cur_env, define_frame=None)
        body = self._to_list(rest.cdr)
        if not body:
            raise SchemeError("malformed let*: empty body")
        def_names = self._scan_defines(body)
        df = Frame()
        for nm in def_names:
            df.bindings[nm] = Box(Box.UNBOUND)
        body_env = Env(df, parent=cur_env, define_frame=df)
        for form in body[:-1]:
            self.run_eval(form, body_env)
        return self.eval_expr(body[-1], body_env)

    def _eval_letrec(self, expr, env):
        rest = expr.cdr
        if not isinstance(rest, Pair):
            raise SchemeError("malformed letrec")
        bindings = self._to_list(rest.car)
        f = Frame()
        for b in bindings:
            if not isinstance(b, Pair) or not isinstance(b.car, Symbol):
                raise SchemeError("malformed letrec binding")
            if not isinstance(b.cdr, Pair):
                raise SchemeError("malformed letrec binding")
            f.bindings[b.car.name] = Box(Box.UNBOUND)
        letrec_env = Env(f, parent=env, define_frame=None)
        for b in bindings:
            val = self.run_eval(b.cdr.car, letrec_env)
            f.bindings[b.car.name].value = val
        body = self._to_list(rest.cdr)
        if not body:
            raise SchemeError("malformed letrec: empty body")
        def_names = self._scan_defines(body)
        df = Frame()
        for nm in def_names:
            df.bindings[nm] = Box(Box.UNBOUND)
        body_env = Env(df, parent=letrec_env, define_frame=df)
        for form in body[:-1]:
            self.run_eval(form, body_env)
        return self.eval_expr(body[-1], body_env)

    def _eval_application(self, expr, env):
        proc = self.run_eval(expr.car, env)
        args = []
        cur = expr.cdr
        while isinstance(cur, Pair):
            args.append(self.run_eval(cur.car, env))
            cur = cur.cdr
        if cur is not NIL:
            raise SchemeError("dotted form in application")
        if not isinstance(proc, (Closure, Builtin)):
            raise SchemeError("not a procedure")
        self._check_arity(proc, args)
        return TailCall(proc, args)

    # ── format ──

    def _format_value(self, val, write_mode=False):
        parts = []
        stack = [('v', val)]
        while stack:
            action, item = stack.pop()
            if action == 's':
                parts.append(item)
            else:
                if isinstance(item, bool):
                    parts.append('#t' if item else '#f')
                elif isinstance(item, int):
                    parts.append(str(item))
                elif isinstance(item, str):
                    if write_mode:
                        parts.append(self._esc_str(item))
                    else:
                        parts.append(item)
                elif isinstance(item, Symbol):
                    parts.append(item.name)
                elif item is NIL:
                    parts.append('()')
                elif isinstance(item, _Unspecified):
                    pass
                elif isinstance(item, (Closure, Builtin)):
                    parts.append('#<procedure>')
                elif isinstance(item, Pair):
                    elems = []
                    cur = item
                    while isinstance(cur, Pair):
                        elems.append(cur.car)
                        cur = cur.cdr
                    stack.append(('s', ')'))
                    if cur is not NIL:
                        stack.append(('v', cur))
                        stack.append(('s', ' . '))
                    for i in range(len(elems) - 1, -1, -1):
                        stack.append(('v', elems[i]))
                        if i > 0:
                            stack.append(('s', ' '))
                    stack.append(('s', '('))
                else:
                    parts.append(str(item))
        return ''.join(parts)

    def _esc_str(self, s):
        r = ['"']
        for c in s:
            if c == '"': r.append('\\"')
            elif c == '\\': r.append('\\\\')
            elif c == '\n': r.append('\\n')
            else: r.append(c)
        r.append('"')
        return ''.join(r)

    # ── builtins setup ──

    def _setup_globals(self):
        g = self.globals.bindings

        def bi(name, func, min_args=0, max_args=None):
            b = Builtin(name, func, min_args, max_args)
            g[name] = Box(b)
            return b

        # ── arithmetic ──
        def _check_ints(args):
            for a in args:
                if isinstance(a, bool) or not isinstance(a, int):
                    raise SchemeError("expected integer")

        def _plus(args):
            _check_ints(args)
            s = 0
            for a in args: s += a
            return s

        def _times(args):
            _check_ints(args)
            p = 1
            for a in args: p *= a
            return p

        def _minus(args):
            _check_ints(args)
            if len(args) == 1: return -args[0]
            r = args[0]
            for a in args[1:]: r -= a
            return r

        def _quotient(args):
            _check_ints(args)
            if args[1] == 0: raise SchemeError("division by zero")
            q = abs(args[0]) // abs(args[1])
            if (args[0] < 0) ^ (args[1] < 0): q = -q
            return q

        def _remainder(args):
            _check_ints(args)
            if args[1] == 0: raise SchemeError("division by zero")
            r = abs(args[0]) % abs(args[1])
            if args[0] < 0: r = -r
            return r

        def _modulo(args):
            _check_ints(args)
            if args[1] == 0: raise SchemeError("division by zero")
            r = abs(args[0]) % abs(args[1])
            if args[1] < 0: r = -r
            return r

        def _eq(args):
            _check_ints(args)
            for i in range(len(args) - 1):
                if args[i] != args[i+1]: return False
            return True

        def _lt(args):
            _check_ints(args)
            for i in range(len(args) - 1):
                if not (args[i] < args[i+1]): return False
            return True

        def _gt(args):
            _check_ints(args)
            for i in range(len(args) - 1):
                if not (args[i] > args[i+1]): return False
            return True

        def _lte(args):
            _check_ints(args)
            for i in range(len(args) - 1):
                if not (args[i] <= args[i+1]): return False
            return True

        def _gte(args):
            _check_ints(args)
            for i in range(len(args) - 1):
                if not (args[i] >= args[i+1]): return False
            return True

        def _num2str(args):
            if isinstance(args[0], bool) or not isinstance(args[0], int):
                raise SchemeError("number->string: expected integer")
            n = args[0]
            radix = 10
            if len(args) == 2:
                if isinstance(args[1], bool) or not isinstance(args[1], int):
                    raise SchemeError("number->string: expected integer radix")
                radix = args[1]
            if radix not in (2, 8, 10, 16):
                raise SchemeError("number->string: invalid radix")
            neg = n < 0
            n = abs(n)
            if n == 0:
                return '0'
            digits = []
            while n > 0:
                digits.append('0123456789abcdef'[n % radix])
                n //= radix
            if neg: digits.append('-')
            return ''.join(reversed(digits))

        bi('+', _plus, 0)
        bi('*', _times, 0)
        bi('-', _minus, 1)
        bi('quotient', _quotient, 2, 2)
        bi('remainder', _remainder, 2, 2)
        bi('modulo', _modulo, 2, 2)
        bi('=', _eq, 1)
        bi('<', _lt, 1)
        bi('>', _gt, 1)
        bi('<=', _lte, 1)
        bi('>=', _gte, 1)
        bi('number->string', _num2str, 1, 2)

        # ── pairs/lists ──
        def _cons(args):
            return Pair(args[0], args[1])

        def _car(args):
            p = args[0]
            if not isinstance(p, Pair):
                raise SchemeError("car: not a pair")
            return p.car

        def _cdr(args):
            p = args[0]
            if not isinstance(p, Pair):
                raise SchemeError("cdr: not a pair")
            return p.cdr

        def _list(args):
            return self._args_to_list(args)

        def _null_p(args):
            return args[0] is NIL

        def _pair_p(args):
            return isinstance(args[0], Pair)

        def _list_p(args):
            return self._is_proper_list(args[0])

        def _length(args):
            cur = args[0]
            n = 0
            while isinstance(cur, Pair):
                n += 1
                cur = cur.cdr
            if cur is not NIL:
                raise SchemeError("length: not a proper list")
            return n

        def _append(args):
            if not args: return NIL
            result = args[-1]
            for i in range(len(args) - 2, -1, -1):
                lst = args[i]
                cur = lst
                while isinstance(cur, Pair):
                    cur = cur.cdr
                if cur is not NIL:
                    raise SchemeError("append: improper list")
                elems = []
                cur = lst
                while isinstance(cur, Pair):
                    elems.append(cur.car)
                    cur = cur.cdr
                for e in reversed(elems):
                    result = Pair(e, result)
            return result

        def _reverse(args):
            cur = args[0]
            result = NIL
            while isinstance(cur, Pair):
                result = Pair(cur.car, result)
                cur = cur.cdr
            if cur is not NIL:
                raise SchemeError("reverse: not a proper list")
            return result

        def _apply(args):
            raise SchemeError("apply called as value in non-tail context")

        self._orig_apply = bi('apply', _apply, 2)

        # ── equality/predicates ──
        def _eq_p(args):
            a, b = args[0], args[1]
            if isinstance(a, bool) or isinstance(b, bool):
                return a is b
            if isinstance(a, int) and isinstance(b, int):
                return a == b
            if a is NIL and b is NIL:
                return True
            if isinstance(a, Symbol) and isinstance(b, Symbol):
                return a is b
            return a is b

        def _equal_p(args):
            return self._equal(args[0], args[1])

        def _not(args):
            return args[0] is False

        def _number_p(args):
            return isinstance(args[0], int) and not isinstance(args[0], bool)

        def _symbol_p(args):
            return isinstance(args[0], Symbol)

        def _string_p(args):
            return isinstance(args[0], str)

        def _procedure_p(args):
            return isinstance(args[0], (Closure, Builtin))

        def _string_append(args):
            for a in args:
                if not isinstance(a, str):
                    raise SchemeError("string-append: expected string")
            return ''.join(args)

        bi('cons', _cons, 2, 2)
        bi('car', _car, 1, 1)
        bi('cdr', _cdr, 1, 1)
        bi('list', _list, 0)
        bi('null?', _null_p, 1, 1)
        bi('pair?', _pair_p, 1, 1)
        bi('list?', _list_p, 1, 1)
        bi('length', _length, 1, 1)
        bi('append', _append, 0)
        bi('reverse', _reverse, 1, 1)
        bi('eq?', _eq_p, 2, 2)
        bi('equal?', _equal_p, 2, 2)
        bi('not', _not, 1, 1)
        bi('number?', _number_p, 1, 1)
        bi('symbol?', _symbol_p, 1, 1)
        bi('string?', _string_p, 1, 1)
        bi('procedure?', _procedure_p, 1, 1)
        bi('string-append', _string_append, 0)

        # ── output/errors ──
        def _display(args):
            self.output.append(self._format_value(args[0], False))
            return UNSPECIFIED

        def _newline(args):
            self.output.append('\n')
            return UNSPECIFIED

        def _error(args):
            msg = args[0]
            if not isinstance(msg, str):
                raise SchemeError(str(msg))
            parts = [msg]
            for ir in args[1:]:
                parts.append(' ' + self._format_value(ir, True))
            raise SchemeError(''.join(parts))

        bi('display', _display, 1, 1)
        bi('newline', _newline, 0, 0)
        bi('error', _error, 1)

    def _equal(self, a, b):
        stack = [(a, b)]
        while stack:
            x, y = stack.pop()
            if x is y:
                continue
            if isinstance(x, bool) or isinstance(y, bool):
                if not (isinstance(x, bool) and isinstance(y, bool)): return False
                if x is not y: return False
            elif isinstance(x, int) and isinstance(y, int):
                if x != y: return False
            elif isinstance(x, str) and isinstance(y, str):
                if x != y: return False
            elif isinstance(x, Symbol) and isinstance(y, Symbol):
                if x.name != y.name: return False
            elif x is NIL and y is NIL:
                pass
            elif isinstance(x, Pair) and isinstance(y, Pair):
                stack.append((x.car, y.car))
                stack.append((x.cdr, y.cdr))
            else:
                return False
        return True


# ─── Public API ───────────────────────────────────────────────────────────────

def run(source):
    interp = Interpreter()
    return interp.run(source)
