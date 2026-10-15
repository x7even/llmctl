import sys
import threading

try:
    sys.set_int_max_str_digits(0)
except (AttributeError, ValueError):
    pass


class SchemeError(Exception):
    def __init__(self, msg, output=''):
        super().__init__(msg)
        self.output = output


class Symbol:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name
    def __repr__(self):
        return self.name


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
        return '<unspecified>'
UNSPECIFIED = _Unspecified()


class _Unset:
    pass
UNSET = _Unset()


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


class Frame:
    __slots__ = ('bindings', 'parent')
    def __init__(self, parent=None):
        self.bindings = {}
        self.parent = parent

    def lookup(self, name):
        f = self
        while f is not None:
            if name in f.bindings:
                val = f.bindings[name]
                if isinstance(val, _Unset):
                    return UNSET
                return val
            f = f.parent
        return None

    def set(self, name, value):
        f = self
        while f is not None:
            if name in f.bindings:
                f.bindings[name] = value
                return True
            f = f.parent
        return False


class _TailCall:
    __slots__ = ('proc', 'args')
    def __init__(self, proc, args):
        self.proc = proc
        self.args = args


# ─── Reader ────────────────────────────────────────────────────────────────────

class Reader:
    def __init__(self, source):
        self.src = source
        self.pos = 0
        self.n = len(source)

    def read_all(self):
        forms = []
        while True:
            self._skip_ws()
            if self.pos >= self.n:
                break
            forms.append(self._read_datum())
        return forms

    def _skip_ws(self):
        while self.pos < self.n:
            c = self.src[self.pos]
            if c in ' \t\n\r':
                self.pos += 1
            elif c == ';':
                while self.pos < self.n and self.src[self.pos] != '\n':
                    self.pos += 1
            else:
                break

    def _read_datum(self):
        self._skip_ws()
        if self.pos >= self.n:
            raise SchemeError("unexpected end of input")
        c = self.src[self.pos]
        if c == '(':
            return self._read_list()
        if c == ')':
            raise SchemeError("unexpected )")
        if c == "'":
            self.pos += 1
            d = self._read_datum()
            return Pair(Symbol('quote'), Pair(d, NIL))
        if c == '"':
            return self._read_string()
        return self._read_atom()

    def _read_list(self):
        self.pos += 1  # skip (
        items = []
        dotted = False
        dotted_rest = None
        while True:
            self._skip_ws()
            if self.pos >= self.n:
                raise SchemeError("unexpected end of input in list")
            c = self.src[self.pos]
            if c == ')':
                self.pos += 1
                break
            if c == '(':
                items.append(self._read_list())
                continue
            if c == "'":
                self.pos += 1
                d = self._read_datum()
                items.append(Pair(Symbol('quote'), Pair(d, NIL)))
                continue
            if c == '"':
                items.append(self._read_string())
                continue
            # read token
            tok = self._read_token()
            if tok == '.' and not dotted:
                if len(items) == 0:
                    raise SchemeError("dot must be preceded by at least one element")
                dotted = True
                self._skip_ws()
                if self.pos >= self.n:
                    raise SchemeError("unexpected end of input after dot")
                c2 = self.src[self.pos]
                if c2 == ')':
                    raise SchemeError("dot must be followed by a datum")
                elif c2 == '(':
                    dotted_rest = self._read_list()
                elif c2 == "'":
                    self.pos += 1
                    d = self._read_datum()
                    dotted_rest = Pair(Symbol('quote'), Pair(d, NIL))
                elif c2 == '"':
                    dotted_rest = self._read_string()
                else:
                    dotted_rest = self._read_atom()
                self._skip_ws()
                if self.pos >= self.n or self.src[self.pos] != ')':
                    raise SchemeError("expected ) after dotted pair")
                self.pos += 1
                break
            else:
                items.append(self._parse_token(tok))
        if dotted:
            result = dotted_rest
            for item in reversed(items):
                result = Pair(item, result)
            return result
        result = NIL
        for item in reversed(items):
            result = Pair(item, result)
        return result

    def _read_token(self):
        start = self.pos
        while self.pos < self.n:
            c = self.src[self.pos]
            if c in ' \t\n\r()";\'':
                break
            self.pos += 1
        return self.src[start:self.pos]

    def _read_atom(self):
        tok = self._read_token()
        if not tok:
            raise SchemeError("unexpected character")
        return self._parse_token(tok)

    def _parse_token(self, tok):
        if tok == '#t':
            return True
        if tok == '#f':
            return False
        if tok.startswith('#'):
            raise SchemeError(f"invalid syntax: {tok}")
        if self._is_int(tok):
            return int(tok)
        return Symbol(tok)

    @staticmethod
    def _is_int(tok):
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

    def _read_string(self):
        self.pos += 1  # skip "
        chars = []
        while self.pos < self.n:
            c = self.src[self.pos]
            if c == '"':
                self.pos += 1
                return ''.join(chars)
            if c == '\\':
                self.pos += 1
                if self.pos >= self.n:
                    raise SchemeError("unterminated string")
                c2 = self.src[self.pos]
                if c2 == '"':
                    chars.append('"')
                elif c2 == '\\':
                    chars.append('\\')
                elif c2 == 'n':
                    chars.append('\n')
                else:
                    raise SchemeError(f"invalid escape: \\{c2}")
                self.pos += 1
            else:
                chars.append(c)
                self.pos += 1
        raise SchemeError("unterminated string")


# ─── Interpreter ───────────────────────────────────────────────────────────────

class Interpreter:
    def __init__(self):
        self.output = []
        self.genv = Frame()
        self._setup_globals()

    def get_output(self):
        return ''.join(self.output)

    def error(self, msg):
        raise SchemeError(msg, self.get_output())

    # ── helpers ──

    def _to_list(self, obj):
        items = []
        while isinstance(obj, Pair):
            items.append(obj.car)
            obj = obj.cdr
        if obj is not NIL:
            self.error("improper list")
        return items

    def _is_proper_list(self, obj):
        while isinstance(obj, Pair):
            obj = obj.cdr
        return obj is NIL

    def _scheme_to_python(self, obj):
        items = []
        while isinstance(obj, Pair):
            items.append(obj.car)
            obj = obj.cdr
        return items

    def _python_to_scheme(self, items):
        result = NIL
        for item in reversed(items):
            result = Pair(item, result)
        return result

    def _truthy(self, v):
        return v is not False

    def _check_int(self, x, name):
        if isinstance(x, bool) or not isinstance(x, int):
            self.error(f"{name}: expected integer")

    # ── evaluation ──

    def eval_expr(self, expr, env):
        return self._eval(expr, env, False)

    def eval_tail(self, expr, env):
        while True:
            result = self._eval(expr, env, True)
            if isinstance(result, _TailCall):
                proc, args = result.proc, result.args
                if isinstance(proc, Closure):
                    env = self._make_call_env(proc, args)
                    body = proc.body
                    for form in body[:-1]:
                        self.eval_expr(form, env)
                    expr = body[-1]
                elif isinstance(proc, Builtin):
                    return proc.func(args)
                else:
                    self.error("not a procedure")
            else:
                return result

    def _eval(self, expr, env, tail):
        # self-evaluating
        if isinstance(expr, int) and not isinstance(expr, bool):
            return expr
        if isinstance(expr, bool):
            return expr
        if isinstance(expr, str):
            return expr
        if expr is NIL:
            self.error("cannot evaluate ()")
        if isinstance(expr, Symbol):
            val = env.lookup(expr.name)
            if val is None:
                self.error(f"unbound variable: {expr.name}")
            if isinstance(val, _Unset):
                self.error(f"unbound variable: {expr.name}")
            return val
        if isinstance(expr, Pair):
            head = expr.car
            if isinstance(head, Symbol):
                name = head.name
                if name == 'quote':
                    return self._eval_quote(expr, env)
                if name == 'if':
                    return self._eval_if(expr, env, tail)
                if name == 'define':
                    return self._eval_define(expr, env)
                if name == 'set!':
                    return self._eval_set(expr, env)
                if name == 'begin':
                    return self._eval_begin(expr, env, tail)
                if name == 'cond':
                    return self._eval_cond(expr, env, tail)
                if name == 'and':
                    return self._eval_and(expr, env, tail)
                if name == 'or':
                    return self._eval_or(expr, env, tail)
                if name == 'lambda':
                    return self._eval_lambda(expr, env)
                if name == 'let':
                    return self._eval_let(expr, env, tail)
                if name == 'let*':
                    return self._eval_letstar(expr, env, tail)
                if name == 'letrec':
                    return self._eval_letrec(expr, env, tail)
                if name == 'apply':
                    return self._eval_apply(expr, env, tail)
            # application
            proc = self.eval_expr(head, env)
            operands = []
            cur = expr.cdr
            while isinstance(cur, Pair):
                operands.append(self.eval_expr(cur.car, env))
                cur = cur.cdr
            if cur is not NIL:
                self.error("dotted form used as application")
            if not isinstance(proc, (Closure, Builtin)):
                self.error("not a procedure")
            self._check_arity(proc, len(operands))
            if tail:
                return _TailCall(proc, operands)
            return self._call_proc(proc, operands)
        # shouldn't reach here
        return expr

    # ── special forms ──

    def _eval_quote(self, expr, env):
        items = self._to_list(expr.cdr)
        if len(items) != 1:
            self.error("malformed quote")
        return items[0]

    def _eval_if(self, expr, env, tail):
        items = self._to_list(expr.cdr)
        if len(items) < 2 or len(items) > 3:
            self.error("malformed if")
        test = self.eval_expr(items[0], env)
        if self._truthy(test):
            branch = items[1]
        elif len(items) == 3:
            branch = items[2]
        else:
            return UNSPECIFIED
        if tail:
            return self._eval(branch, env, True)
        return self.eval_expr(branch, env)

    def _eval_define(self, expr, env):
        items = self._to_list(expr.cdr)
        if len(items) < 2:
            self.error("malformed define")
        target = items[0]
        if isinstance(target, Symbol):
            if len(items) != 2:
                self.error("malformed define")
            value = self.eval_expr(items[1], env)
            env.bindings[target.name] = value
            return UNSPECIFIED
        if isinstance(target, Pair):
            if not isinstance(target.car, Symbol):
                self.error("malformed define")
            name = target.car.name
            formals = target.cdr
            body = items[1:]
            if len(body) == 0:
                self.error("empty body")
            self._validate_formals(formals)
            closure = Closure(formals, body, env)
            env.bindings[name] = closure
            return UNSPECIFIED
        self.error("malformed define")

    def _eval_set(self, expr, env):
        items = self._to_list(expr.cdr)
        if len(items) != 2:
            self.error("malformed set!")
        name = items[0]
        if not isinstance(name, Symbol):
            self.error("malformed set!")
        value = self.eval_expr(items[1], env)
        if not env.set(name.name, value):
            self.error(f"unbound variable: {name.name}")
        return UNSPECIFIED

    def _eval_begin(self, expr, env, tail):
        items = self._to_list(expr.cdr)
        if len(items) == 0:
            self.error("malformed begin")
        for i, form in enumerate(items):
            if i == len(items) - 1:
                if tail:
                    return self._eval(form, env, True)
                return self.eval_expr(form, env)
            else:
                self.eval_expr(form, env)

    def _eval_cond(self, expr, env, tail):
        clauses = self._to_list(expr.cdr)
        if len(clauses) == 0:
            self.error("malformed cond")
        for i, clause in enumerate(clauses):
            if not isinstance(clause, Pair):
                self.error("malformed cond clause")
            test = clause.car
            body = self._to_list(clause.cdr)
            if isinstance(test, Symbol) and test.name == 'else':
                if i != len(clauses) - 1:
                    self.error("else must be last clause")
                if len(body) == 0:
                    return UNSPECIFIED
                for j, e in enumerate(body):
                    if j == len(body) - 1:
                        if tail:
                            return self._eval(e, env, True)
                        return self.eval_expr(e, env)
                    else:
                        self.eval_expr(e, env)
            else:
                test_val = self.eval_expr(test, env)
                if self._truthy(test_val):
                    if len(body) == 0:
                        return test_val
                    for j, e in enumerate(body):
                        if j == len(body) - 1:
                            if tail:
                                return self._eval(e, env, True)
                            return self.eval_expr(e, env)
                        else:
                            self.eval_expr(e, env)
        return UNSPECIFIED

    def _eval_and(self, expr, env, tail):
        items = self._to_list(expr.cdr)
        if len(items) == 0:
            return True
        for i, e in enumerate(items):
            if i == len(items) - 1:
                if tail:
                    return self._eval(e, env, True)
                return self.eval_expr(e, env)
            else:
                val = self.eval_expr(e, env)
                if not self._truthy(val):
                    return False
        return True

    def _eval_or(self, expr, env, tail):
        items = self._to_list(expr.cdr)
        if len(items) == 0:
            return False
        for i, e in enumerate(items):
            if i == len(items) - 1:
                if tail:
                    return self._eval(e, env, True)
                return self.eval_expr(e, env)
            else:
                val = self.eval_expr(e, env)
                if self._truthy(val):
                    return val
        return False

    def _eval_lambda(self, expr, env):
        items = self._to_list(expr.cdr)
        if len(items) < 2:
            self.error("malformed lambda")
        formals = items[0]
        body = items[1:]
        self._validate_formals(formals)
        return Closure(formals, body, env)

    def _eval_let(self, expr, env, tail):
        items = self._to_list(expr.cdr)
        if len(items) < 1:
            self.error("malformed let")
        # Determine if named let
        if isinstance(items[0], Symbol):
            return self._eval_named_let(items, env, tail)
        bindings = self._to_list(items[0])
        body = items[1:]
        if len(body) == 0:
            self.error("empty body")
        # evaluate inits in outer env
        inits = []
        for b in bindings:
            if not isinstance(b, Pair):
                self.error("malformed let binding")
            var = b.car
            if not isinstance(var, Symbol):
                self.error("malformed let binding")
            init_list = self._to_list(b.cdr)
            if len(init_list) != 1:
                self.error("malformed let binding")
            inits.append(self.eval_expr(init_list[0], env))
        frame = Frame(parent=env)
        for b, v in zip(bindings, inits):
            frame.bindings[b.car.name] = v
        self._pre_bind_internal_defs(body, frame)
        return self._exec_body(body, frame, tail)

    def _eval_named_let(self, items, env, tail):
        name = items[0]
        bindings = self._to_list(items[1])
        body = items[2:]
        if len(body) == 0:
            self.error("empty body")
        frame = Frame(parent=env)
        formals = []
        inits = []
        for b in bindings:
            if not isinstance(b, Pair):
                self.error("malformed let binding")
            var = b.car
            if not isinstance(var, Symbol):
                self.error("malformed let binding")
            init_list = self._to_list(b.cdr)
            if len(init_list) != 1:
                self.error("malformed let binding")
            formals.append(var)
            inits.append(self.eval_expr(init_list[0], env))
        formals_scheme = self._python_to_scheme(formals)
        closure = Closure(formals_scheme, body, frame)
        frame.bindings[name.name] = closure
        self._check_arity(closure, len(inits))
        if tail:
            return _TailCall(closure, inits)
        return self._call_proc(closure, inits)

    def _eval_letstar(self, expr, env, tail):
        items = self._to_list(expr.cdr)
        if len(items) < 1:
            self.error("malformed let*")
        bindings = self._to_list(items[0])
        body = items[1:]
        if len(body) == 0:
            self.error("empty body")
        frame = Frame(parent=env)
        for b in bindings:
            if not isinstance(b, Pair):
                self.error("malformed let* binding")
            var = b.car
            if not isinstance(var, Symbol):
                self.error("malformed let* binding")
            init_list = self._to_list(b.cdr)
            if len(init_list) != 1:
                self.error("malformed let* binding")
            val = self.eval_expr(init_list[0], frame)
            frame.bindings[var.name] = val
        self._pre_bind_internal_defs(body, frame)
        return self._exec_body(body, frame, tail)

    def _eval_letrec(self, expr, env, tail):
        items = self._to_list(expr.cdr)
        if len(items) < 1:
            self.error("malformed letrec")
        bindings = self._to_list(items[0])
        body = items[1:]
        if len(body) == 0:
            self.error("empty body")
        frame = Frame(parent=env)
        for b in bindings:
            if not isinstance(b, Pair):
                self.error("malformed letrec binding")
            var = b.car
            if not isinstance(var, Symbol):
                self.error("malformed letrec binding")
            frame.bindings[var.name] = UNSET
        for b in bindings:
            var = b.car
            init_list = self._to_list(b.cdr)
            if len(init_list) != 1:
                self.error("malformed letrec binding")
            val = self.eval_expr(init_list[0], frame)
            frame.bindings[var.name] = val
        self._pre_bind_internal_defs(body, frame)
        return self._exec_body(body, frame, tail)

    def _eval_apply(self, expr, env, tail):
        operands = self._to_list(expr.cdr)
        if len(operands) < 2:
            self.error("apply requires at least 2 arguments")
        args = [self.eval_expr(o, env) for o in operands]
        proc = args[0]
        last = args[-1]
        if not self._is_proper_list(last):
            self.error("apply: last argument must be a proper list")
        expanded = args[1:-1] + self._scheme_to_python(last)
        if not isinstance(proc, (Closure, Builtin)):
            self.error("not a procedure")
        self._check_arity(proc, len(expanded))
        if tail:
            return _TailCall(proc, expanded)
        return self._call_proc(proc, expanded)

    # ── body / internal defs ──

    def _get_define_name(self, form):
        if not isinstance(form, Pair):
            return None
        if not (isinstance(form.car, Symbol) and form.car.name == 'define'):
            return None
        items = []
        cur = form.cdr
        while isinstance(cur, Pair):
            items.append(cur.car)
            cur = cur.cdr
        if len(items) < 2:
            return None
        target = items[0]
        if isinstance(target, Symbol):
            return target.name
        if isinstance(target, Pair) and isinstance(target.car, Symbol):
            return target.car.name
        return None

    def _pre_bind_internal_defs(self, body, frame):
        for form in body:
            name = self._get_define_name(form)
            if name is not None:
                frame.bindings[name] = UNSET

    def _exec_body(self, body, frame, tail):
        for i, form in enumerate(body):
            if i == len(body) - 1:
                if tail:
                    return self._eval(form, frame, True)
                return self.eval_expr(form, frame)
            else:
                self.eval_expr(form, frame)

    # ── procedure calling ──

    def _validate_formals(self, formals):
        if isinstance(formals, Symbol):
            return
        if formals is NIL:
            return
        if isinstance(formals, Pair):
            f = formals
            while isinstance(f, Pair):
                if not isinstance(f.car, Symbol):
                    self.error("invalid formals")
                f = f.cdr
            if isinstance(f, Symbol) or f is NIL:
                return
            self.error("invalid formals")
        self.error("invalid formals")

    def _check_arity(self, proc, nargs):
        if isinstance(proc, Builtin):
            if nargs < proc.min_args:
                self.error(f"{proc.name}: too few arguments")
            if proc.max_args is not None and nargs > proc.max_args:
                self.error(f"{proc.name}: too many arguments")
        elif isinstance(proc, Closure):
            formals = proc.formals
            if isinstance(formals, Symbol):
                return
            if formals is NIL:
                if nargs != 0:
                    self.error("wrong number of arguments")
                return
            if isinstance(formals, Pair):
                required = 0
                f = formals
                while isinstance(f, Pair):
                    required += 1
                    f = f.cdr
                if isinstance(f, Symbol):
                    if nargs < required:
                        self.error("too few arguments")
                elif f is NIL:
                    if nargs != required:
                        self.error("wrong number of arguments")
                else:
                    self.error("invalid formals")
                return
            self.error("invalid formals")

    def _make_call_env(self, closure, args):
        frame = Frame(parent=closure.env)
        self._bind_formals(closure.formals, args, frame)
        self._pre_bind_internal_defs(closure.body, frame)
        return frame

    def _bind_formals(self, formals, args, frame):
        if isinstance(formals, Symbol):
            frame.bindings[formals.name] = self._python_to_scheme(args)
            return
        if formals is NIL:
            return
        if isinstance(formals, Pair):
            i = 0
            f = formals
            while isinstance(f, Pair):
                if i >= len(args):
                    self.error("too few arguments")
                frame.bindings[f.car.name] = args[i]
                i += 1
                f = f.cdr
            if isinstance(f, Symbol):
                frame.bindings[f.name] = self._python_to_scheme(args[i:])
            elif f is NIL:
                pass
            else:
                self.error("invalid formals")
            return
        self.error("invalid formals")

    def _call_proc(self, proc, args):
        if isinstance(proc, Builtin):
            return proc.func(args)
        if isinstance(proc, Closure):
            env = self._make_call_env(proc, args)
            body = proc.body
            for form in body[:-1]:
                self.eval_expr(form, env)
            return self.eval_tail(body[-1], env)
        self.error("not a procedure")

    # ── display / write ──

    def _display_repr(self, obj, write=False):
        if obj is True:
            return '#t'
        if obj is False:
            return '#f'
        if isinstance(obj, bool):
            return '#t' if obj else '#f'
        if isinstance(obj, int):
            return self._int_to_str(obj)
        if isinstance(obj, str):
            if write:
                return self._write_string(obj)
            return obj
        if isinstance(obj, Symbol):
            return obj.name
        if obj is NIL:
            return '()'
        if isinstance(obj, Pair):
            return self._display_pair(obj, write)
        if isinstance(obj, (Closure, Builtin)):
            return '#<procedure>'
        if isinstance(obj, _Unspecified):
            return ''
        return str(obj)

    def _display_pair(self, pair, write):
        parts = []
        cur = pair
        while isinstance(cur, Pair):
            parts.append(self._display_repr(cur.car, write))
            cur = cur.cdr
        if cur is NIL:
            return '(' + ' '.join(parts) + ')'
        return '(' + ' '.join(parts) + ' . ' + self._display_repr(cur, write) + ')'

    def _write_string(self, s):
        parts = ['"']
        for c in s:
            if c == '"':
                parts.append('\\"')
            elif c == '\\':
                parts.append('\\\\')
            elif c == '\n':
                parts.append('\\n')
            else:
                parts.append(c)
        parts.append('"')
        return ''.join(parts)

    @staticmethod
    def _int_to_str(n):
        if n == 0:
            return '0'
        neg = n < 0
        n = abs(n)
        digits = []
        while n > 0:
            digits.append(chr(48 + n % 10))
            n //= 10
        if neg:
            digits.append('-')
        return ''.join(reversed(digits))

    # ── globals setup ──

    def _setup_globals(self):
        g = self.genv
        self._def(g, '+', self._bi_plus, 0)
        self._def(g, '*', self._bi_mul, 0)
        self._def(g, '-', self._bi_sub, 1)
        self._def(g, 'quotient', self._bi_quotient, 2, 2)
        self._def(g, 'remainder', self._bi_remainder, 2, 2)
        self._def(g, 'modulo', self._bi_modulo, 2, 2)
        self._def(g, '=', self._bi_eq, 1)
        self._def(g, '<', self._bi_lt, 1)
        self._def(g, '>', self._bi_gt, 1)
        self._def(g, '<=', self._bi_le, 1)
        self._def(g, '>=', self._bi_ge, 1)
        self._def(g, 'number->string', self._bi_num2str, 1, 2)
        self._def(g, 'cons', self._bi_cons, 2, 2)
        self._def(g, 'car', self._bi_car, 1, 1)
        self._def(g, 'cdr', self._bi_cdr, 1, 1)
        self._def(g, 'list', self._bi_list, 0)
        self._def(g, 'null?', self._bi_null, 1, 1)
        self._def(g, 'pair?', self._bi_pair, 1, 1)
        self._def(g, 'list?', self._bi_listp, 1, 1)
        self._def(g, 'length', self._bi_length, 1, 1)
        self._def(g, 'append', self._bi_append, 0)
        self._def(g, 'reverse', self._bi_reverse, 1, 1)
        self._def(g, 'apply', self._bi_apply, 2)
        self._def(g, 'eq?', self._bi_eqq, 2, 2)
        self._def(g, 'equal?', self._bi_equal, 2, 2)
        self._def(g, 'not', self._bi_not, 1, 1)
        self._def(g, 'number?', self._bi_numberp, 1, 1)
        self._def(g, 'symbol?', self._bi_symbolp, 1, 1)
        self._def(g, 'string?', self._bi_stringp, 1, 1)
        self._def(g, 'procedure?', self._bi_procp, 1, 1)
        self._def(g, 'string-append', self._bi_str_append, 0)
        self._def(g, 'display', self._bi_display, 1, 1)
        self._def(g, 'newline', self._bi_newline, 0, 0)
        self._def(g, 'error', self._bi_error, 1)

    def _def(self, env, name, func, min_args=0, max_args=None):
        env.bindings[name] = Builtin(name, func, min_args, max_args)

    # ── builtins ──

    def _bi_plus(self, args):
        s = 0
        for a in args:
            self._check_int(a, '+')
            s += a
        return s

    def _bi_mul(self, args):
        p = 1
        for a in args:
            self._check_int(a, '*')
            p *= a
        return p

    def _bi_sub(self, args):
        self._check_int(args[0], '-')
        if len(args) == 1:
            return -args[0]
        r = args[0]
        for a in args[1:]:
            self._check_int(a, '-')
            r -= a
        return r

    def _bi_quotient(self, args):
        a, b = args
        self._check_int(a, 'quotient')
        self._check_int(b, 'quotient')
        if b == 0:
            self.error("division by zero")
        q = abs(a) // abs(b)
        if (a < 0) != (b < 0):
            q = -q
        return q

    def _bi_remainder(self, args):
        a, b = args
        self._check_int(a, 'remainder')
        self._check_int(b, 'remainder')
        if b == 0:
            self.error("division by zero")
        q = abs(a) // abs(b)
        if (a < 0) != (b < 0):
            q = -q
        return a - q * b

    def _bi_modulo(self, args):
        a, b = args
        self._check_int(a, 'modulo')
        self._check_int(b, 'modulo')
        if b == 0:
            self.error("division by zero")
        q = abs(a) // abs(b)
        if (a < 0) != (b < 0):
            q = -q
        r = a - q * b
        if r != 0 and (r < 0) != (b < 0):
            r += b
        return r

    def _bi_eq(self, args):
        for a in args:
            self._check_int(a, '=')
        for i in range(len(args) - 1):
            if args[i] != args[i + 1]:
                return False
        return True

    def _bi_lt(self, args):
        for a in args:
            self._check_int(a, '<')
        for i in range(len(args) - 1):
            if not args[i] < args[i + 1]:
                return False
        return True

    def _bi_gt(self, args):
        for a in args:
            self._check_int(a, '>')
        for i in range(len(args) - 1):
            if not args[i] > args[i + 1]:
                return False
        return True

    def _bi_le(self, args):
        for a in args:
            self._check_int(a, '<=')
        for i in range(len(args) - 1):
            if not args[i] <= args[i + 1]:
                return False
        return True

    def _bi_ge(self, args):
        for a in args:
            self._check_int(a, '>=')
        for i in range(len(args) - 1):
            if not args[i] >= args[i + 1]:
                return False
        return True

    def _bi_num2str(self, args):
        n = args[0]
        self._check_int(n, 'number->string')
        radix = 10
        if len(args) == 2:
            radix = args[1]
            self._check_int(radix, 'number->string')
            if radix not in (2, 8, 10, 16):
                self.error("number->string: invalid radix")
        if n == 0:
            return '0'
        neg = n < 0
        n = abs(n)
        digits = '0123456789abcdef'
        parts = []
        while n > 0:
            parts.append(digits[n % radix])
            n //= radix
        if neg:
            parts.append('-')
        return ''.join(reversed(parts))

    def _bi_cons(self, args):
        return Pair(args[0], args[1])

    def _bi_car(self, args):
        p = args[0]
        if not isinstance(p, Pair):
            self.error("car: not a pair")
        return p.car

    def _bi_cdr(self, args):
        p = args[0]
        if not isinstance(p, Pair):
            self.error("cdr: not a pair")
        return p.cdr

    def _bi_list(self, args):
        return self._python_to_scheme(args)

    def _bi_null(self, args):
        return args[0] is NIL

    def _bi_pair(self, args):
        return isinstance(args[0], Pair)

    def _bi_listp(self, args):
        return self._is_proper_list(args[0])

    def _bi_length(self, args):
        obj = args[0]
        count = 0
        while isinstance(obj, Pair):
            count += 1
            obj = obj.cdr
        if obj is not NIL:
            self.error("length: not a proper list")
        return count

    def _bi_append(self, args):
        if len(args) == 0:
            return NIL
        result = args[-1]
        for lst in reversed(args[:-1]):
            if not self._is_proper_list(lst):
                self.error("append: not a proper list")
            elements = []
            cur = lst
            while isinstance(cur, Pair):
                elements.append(cur.car)
                cur = cur.cdr
            for elem in reversed(elements):
                result = Pair(elem, result)
        return result

    def _bi_reverse(self, args):
        lst = args[0]
        if not self._is_proper_list(lst):
            self.error("reverse: not a proper list")
        result = NIL
        cur = lst
        while isinstance(cur, Pair):
            result = Pair(cur.car, result)
            cur = cur.cdr
        return result

    def _bi_apply(self, args):
        proc = args[0]
        last = args[-1]
        if not self._is_proper_list(last):
            self.error("apply: last argument must be a proper list")
        expanded = list(args[1:-1]) + self._scheme_to_python(last)
        if not isinstance(proc, (Closure, Builtin)):
            self.error("apply: not a procedure")
        self._check_arity(proc, len(expanded))
        return self._call_proc(proc, expanded)

    def _bi_eqq(self, args):
        a, b = args
        if isinstance(a, bool) and isinstance(b, bool):
            return a is b
        if isinstance(a, bool) or isinstance(b, bool):
            return False
        if isinstance(a, int) and isinstance(b, int):
            return a == b
        if isinstance(a, Symbol) and isinstance(b, Symbol):
            return a.name == b.name
        if a is NIL and b is NIL:
            return True
        if isinstance(a, _Unspecified) and isinstance(b, _Unspecified):
            return True
        return a is b

    def _bi_equal(self, args):
        return self._equal(args[0], args[1])

    def _equal(self, a, b):
        if isinstance(a, bool) and isinstance(b, bool):
            return a is b
        if isinstance(a, bool) or isinstance(b, bool):
            return False
        if isinstance(a, int) and isinstance(b, int):
            return a == b
        if isinstance(a, str) and isinstance(b, str):
            return a == b
        if isinstance(a, Symbol) and isinstance(b, Symbol):
            return a.name == b.name
        if isinstance(a, Pair) and isinstance(b, Pair):
            while isinstance(a, Pair) and isinstance(b, Pair):
                if not self._equal(a.car, b.car):
                    return False
                a = a.cdr
                b = b.cdr
            return a is b
        if a is NIL and b is NIL:
            return True
        return a is b

    def _bi_not(self, args):
        return args[0] is False

    def _bi_numberp(self, args):
        x = args[0]
        return isinstance(x, int) and not isinstance(x, bool)

    def _bi_symbolp(self, args):
        return isinstance(args[0], Symbol)

    def _bi_stringp(self, args):
        return isinstance(args[0], str)

    def _bi_procp(self, args):
        return isinstance(args[0], (Closure, Builtin))

    def _bi_str_append(self, args):
        parts = []
        for s in args:
            if not isinstance(s, str):
                self.error("string-append: expected string")
            parts.append(s)
        return ''.join(parts)

    def _bi_display(self, args):
        self.output.append(self._display_repr(args[0]))
        return UNSPECIFIED

    def _bi_newline(self, args):
        self.output.append('\n')
        return UNSPECIFIED

    def _bi_error(self, args):
        msg = args[0]
        if not isinstance(msg, str):
            self.error(self._display_repr(msg))
        parts = [msg]
        for irr in args[1:]:
            parts.append(' ')
            parts.append(self._display_repr(irr, write=True))
        self.error(''.join(parts))

    # ── run ──

    def run(self, source):
        reader = Reader(source)
        forms = reader.read_all()
        for form in forms:
            self.eval_expr(form, self.genv)
        return self.get_output()


# ─── Public API ────────────────────────────────────────────────────────────────

def run(source: str) -> str:
    result = [None]
    error = [None]

    def _target():
        interp = Interpreter()
        try:
            result[0] = interp.run(source)
        except SchemeError as e:
            error[0] = e
        except RecursionError as e:
            error[0] = SchemeError("stack overflow", interp.get_output())
        except Exception as e:
            error[0] = SchemeError(str(e), interp.get_output())

    old_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(1000000)
    try:
        threading.stack_size(256 * 1024 * 1024)
    except Exception:
        pass
    t = threading.Thread(target=_target)
    t.start()
    t.join()
    sys.setrecursionlimit(old_limit)

    if error[0] is not None:
        raise error[0]
    return result[0]
