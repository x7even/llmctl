import sys

sys.setrecursionlimit(200000)


class SchemeError(Exception):
    def __init__(self, message, output=''):
        super().__init__(message)
        self.output = output


# ─── Data Types ───────────────────────────────────────────────────────────────

class Symbol:
    _intern = {}
    __slots__ = ('name',)

    def __new__(cls, name):
        s = cls._intern.get(name)
        if s is not None:
            return s
        obj = object.__new__(cls)
        obj.name = name
        cls._intern[name] = obj
        return obj

    def __repr__(self):
        return f"Sym({self.name})"


class Pair:
    __slots__ = ('car', 'cdr')

    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr


class _EmptyList:
    def __repr__(self):
        return "()"


EMPTY = _EmptyList()


class _Unspecified:
    def __repr__(self):
        return "<unspecified>"


UNSPECIFIED = _Unspecified()


class _Uninit:
    pass


UNINIT = _Uninit()


class Closure:
    __slots__ = ('params', 'body', 'env', 'var_args')

    def __init__(self, params, body, env, var_args):
        self.params = params
        self.body = body
        self.env = env
        self.var_args = var_args


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


# ─── Environment ──────────────────────────────────────────────────────────────

class Env:
    __slots__ = ('vars', 'parent')

    def __init__(self, vars=None, parent=None):
        self.vars = vars if vars is not None else {}
        self.parent = parent


def lookup(sym, env):
    name = sym.name
    e = env
    while e is not None:
        if name in e.vars:
            v = e.vars[name]
            if isinstance(v, _Uninit):
                raise SchemeError(f"uninitialized variable: {name}")
            return v
        e = e.parent
    raise SchemeError(f"unbound variable: {name}")


def set_binding(sym, val, env):
    name = sym.name
    e = env
    while e is not None:
        if name in e.vars:
            e.vars[name] = val
            return
        e = e.parent
    raise SchemeError(f"set!: unbound variable: {name}")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def to_python_list(lst):
    result = []
    while isinstance(lst, Pair):
        result.append(lst.car)
        lst = lst.cdr
    if not isinstance(lst, _EmptyList):
        raise SchemeError("improper list")
    return result


def list_to_scheme(items):
    result = EMPTY
    for item in reversed(items):
        result = Pair(item, result)
    return result


def is_proper_list(v):
    while isinstance(v, Pair):
        v = v.cdr
    return isinstance(v, _EmptyList)


def truthy(v):
    return v is not False


def int_to_str(n, radix=10):
    if n == 0:
        return "0"
    negative = n < 0
    n = abs(n)
    digits = "0123456789abcdef"
    parts = []
    while n > 0:
        parts.append(digits[n % radix])
        n //= radix
    if negative:
        parts.append('-')
    return ''.join(reversed(parts))


# ─── Reader ───────────────────────────────────────────────────────────────────

def _is_integer_token(s):
    if not s:
        return False
    i = 0
    if s[0] in '+-':
        i = 1
    if i >= len(s):
        return False
    for c in s[i:]:
        if not ('0' <= c <= '9'):
            return False
    return True


def tokenize(source):
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
            tokens.append(('(', None))
            i += 1
            continue
        if c == ')':
            tokens.append((')', None))
            i += 1
            continue
        if c == "'":
            tokens.append(("'", None))
            i += 1
            continue
        if c == '"':
            i += 1
            chars = []
            while True:
                if i >= n:
                    raise SchemeError("unterminated string")
                c = source[i]
                if c == '"':
                    i += 1
                    break
                if c == '\\':
                    i += 1
                    if i >= n:
                        raise SchemeError("unterminated string")
                    c = source[i]
                    if c == '"':
                        chars.append('"')
                    elif c == '\\':
                        chars.append('\\')
                    elif c == 'n':
                        chars.append('\n')
                    else:
                        raise SchemeError(f"invalid escape: \\{c}")
                    i += 1
                else:
                    chars.append(c)
                    i += 1
            tokens.append(('string', ''.join(chars)))
            continue
        # Read a token
        start = i
        while i < n and source[i] not in ' \t\n\r()";\'':
            i += 1
        token_str = source[start:i]
        if token_str == '.':
            tokens.append(('dot', None))
        elif token_str == '#t':
            tokens.append(('bool', True))
        elif token_str == '#f':
            tokens.append(('bool', False))
        elif token_str.startswith('#'):
            raise SchemeError(f"invalid token: {token_str}")
        elif _is_integer_token(token_str):
            tokens.append(('int', int(token_str)))
        else:
            tokens.append(('sym', token_str))
    return tokens


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def parse_all(self):
        forms = []
        while self.peek() is not None:
            if self.peek()[0] == ')':
                raise SchemeError("unexpected )")
            forms.append(self.parse_datum())
        return forms

    def parse_datum(self):
        tok = self.peek()
        if tok is None:
            raise SchemeError("unexpected end of input")
        if tok[0] == '(':
            return self.parse_list()
        if tok[0] == "'":
            self.pos += 1
            datum = self.parse_datum()
            return Pair(Symbol('quote'), Pair(datum, EMPTY))
        if tok[0] == ')':
            raise SchemeError("unexpected )")
        if tok[0] == 'dot':
            raise SchemeError("unexpected .")
        self.pos += 1
        if tok[0] == 'int':
            return tok[1]
        if tok[0] == 'bool':
            return tok[1]
        if tok[0] == 'string':
            return tok[1]
        if tok[0] == 'sym':
            return Symbol(tok[1])
        raise SchemeError(f"unexpected token: {tok}")

    def parse_list(self):
        self.pos += 1  # consume (
        items = []
        dot_seen = False
        tail = None
        while True:
            tok = self.peek()
            if tok is None:
                raise SchemeError("unbalanced (")
            if tok[0] == ')':
                self.pos += 1
                break
            if tok[0] == 'dot':
                if dot_seen:
                    raise SchemeError("multiple dots in list")
                if not items:
                    raise SchemeError("dot with no preceding element")
                self.pos += 1
                tail = self.parse_datum()
                dot_seen = True
                tok2 = self.peek()
                if tok2 is None or tok2[0] != ')':
                    raise SchemeError("expected ) after dotted pair")
                self.pos += 1
                break
            if dot_seen:
                raise SchemeError("element after dot")
            items.append(self.parse_datum())
        if dot_seen:
            result = tail
        else:
            result = EMPTY
        for item in reversed(items):
            result = Pair(item, result)
        return result


def read_all(source):
    tokens = tokenize(source)
    parser = Parser(tokens)
    return parser.parse_all()


# ─── Display / Write ──────────────────────────────────────────────────────────

def display_value(val, output, write_mode=False):
    stack = [('val', val)]
    while stack:
        kind, data = stack.pop()
        if kind == 'lit':
            output.append(data)
            continue
        v = data
        if isinstance(v, Pair):
            elements = []
            current = v
            while isinstance(current, Pair):
                elements.append(current.car)
                current = current.cdr
            stack.append(('lit', ')'))
            if not isinstance(current, _EmptyList):
                stack.append(('val', current))
                stack.append(('lit', ' . '))
            for i in range(len(elements) - 1, 0, -1):
                stack.append(('val', elements[i]))
                stack.append(('lit', ' '))
            if elements:
                stack.append(('val', elements[0]))
            stack.append(('lit', '('))
        elif isinstance(v, str):
            if write_mode:
                escaped = v.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
                output.append('"' + escaped + '"')
            else:
                output.append(v)
        elif isinstance(v, bool):
            output.append('#t' if v else '#f')
        elif isinstance(v, int):
            output.append(int_to_str(v, 10))
        elif isinstance(v, Symbol):
            output.append(v.name)
        elif isinstance(v, _EmptyList):
            output.append('()')
        elif isinstance(v, _Unspecified):
            pass
        elif isinstance(v, (Closure, Builtin)):
            output.append('#<procedure>')
        else:
            output.append(str(v))


def write_repr(val):
    parts = []
    display_value(val, parts, write_mode=True)
    return ''.join(parts)


# ─── Equality ─────────────────────────────────────────────────────────────────

def scheme_eq(a, b):
    if a is b:
        return True
    if isinstance(a, bool) or isinstance(b, bool):
        return False
    if isinstance(a, int) and isinstance(b, int):
        return a == b
    if isinstance(a, _EmptyList) and isinstance(b, _EmptyList):
        return True
    return False


def scheme_equal(a, b):
    stack = [(a, b)]
    while stack:
        x, y = stack.pop()
        if x is y:
            continue
        if isinstance(x, bool) or isinstance(y, bool):
            if not (isinstance(x, bool) and isinstance(y, bool)):
                return False
            if x != y:
                return False
            continue
        if isinstance(x, int) and isinstance(y, int):
            if x != y:
                return False
            continue
        if isinstance(x, str) and isinstance(y, str):
            if x != y:
                return False
            continue
        if isinstance(x, Symbol) and isinstance(y, Symbol):
            if x.name != y.name:
                return False
            continue
        if isinstance(x, Pair) and isinstance(y, Pair):
            stack.append((x.cdr, y.cdr))
            stack.append((x.car, y.car))
            continue
        if isinstance(x, _EmptyList) and isinstance(y, _EmptyList):
            continue
        if isinstance(x, _Unspecified) and isinstance(y, _Unspecified):
            continue
        return False
    return True


# ─── Evaluator ────────────────────────────────────────────────────────────────

def parse_formals(formals):
    if isinstance(formals, Symbol):
        return [], formals
    if isinstance(formals, _EmptyList):
        return [], None
    if isinstance(formals, Pair):
        params = []
        current = formals
        while isinstance(current, Pair):
            if not isinstance(current.car, Symbol):
                raise SchemeError("malformed formals: parameter must be a symbol")
            params.append(current.car)
            current = current.cdr
        if isinstance(current, _EmptyList):
            return params, None
        elif isinstance(current, Symbol):
            return params, current
        else:
            raise SchemeError("malformed formals")
    raise SchemeError("malformed formals")


def check_arity(proc, args):
    if isinstance(proc, Builtin):
        if len(args) < proc.min_args:
            raise SchemeError(f"{proc.name}: too few arguments")
        if proc.max_args is not None and len(args) > proc.max_args:
            raise SchemeError(f"{proc.name}: too many arguments")
    elif isinstance(proc, Closure):
        n_fixed = len(proc.params)
        if proc.var_args is None:
            if len(args) != n_fixed:
                raise SchemeError("wrong number of arguments")
        else:
            if len(args) < n_fixed:
                raise SchemeError("too few arguments")


def apply_proc(proc, args):
    if not isinstance(proc, (Closure, Builtin)):
        raise SchemeError("not a procedure")
    check_arity(proc, args)
    if isinstance(proc, Builtin):
        return proc.func(args)
    # Closure
    param_vars = {}
    for i, name in enumerate(proc.params):
        param_vars[name.name] = args[i]
    if proc.var_args is not None:
        param_vars[proc.var_args.name] = list_to_scheme(args[len(proc.params):])
    new_env = Env(param_vars, proc.env)
    return eval_body(proc.body, new_env)


def force(result):
    while isinstance(result, TailCall):
        result = apply_proc(result.proc, result.args)
    return result


def eval_non_tail(expr, env):
    return force(eval_tail(expr, env))


def is_define_form(form):
    return (isinstance(form, Pair) and
            isinstance(form.car, Symbol) and
            form.car.name == 'define')


def get_define_name(form):
    first = form.cdr.car
    if isinstance(first, Symbol):
        return first.name
    if isinstance(first, Pair):
        if isinstance(first.car, Symbol):
            return first.car.name
    raise SchemeError("malformed define")


def execute_define(form, env):
    rest = form.cdr
    first = rest.car
    if isinstance(first, Symbol):
        if rest.cdr is EMPTY:
            raise SchemeError("malformed define: no expression")
        val = eval_non_tail(rest.cdr.car, env)
        env.vars[first.name] = val
    elif isinstance(first, Pair):
        name = first.car
        if not isinstance(name, Symbol):
            raise SchemeError("malformed define")
        formals = first.cdr
        body = to_python_list(rest.cdr)
        if not body:
            raise SchemeError("define: empty body")
        params, var_args = parse_formals(formals)
        closure = Closure(params, body, env, var_args)
        env.vars[name.name] = closure
    else:
        raise SchemeError("malformed define")


def eval_body(body, env):
    # Scan for internal defines
    defined_names = []
    for form in body:
        if is_define_form(form):
            defined_names.append(get_define_name(form))
    # Pre-bind
    for name in defined_names:
        env.vars[name] = UNINIT
    # Execute in order
    for i, form in enumerate(body):
        is_last = (i == len(body) - 1)
        if is_define_form(form):
            execute_define(form, env)
            if is_last:
                return UNSPECIFIED
        else:
            if is_last:
                return eval_tail(form, env)
            else:
                eval_non_tail(form, env)
    return UNSPECIFIED


def eval_tail(expr, env):
    # Self-evaluating
    if isinstance(expr, int) or isinstance(expr, bool) or isinstance(expr, str):
        return expr
    if isinstance(expr, _EmptyList):
        raise SchemeError("cannot evaluate ()")
    if isinstance(expr, Symbol):
        return lookup(expr, env)
    if isinstance(expr, _Unspecified):
        return UNSPECIFIED
    if isinstance(expr, (Closure, Builtin)):
        return expr
    if not isinstance(expr, Pair):
        return expr

    # It's a pair - check for special forms
    head = expr.car
    if isinstance(head, Symbol):
        hname = head.name

        if hname == 'quote':
            parts = to_python_list(expr.cdr)
            if len(parts) != 1:
                raise SchemeError("malformed quote")
            return parts[0]

        if hname == 'if':
            parts = to_python_list(expr.cdr)
            if len(parts) < 2 or len(parts) > 3:
                raise SchemeError("malformed if")
            test_val = eval_non_tail(parts[0], env)
            if truthy(test_val):
                return eval_tail(parts[1], env)
            elif len(parts) == 3:
                return eval_tail(parts[2], env)
            else:
                return UNSPECIFIED

        if hname == 'lambda':
            rest = expr.cdr
            if rest is EMPTY:
                raise SchemeError("malformed lambda")
            formals = rest.car
            body = to_python_list(rest.cdr)
            if not body:
                raise SchemeError("lambda: empty body")
            params, var_args = parse_formals(formals)
            return Closure(params, body, env, var_args)

        if hname == 'define':
            rest = expr.cdr
            if rest is EMPTY:
                raise SchemeError("malformed define")
            first = rest.car
            if isinstance(first, Symbol):
                if rest.cdr is EMPTY:
                    raise SchemeError("malformed define: no expression")
                val = eval_non_tail(rest.cdr.car, env)
                env.vars[first.name] = val
                return UNSPECIFIED
            elif isinstance(first, Pair):
                name = first.car
                if not isinstance(name, Symbol):
                    raise SchemeError("malformed define")
                formals = first.cdr
                body = to_python_list(rest.cdr)
                if not body:
                    raise SchemeError("define: empty body")
                params, var_args = parse_formals(formals)
                closure = Closure(params, body, env, var_args)
                env.vars[name.name] = closure
                return UNSPECIFIED
            else:
                raise SchemeError("malformed define")

        if hname == 'set!':
            parts = to_python_list(expr.cdr)
            if len(parts) != 2:
                raise SchemeError("malformed set!")
            name_sym, val_expr = parts
            if not isinstance(name_sym, Symbol):
                raise SchemeError("set!: not a symbol")
            val = eval_non_tail(val_expr, env)
            set_binding(name_sym, val, env)
            return UNSPECIFIED

        if hname == 'begin':
            exprs = to_python_list(expr.cdr)
            if not exprs:
                raise SchemeError("malformed begin")
            for e in exprs[:-1]:
                eval_non_tail(e, env)
            return eval_tail(exprs[-1], env)

        if hname == 'cond':
            clauses = to_python_list(expr.cdr)
            for i, clause in enumerate(clauses):
                if not isinstance(clause, Pair):
                    raise SchemeError("malformed cond clause")
                test = clause.car
                exprs = to_python_list(clause.cdr)
                if isinstance(test, Symbol) and test.name == 'else':
                    if i != len(clauses) - 1:
                        raise SchemeError("else not last in cond")
                    if not exprs:
                        return UNSPECIFIED
                    for e in exprs[:-1]:
                        eval_non_tail(e, env)
                    return eval_tail(exprs[-1], env)
                else:
                    test_val = eval_non_tail(test, env)
                    if truthy(test_val):
                        if not exprs:
                            return test_val
                        for e in exprs[:-1]:
                            eval_non_tail(e, env)
                        return eval_tail(exprs[-1], env)
            return UNSPECIFIED

        if hname == 'and':
            exprs = to_python_list(expr.cdr)
            if not exprs:
                return True
            for e in exprs[:-1]:
                val = eval_non_tail(e, env)
                if val is False:
                    return False
            return eval_tail(exprs[-1], env)

        if hname == 'or':
            exprs = to_python_list(expr.cdr)
            if not exprs:
                return False
            for e in exprs[:-1]:
                val = eval_non_tail(e, env)
                if val is not False:
                    return val
            return eval_tail(exprs[-1], env)

        if hname == 'let':
            rest = expr.cdr
            if rest is EMPTY:
                raise SchemeError("malformed let")
            first = rest.car
            if isinstance(first, Symbol):
                # Named let
                name_sym = first
                bindings_form = rest.cdr
                if bindings_form is EMPTY:
                    raise SchemeError("malformed named let")
                bindings_list = bindings_form.car
                body_forms = to_python_list(bindings_form.cdr)
                if not body_forms:
                    raise SchemeError("named let: empty body")
                names = []
                values = []
                for b in to_python_list(bindings_list):
                    if not isinstance(b, Pair) or not isinstance(b.cdr, Pair) or not isinstance(b.cdr.cdr, _EmptyList):
                        raise SchemeError("malformed let binding")
                    if not isinstance(b.car, Symbol):
                        raise SchemeError("malformed let binding")
                    names.append(b.car)
                    values.append(eval_non_tail(b.cdr.car, env))
                letrec_vars = {name_sym.name: UNINIT}
                letrec_env = Env(letrec_vars, env)
                closure = Closure(names, body_forms, letrec_env, None)
                letrec_vars[name_sym.name] = closure
                return apply_proc(closure, values)
            elif isinstance(first, (Pair, _EmptyList)):
                # Anonymous let
                bindings_list = first
                body_forms = to_python_list(rest.cdr)
                if not body_forms:
                    raise SchemeError("let: empty body")
                names = []
                values = []
                for b in to_python_list(bindings_list):
                    if not isinstance(b, Pair) or not isinstance(b.cdr, Pair) or not isinstance(b.cdr.cdr, _EmptyList):
                        raise SchemeError("malformed let binding")
                    if not isinstance(b.car, Symbol):
                        raise SchemeError("malformed let binding")
                    names.append(b.car)
                    values.append(eval_non_tail(b.cdr.car, env))
                new_vars = {}
                for name, val in zip(names, values):
                    new_vars[name.name] = val
                new_env = Env(new_vars, env)
                return eval_body(body_forms, new_env)
            else:
                raise SchemeError("malformed let")

        if hname == 'let*':
            rest = expr.cdr
            if rest is EMPTY:
                raise SchemeError("malformed let*")
            bindings_list = rest.car
            if not isinstance(bindings_list, (Pair, _EmptyList)):
                raise SchemeError("malformed let*")
            body_forms = to_python_list(rest.cdr)
            if not body_forms:
                raise SchemeError("let*: empty body")
            new_vars = {}
            cur_env = Env(new_vars, env)
            for b in to_python_list(bindings_list):
                if not isinstance(b, Pair) or not isinstance(b.cdr, Pair) or not isinstance(b.cdr.cdr, _EmptyList):
                    raise SchemeError("malformed let* binding")
                if not isinstance(b.car, Symbol):
                    raise SchemeError("malformed let* binding")
                val = eval_non_tail(b.cdr.car, cur_env)
                new_vars[b.car.name] = val
            return eval_body(body_forms, cur_env)

        if hname == 'letrec':
            rest = expr.cdr
            if rest is EMPTY:
                raise SchemeError("malformed letrec")
            bindings_list = rest.car
            if not isinstance(bindings_list, (Pair, _EmptyList)):
                raise SchemeError("malformed letrec")
            body_forms = to_python_list(rest.cdr)
            if not body_forms:
                raise SchemeError("letrec: empty body")
            new_vars = {}
            for b in to_python_list(bindings_list):
                if not isinstance(b, Pair) or not isinstance(b.cdr, Pair) or not isinstance(b.cdr.cdr, _EmptyList):
                    raise SchemeError("malformed letrec binding")
                if not isinstance(b.car, Symbol):
                    raise SchemeError("malformed letrec binding")
                new_vars[b.car.name] = UNINIT
            new_env = Env(new_vars, env)
            for b in to_python_list(bindings_list):
                val = eval_non_tail(b.cdr.car, new_env)
                new_vars[b.car.name] = val
            return eval_body(body_forms, new_env)

        if hname == 'apply':
            parts = to_python_list(expr.cdr)
            if len(parts) < 2:
                raise SchemeError("apply: too few arguments")
            f = eval_non_tail(parts[0], env)
            final_args = []
            for p in parts[1:-1]:
                final_args.append(eval_non_tail(p, env))
            lst = eval_non_tail(parts[-1], env)
            if not is_proper_list(lst):
                raise SchemeError("apply: last argument is not a proper list")
            final_args.extend(to_python_list(lst))
            if not isinstance(f, (Closure, Builtin)):
                raise SchemeError("apply: not a procedure")
            check_arity(f, final_args)
            return apply_proc(f, final_args)

    # Procedure application
    proc = eval_non_tail(expr.car, env)
    args = [eval_non_tail(arg, env) for arg in to_python_list(expr.cdr)]
    if not isinstance(proc, (Closure, Builtin)):
        raise SchemeError("not a procedure")
    check_arity(proc, args)
    return apply_proc(proc, args)


# ─── Builtins ─────────────────────────────────────────────────────────────────

def make_global_env(output):
    env = Env()

    def add_builtin(name, func, min_args=0, max_args=None):
        env.vars[name] = Builtin(name, func, min_args, max_args)

    # ── Arithmetic ──
    def _check_int(v, name):
        if isinstance(v, bool) or not isinstance(v, int):
            raise SchemeError(f"{name}: not an integer")

    def b_plus(args):
        s = 0
        for a in args:
            _check_int(a, '+')
            s += a
        return s

    def b_times(args):
        s = 1
        for a in args:
            _check_int(a, '*')
            s *= a
        return s

    def b_minus(args):
        if not args:
            raise SchemeError("-: requires at least 1 argument")
        _check_int(args[0], '-')
        if len(args) == 1:
            return -args[0]
        s = args[0]
        for a in args[1:]:
            _check_int(a, '-')
            s -= a
        return s

    def b_quotient(args):
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
        a, b = args
        _check_int(a, 'remainder')
        _check_int(b, 'remainder')
        if b == 0:
            raise SchemeError("remainder: division by zero")
        return a - b * b_quotient([a, b])

    def b_modulo(args):
        a, b = args
        _check_int(a, 'modulo')
        _check_int(b, 'modulo')
        if b == 0:
            raise SchemeError("modulo: division by zero")
        r = a - b * b_quotient([a, b])
        if r != 0 and (r < 0) != (b < 0):
            r += b
        return r

    def b_eq(args):
        for a in args:
            _check_int(a, '=')
        for i in range(len(args) - 1):
            if args[i] != args[i + 1]:
                return False
        return True

    def b_lt(args):
        for a in args:
            _check_int(a, '<')
        for i in range(len(args) - 1):
            if not (args[i] < args[i + 1]):
                return False
        return True

    def b_gt(args):
        for a in args:
            _check_int(a, '>')
        for i in range(len(args) - 1):
            if not (args[i] > args[i + 1]):
                return False
        return True

    def b_le(args):
        for a in args:
            _check_int(a, '<=')
        for i in range(len(args) - 1):
            if not (args[i] <= args[i + 1]):
                return False
        return True

    def b_ge(args):
        for a in args:
            _check_int(a, '>=')
        for i in range(len(args) - 1):
            if not (args[i] >= args[i + 1]):
                return False
        return True

    def b_number_to_string(args):
        n = args[0]
        _check_int(n, 'number->string')
        radix = 10
        if len(args) == 2:
            radix = args[1]
            _check_int(radix, 'number->string')
            if radix not in (2, 8, 10, 16):
                raise SchemeError("number->string: invalid radix")
        return int_to_str(n, radix)

    add_builtin('+', b_plus, 0)
    add_builtin('*', b_times, 0)
    add_builtin('-', b_minus, 1)
    add_builtin('quotient', b_quotient, 2, 2)
    add_builtin('remainder', b_remainder, 2, 2)
    add_builtin('modulo', b_modulo, 2, 2)
    add_builtin('=', b_eq, 1)
    add_builtin('<', b_lt, 1)
    add_builtin('>', b_gt, 1)
    add_builtin('<=', b_le, 1)
    add_builtin('>=', b_ge, 1)
    add_builtin('number->string', b_number_to_string, 1, 2)

    # ── Lists and pairs ──
    def b_cons(args):
        return Pair(args[0], args[1])

    def b_car(args):
        p = args[0]
        if not isinstance(p, Pair):
            raise SchemeError("car: not a pair")
        return p.car

    def b_cdr(args):
        p = args[0]
        if not isinstance(p, Pair):
            raise SchemeError("cdr: not a pair")
        return p.cdr

    def b_list(args):
        return list_to_scheme(args)

    def b_null_q(args):
        return isinstance(args[0], _EmptyList)

    def b_pair_q(args):
        return isinstance(args[0], Pair)

    def b_list_q(args):
        return is_proper_list(args[0])

    def b_length(args):
        lst = args[0]
        count = 0
        while isinstance(lst, Pair):
            count += 1
            lst = lst.cdr
        if not isinstance(lst, _EmptyList):
            raise SchemeError("length: not a proper list")
        return count

    def b_append(args):
        if not args:
            return EMPTY
        if len(args) == 1:
            return args[0]
        for a in args[:-1]:
            if not is_proper_list(a):
                raise SchemeError("append: improper list argument")
        result = args[-1]
        for lst in reversed(args[:-1]):
            elements = to_python_list(lst)
            for elem in reversed(elements):
                result = Pair(elem, result)
        return result

    def b_reverse(args):
        lst = args[0]
        if not is_proper_list(lst):
            raise SchemeError("reverse: not a proper list")
        elements = to_python_list(lst)
        elements.reverse()
        return list_to_scheme(elements)

    def b_apply(args):
        if len(args) < 2:
            raise SchemeError("apply: too few arguments")
        f = args[0]
        lst = args[-1]
        if not is_proper_list(lst):
            raise SchemeError("apply: last argument is not a proper list")
        final_args = list(args[1:-1]) + to_python_list(lst)
        if not isinstance(f, (Closure, Builtin)):
            raise SchemeError("apply: not a procedure")
        check_arity(f, final_args)
        return force(apply_proc(f, final_args))

    add_builtin('cons', b_cons, 2, 2)
    add_builtin('car', b_car, 1, 1)
    add_builtin('cdr', b_cdr, 1, 1)
    add_builtin('list', b_list, 0)
    add_builtin('null?', b_null_q, 1, 1)
    add_builtin('pair?', b_pair_q, 1, 1)
    add_builtin('list?', b_list_q, 1, 1)
    add_builtin('length', b_length, 1, 1)
    add_builtin('append', b_append, 0)
    add_builtin('reverse', b_reverse, 1, 1)
    add_builtin('apply', b_apply, 2)

    # ── Equality and predicates ──
    def b_eq_q(args):
        return scheme_eq(args[0], args[1])

    def b_equal_q(args):
        return scheme_equal(args[0], args[1])

    def b_not(args):
        return args[0] is False

    def b_number_q(args):
        v = args[0]
        return isinstance(v, int) and not isinstance(v, bool)

    def b_symbol_q(args):
        return isinstance(args[0], Symbol)

    def b_string_q(args):
        return isinstance(args[0], str)

    def b_procedure_q(args):
        return isinstance(args[0], (Closure, Builtin))

    def b_string_append(args):
        parts = []
        for a in args:
            if not isinstance(a, str):
                raise SchemeError("string-append: not a string")
            parts.append(a)
        return ''.join(parts)

    add_builtin('eq?', b_eq_q, 2, 2)
    add_builtin('equal?', b_equal_q, 2, 2)
    add_builtin('not', b_not, 1, 1)
    add_builtin('number?', b_number_q, 1, 1)
    add_builtin('symbol?', b_symbol_q, 1, 1)
    add_builtin('string?', b_string_q, 1, 1)
    add_builtin('procedure?', b_procedure_q, 1, 1)
    add_builtin('string-append', b_string_append, 0)

    # ── Output and errors ──
    def b_display(args):
        display_value(args[0], output, write_mode=False)
        return UNSPECIFIED

    def b_newline(args):
        output.append('\n')
        return UNSPECIFIED

    def b_error(args):
        if not args:
            raise SchemeError("error: no arguments")
        msg = args[0]
        if not isinstance(msg, str):
            raise SchemeError("error: first argument must be a string")
        parts = [msg]
        for irritant in args[1:]:
            parts.append(' ')
            parts.append(write_repr(irritant))
        raise SchemeError(''.join(parts))

    add_builtin('display', b_display, 1, 1)
    add_builtin('newline', b_newline, 0, 0)
    add_builtin('error', b_error, 1)

    return env


# ─── Main Entry Point ─────────────────────────────────────────────────────────

def run(source):
    output = []
    try:
        forms = read_all(source)
    except SchemeError as e:
        raise SchemeError(str(e), '')
    except Exception as e:
        raise SchemeError(str(e), '')

    try:
        env = make_global_env(output)
        for form in forms:
            force(eval_tail(form, env))
    except SchemeError as e:
        e.output = ''.join(output)
        raise
    except RecursionError:
        raise SchemeError("stack overflow", ''.join(output))
    except Exception as e:
        raise SchemeError(str(e), ''.join(output))

    return ''.join(output)
