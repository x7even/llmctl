import sys

try:
    sys.set_int_max_str_digits(0)
except (AttributeError, ValueError):
    pass

sys.setrecursionlimit(100000)


class SchemeError(Exception):
    def __init__(self, msg='', output=''):
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
        return '#<unspecified>'

UNSPEC = _Unspecified()


class _Unassigned:
    pass

UNASSIGNED = _Unassigned()


class Closure:
    __slots__ = ('params', 'rest', 'body', 'env')
    def __init__(self, params, rest, body, env):
        self.params = params
        self.rest = rest
        self.body = body
        self.env = env


class Builtin:
    __slots__ = ('func', 'name', 'min_args', 'max_args')
    def __init__(self, func, name, min_args, max_args=None):
        self.func = func
        self.name = name
        self.min_args = min_args
        self.max_args = max_args


class OutputBuffer:
    def __init__(self):
        self.parts = []
    def write(self, s):
        self.parts.append(s)
    def get(self):
        return ''.join(self.parts)


# ─── Helpers ───────────────────────────────────────────────────────────────────

def is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)


def is_proper_list(x):
    while isinstance(x, Pair):
        x = x.cdr
    return x is NIL


def to_scheme_list(lst):
    result = []
    while isinstance(lst, Pair):
        result.append(lst.car)
        lst = lst.cdr
    if lst is not NIL:
        raise SchemeError("improper list")
    return result


def scheme_to_python_list(x):
    result = []
    while isinstance(x, Pair):
        result.append(x.car)
        x = x.cdr
    if x is not NIL:
        raise SchemeError("not a proper list")
    return result


def build_proper_list(elements):
    result = NIL
    for e in reversed(elements):
        result = Pair(e, result)
    return result


def int_to_base(n, radix):
    if n == 0:
        return "0"
    negative = n < 0
    n = abs(n)
    digits = []
    while n > 0:
        digits.append("0123456789abcdef"[n % radix])
        n //= radix
    if negative:
        digits.append('-')
    return ''.join(reversed(digits))


def escape_string(s):
    parts = []
    for c in s:
        if c == '"':
            parts.append('\\"')
        elif c == '\\':
            parts.append('\\\\')
        elif c == '\n':
            parts.append('\\n')
        else:
            parts.append(c)
    return ''.join(parts)


# ─── Reader ────────────────────────────────────────────────────────────────────

def is_integer_token(s):
    if not s:
        return False
    i = 0
    if s[0] in '+-':
        i = 1
    if i >= len(s):
        return False
    for c in s[i:]:
        if c < '0' or c > '9':
            return False
    return True


def atom_to_value(tok):
    if tok == '#t':
        return True
    if tok == '#f':
        return False
    if tok.startswith('#'):
        raise SchemeError("bad # token: " + tok)
    if is_integer_token(tok):
        return int(tok)
    return Symbol(tok)


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
            parts = []
            while i < n and source[i] != '"':
                if source[i] == '\\':
                    i += 1
                    if i >= n:
                        raise SchemeError("unterminated string escape")
                    if source[i] == '"':
                        parts.append('"')
                    elif source[i] == '\\':
                        parts.append('\\')
                    elif source[i] == 'n':
                        parts.append('\n')
                    else:
                        raise SchemeError("bad escape")
                    i += 1
                else:
                    parts.append(source[i])
                    i += 1
            if i >= n:
                raise SchemeError("unterminated string")
            i += 1
            tokens.append(('str', ''.join(parts)))
            continue
        start = i
        while i < n and source[i] not in ' \t\n\r()";\'':
            i += 1
        tok = source[start:i]
        if tok:
            tokens.append(('atom', tok))
    return tokens


def parse_all(tokens):
    pos = [0]

    def peek():
        if pos[0] < len(tokens):
            return tokens[pos[0]]
        return None

    def advance():
        t = tokens[pos[0]]
        pos[0] += 1
        return t

    def read_datum():
        tok = peek()
        if tok is None:
            raise SchemeError("unexpected end of input")
        kind, val = tok
        if kind == '(':
            advance()
            return read_list_body()
        elif kind == ')':
            raise SchemeError("unexpected )")
        elif kind == "'":
            advance()
            datum = read_datum()
            return Pair(Symbol('quote'), Pair(datum, NIL))
        elif kind == 'str':
            advance()
            return val
        elif kind == 'atom':
            advance()
            return atom_to_value(val)
        else:
            raise SchemeError("unexpected token")

    def read_list_body():
        elements = []
        while True:
            tok = peek()
            if tok is None:
                raise SchemeError("unexpected end of input in list")
            if tok[0] == ')':
                advance()
                return build_proper_list(elements)
            if tok[0] == 'atom' and tok[1] == '.':
                if not elements:
                    raise SchemeError("dot at beginning of list")
                advance()
                tail = read_datum()
                tok2 = peek()
                if tok2 is None or tok2[0] != ')':
                    raise SchemeError("expected ) after dotted pair")
                advance()
                result = tail
                for e in reversed(elements):
                    result = Pair(e, result)
                return result
            elements.append(read_datum())

    forms = []
    while pos[0] < len(tokens):
        tok = peek()
        if tok[0] == ')':
            raise SchemeError("unexpected )")
        forms.append(read_datum())
    return forms


def read_all(source):
    tokens = tokenize(source)
    return parse_all(tokens)


# ─── Display ───────────────────────────────────────────────────────────────────

def display_value(x, out, write_mode=False):
    if isinstance(x, _Unspecified):
        return
    if isinstance(x, bool):
        out.write('#t' if x else '#f')
    elif is_int(x):
        out.write(int_to_base(x, 10))
    elif isinstance(x, str):
        if write_mode:
            out.write('"' + escape_string(x) + '"')
        else:
            out.write(x)
    elif isinstance(x, Symbol):
        out.write(x.name)
    elif isinstance(x, _Nil):
        out.write('()')
    elif isinstance(x, Pair):
        out.write('(')
        first = True
        current = x
        while isinstance(current, Pair):
            if not first:
                out.write(' ')
            display_value(current.car, out, write_mode)
            first = False
            current = current.cdr
        if not isinstance(current, _Nil):
            out.write(' . ')
            display_value(current, out, write_mode)
        out.write(')')
    elif isinstance(x, (Closure, Builtin)):
        out.write('#<procedure>')
    else:
        out.write(str(x))


def write_repr(x):
    buf = OutputBuffer()
    display_value(x, buf, True)
    return buf.get()


# ─── Environment ───────────────────────────────────────────────────────────────

class Frame:
    __slots__ = ('vars', 'parent')
    def __init__(self, parent=None):
        self.vars = {}
        self.parent = parent


def lookup(sym, env):
    frame = env
    while frame is not None:
        if sym.name in frame.vars:
            val = frame.vars[sym.name]
            if isinstance(val, _Unassigned):
                raise SchemeError("unassigned variable: " + sym.name)
            return val
        frame = frame.parent
    raise SchemeError("unbound variable: " + sym.name)


def set_var(sym, val, env):
    frame = env
    while frame is not None:
        if sym.name in frame.vars:
            frame.vars[sym.name] = val
            return
        frame = frame.parent
    raise SchemeError("set!: unbound variable: " + sym.name)


def parse_formals(formals):
    if isinstance(formals, Symbol):
        return [], formals
    if isinstance(formals, _Nil):
        return [], None
    params = []
    cur = formals
    while isinstance(cur, Pair):
        if not isinstance(cur.car, Symbol):
            raise SchemeError("bad formals")
        params.append(cur.car)
        cur = cur.cdr
    if isinstance(cur, _Nil):
        return params, None
    elif isinstance(cur, Symbol):
        return params, cur
    else:
        raise SchemeError("bad formals")


def make_call_env(closure, args):
    env = Frame(closure.env)
    if closure.rest is None:
        if len(args) != len(closure.params):
            raise SchemeError("wrong number of arguments to procedure")
        for p, v in zip(closure.params, args):
            env.vars[p.name] = v
    else:
        if len(args) < len(closure.params):
            raise SchemeError("too few arguments to procedure")
        for p, v in zip(closure.params, args):
            env.vars[p.name] = v
        rest_list = build_proper_list(args[len(closure.params):])
        env.vars[closure.rest.name] = rest_list
    return env


def is_define(form):
    return (isinstance(form, Pair) and isinstance(form.car, Symbol)
            and form.car.name == 'define')


def get_define_name(form):
    target = form.cdr.car
    if isinstance(target, Symbol):
        return target
    elif isinstance(target, Pair):
        return target.car
    raise SchemeError("malformed define")


def setup_body_env(body, env):
    def_names = []
    for form in body:
        if is_define(form):
            try:
                def_names.append(get_define_name(form))
            except SchemeError:
                pass
    if def_names:
        new_frame = Frame(env)
        for name in def_names:
            new_frame.vars[name.name] = UNASSIGNED
        return new_frame
    return env


def execute_define(form, env):
    if not isinstance(form.cdr, Pair):
        raise SchemeError("malformed define")
    target = form.cdr.car
    if isinstance(target, Symbol):
        if not isinstance(form.cdr.cdr, Pair):
            raise SchemeError("malformed define")
        if form.cdr.cdr.cdr is not NIL:
            raise SchemeError("malformed define")
        val = evaluate(form.cdr.cdr.car, env)
        env.vars[target.name] = val
    elif isinstance(target, Pair):
        func_name = target.car
        if not isinstance(func_name, Symbol):
            raise SchemeError("malformed define")
        formals = target.cdr
        body = to_scheme_list(form.cdr.cdr)
        if not body:
            raise SchemeError("malformed define: empty body")
        params, rest = parse_formals(formals)
        closure = Closure(params, rest, body, env)
        env.vars[func_name.name] = closure
    else:
        raise SchemeError("malformed define")


# ─── Evaluator ─────────────────────────────────────────────────────────────────

def evaluate(expr, env):
    while True:
        # Self-evaluating types
        if isinstance(expr, bool):
            return expr
        if is_int(expr):
            return expr
        if isinstance(expr, str):
            return expr
        if isinstance(expr, _Unspecified):
            return expr
        if isinstance(expr, _Nil):
            raise SchemeError("cannot evaluate ()")

        # Symbol lookup
        if isinstance(expr, Symbol):
            return lookup(expr, env)

        # Must be a pair (a form)
        if not isinstance(expr, Pair):
            raise SchemeError("cannot evaluate: " + repr(expr))

        head = expr.car

        # Special forms (head must be a symbol)
        if isinstance(head, Symbol):
            name = head.name

            if name == 'quote':
                if not isinstance(expr.cdr, Pair):
                    raise SchemeError("malformed quote")
                if expr.cdr.cdr is not NIL:
                    raise SchemeError("malformed quote")
                return expr.cdr.car

            elif name == 'if':
                if not isinstance(expr.cdr, Pair):
                    raise SchemeError("malformed if")
                args = expr.cdr
                test_expr = args.car
                args = args.cdr
                if not isinstance(args, Pair):
                    raise SchemeError("malformed if")
                then_expr = args.car
                args = args.cdr
                if isinstance(args, _Nil):
                    else_expr = None
                elif isinstance(args, Pair):
                    else_expr = args.car
                    if args.cdr is not NIL:
                        raise SchemeError("malformed if")
                else:
                    raise SchemeError("malformed if")
                test_val = evaluate(test_expr, env)
                if test_val is not False:
                    expr = then_expr
                    continue
                else:
                    if else_expr is not None:
                        expr = else_expr
                        continue
                    return UNSPEC

            elif name == 'define':
                if not isinstance(expr.cdr, Pair):
                    raise SchemeError("malformed define")
                target = expr.cdr.car
                if isinstance(target, Symbol):
                    if not isinstance(expr.cdr.cdr, Pair):
                        raise SchemeError("malformed define")
                    if expr.cdr.cdr.cdr is not NIL:
                        raise SchemeError("malformed define")
                    val = evaluate(expr.cdr.cdr.car, env)
                    env.vars[target.name] = val
                elif isinstance(target, Pair):
                    func_name = target.car
                    if not isinstance(func_name, Symbol):
                        raise SchemeError("malformed define")
                    formals = target.cdr
                    body = to_scheme_list(expr.cdr.cdr)
                    if not body:
                        raise SchemeError("malformed define: empty body")
                    params, rest = parse_formals(formals)
                    closure = Closure(params, rest, body, env)
                    env.vars[func_name.name] = closure
                else:
                    raise SchemeError("malformed define")
                return UNSPEC

            elif name == 'set!':
                if not isinstance(expr.cdr, Pair):
                    raise SchemeError("malformed set!")
                var = expr.cdr.car
                if not isinstance(var, Symbol):
                    raise SchemeError("set!: not a symbol")
                if not isinstance(expr.cdr.cdr, Pair):
                    raise SchemeError("malformed set!")
                if expr.cdr.cdr.cdr is not NIL:
                    raise SchemeError("malformed set!")
                val = evaluate(expr.cdr.cdr.car, env)
                set_var(var, val, env)
                return UNSPEC

            elif name == 'begin':
                forms = to_scheme_list(expr.cdr)
                if not forms:
                    raise SchemeError("empty begin")
                for f in forms[:-1]:
                    evaluate(f, env)
                expr = forms[-1]
                continue

            elif name == 'cond':
                clauses = to_scheme_list(expr.cdr)
                matched = False
                for ci, clause in enumerate(clauses):
                    if not isinstance(clause, Pair):
                        raise SchemeError("malformed cond clause")
                    test = clause.car
                    body = to_scheme_list(clause.cdr)
                    if isinstance(test, Symbol) and test.name == 'else':
                        if ci != len(clauses) - 1:
                            raise SchemeError("else not last in cond")
                        if not body:
                            return UNSPEC
                        for f in body[:-1]:
                            evaluate(f, env)
                        expr = body[-1]
                        matched = True
                        break
                    else:
                        test_val = evaluate(test, env)
                        if test_val is not False:
                            if not body:
                                return test_val
                            for f in body[:-1]:
                                evaluate(f, env)
                            expr = body[-1]
                            matched = True
                            break
                if not matched:
                    return UNSPEC
                continue

            elif name == 'and':
                exprs = to_scheme_list(expr.cdr)
                if not exprs:
                    return True
                for e in exprs[:-1]:
                    val = evaluate(e, env)
                    if val is False:
                        return False
                expr = exprs[-1]
                continue

            elif name == 'or':
                exprs = to_scheme_list(expr.cdr)
                if not exprs:
                    return False
                for e in exprs[:-1]:
                    val = evaluate(e, env)
                    if val is not False:
                        return val
                expr = exprs[-1]
                continue

            elif name == 'lambda':
                if not isinstance(expr.cdr, Pair):
                    raise SchemeError("malformed lambda")
                formals = expr.cdr.car
                body = to_scheme_list(expr.cdr.cdr)
                if not body:
                    raise SchemeError("empty lambda body")
                params, rest = parse_formals(formals)
                return Closure(params, rest, body, env)

            elif name == 'let':
                if not isinstance(expr.cdr, Pair):
                    raise SchemeError("malformed let")
                second = expr.cdr.car
                if isinstance(second, Symbol):
                    # Named let
                    let_name = second
                    if not isinstance(expr.cdr.cdr, Pair):
                        raise SchemeError("malformed named let")
                    bindings_expr = expr.cdr.cdr.car
                    bindings = to_scheme_list(bindings_expr)
                    body = to_scheme_list(expr.cdr.cdr.cdr)
                    if not body:
                        raise SchemeError("malformed named let: empty body")
                    inits = []
                    names = []
                    for b in bindings:
                        if not isinstance(b, Pair):
                            raise SchemeError("malformed let binding")
                        if not isinstance(b.cdr, Pair):
                            raise SchemeError("malformed let binding")
                        names.append(b.car)
                        inits.append(evaluate(b.cdr.car, env))
                    closure_env = Frame(env)
                    closure = Closure(names, None, body, closure_env)
                    closure_env.vars[let_name.name] = closure
                    call_env = Frame(closure_env)
                    for p, v in zip(names, inits):
                        call_env.vars[p.name] = v
                    env = setup_body_env(body, call_env)
                    for f in body[:-1]:
                        if is_define(f):
                            execute_define(f, env)
                        else:
                            evaluate(f, env)
                    expr = body[-1]
                    if is_define(expr):
                        execute_define(expr, env)
                        return UNSPEC
                    continue
                else:
                    # Regular let
                    bindings = to_scheme_list(second)
                    body = to_scheme_list(expr.cdr.cdr)
                    if not body:
                        raise SchemeError("malformed let: empty body")
                    inits = []
                    names = []
                    for b in bindings:
                        if not isinstance(b, Pair):
                            raise SchemeError("malformed let binding")
                        if not isinstance(b.cdr, Pair):
                            raise SchemeError("malformed let binding")
                        names.append(b.car)
                        inits.append(evaluate(b.cdr.car, env))
                    new_env = Frame(env)
                    for n, v in zip(names, inits):
                        new_env.vars[n.name] = v
                    env = setup_body_env(body, new_env)
                    for f in body[:-1]:
                        if is_define(f):
                            execute_define(f, env)
                        else:
                            evaluate(f, env)
                    expr = body[-1]
                    if is_define(expr):
                        execute_define(expr, env)
                        return UNSPEC
                    continue

            elif name == 'let*':
                if not isinstance(expr.cdr, Pair):
                    raise SchemeError("malformed let*")
                bindings = to_scheme_list(expr.cdr.car)
                body = to_scheme_list(expr.cdr.cdr)
                if not body:
                    raise SchemeError("malformed let*: empty body")
                new_env = Frame(env)
                for b in bindings:
                    if not isinstance(b, Pair):
                        raise SchemeError("malformed let* binding")
                    if not isinstance(b.cdr, Pair):
                        raise SchemeError("malformed let* binding")
                    val = evaluate(b.cdr.car, new_env)
                    new_env.vars[b.car.name] = val
                env = setup_body_env(body, new_env)
                for f in body[:-1]:
                    if is_define(f):
                        execute_define(f, env)
                    else:
                        evaluate(f, env)
                expr = body[-1]
                if is_define(expr):
                    execute_define(expr, env)
                    return UNSPEC
                continue

            elif name == 'letrec':
                if not isinstance(expr.cdr, Pair):
                    raise SchemeError("malformed letrec")
                bindings = to_scheme_list(expr.cdr.car)
                body = to_scheme_list(expr.cdr.cdr)
                if not body:
                    raise SchemeError("malformed letrec: empty body")
                new_env = Frame(env)
                for b in bindings:
                    if not isinstance(b, Pair):
                        raise SchemeError("malformed letrec binding")
                    if not isinstance(b.cdr, Pair):
                        raise SchemeError("malformed letrec binding")
                    new_env.vars[b.car.name] = UNASSIGNED
                for b in bindings:
                    val = evaluate(b.cdr.car, new_env)
                    new_env.vars[b.car.name] = val
                env = setup_body_env(body, new_env)
                for f in body[:-1]:
                    if is_define(f):
                        execute_define(f, env)
                    else:
                        evaluate(f, env)
                expr = body[-1]
                if is_define(expr):
                    execute_define(expr, env)
                    return UNSPEC
                continue

            elif name == 'apply':
                args_list = to_scheme_list(expr.cdr)
                if len(args_list) < 2:
                    raise SchemeError("apply: too few arguments")
                proc = evaluate(args_list[0], env)
                individual_args = [evaluate(a, env) for a in args_list[1:-1]]
                lst = evaluate(args_list[-1], env)
                py_args = individual_args + scheme_to_python_list(lst)
                if isinstance(proc, Closure):
                    call_env = make_call_env(proc, py_args)
                    body = proc.body
                    env = setup_body_env(body, call_env)
                    for f in body[:-1]:
                        if is_define(f):
                            execute_define(f, env)
                        else:
                            evaluate(f, env)
                    expr = body[-1]
                    if is_define(expr):
                        execute_define(expr, env)
                        return UNSPEC
                    continue
                elif isinstance(proc, Builtin):
                    _check_arity(proc, len(py_args))
                    return proc.func(py_args)
                else:
                    raise SchemeError("apply: not a procedure")

        # ─── Application ──────────────────────────────────────────────────────
        if isinstance(head, Symbol) and head.name in (
            'quote', 'if', 'define', 'set!', 'begin', 'cond',
            'and', 'or', 'lambda', 'let', 'let*', 'letrec', 'apply'
        ):
            raise SchemeError("malformed special form: " + head.name)

        proc = evaluate(head, env)
        operands = to_scheme_list(expr.cdr)
        args = [evaluate(op, env) for op in operands]

        if isinstance(proc, Closure):
            call_env = make_call_env(proc, args)
            body = proc.body
            env = setup_body_env(body, call_env)
            for f in body[:-1]:
                if is_define(f):
                    execute_define(f, env)
                else:
                    evaluate(f, env)
            expr = body[-1]
            if is_define(expr):
                execute_define(expr, env)
                return UNSPEC
            continue
        elif isinstance(proc, Builtin):
            _check_arity(proc, len(args))
            return proc.func(args)
        else:
            raise SchemeError("not a procedure")


def _check_arity(builtin, n):
    if n < builtin.min_args:
        raise SchemeError(builtin.name + ": too few arguments")
    if builtin.max_args is not None and n > builtin.max_args:
        raise SchemeError(builtin.name + ": too many arguments")


# ─── Equality predicates ───────────────────────────────────────────────────────

def scheme_eq(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if is_int(a) and is_int(b):
        return a == b
    if isinstance(a, Symbol) and isinstance(b, Symbol):
        return a.name == b.name
    if isinstance(a, _Nil) and isinstance(b, _Nil):
        return True
    return a is b


def scheme_equal(a, b):
    stack = [(a, b)]
    while stack:
        a, b = stack.pop()
        if isinstance(a, Pair) and isinstance(b, Pair):
            stack.append((a.cdr, b.cdr))
            stack.append((a.car, b.car))
        elif isinstance(a, str) and isinstance(b, str):
            if a != b:
                return False
        elif isinstance(a, bool) and isinstance(b, bool):
            if a is not b:
                return False
        elif is_int(a) and is_int(b):
            if a != b:
                return False
        elif isinstance(a, Symbol) and isinstance(b, Symbol):
            if a.name != b.name:
                return False
        elif isinstance(a, _Nil) and isinstance(b, _Nil):
            pass
        elif isinstance(a, _Unspecified) and isinstance(b, _Unspecified):
            pass
        elif isinstance(a, (Closure, Builtin)) and isinstance(b, (Closure, Builtin)):
            if a is not b:
                return False
        else:
            return False
    return True


# ─── Builtins ──────────────────────────────────────────────────────────────────

def _call_procedure(proc, args):
    if isinstance(proc, Closure):
        call_env = make_call_env(proc, args)
        body = proc.body
        env = setup_body_env(body, call_env)
        for f in body[:-1]:
            if is_define(f):
                execute_define(f, env)
            else:
                evaluate(f, env)
        return evaluate(body[-1], env)
    elif isinstance(proc, Builtin):
        _check_arity(proc, len(args))
        return proc.func(args)
    else:
        raise SchemeError("not a procedure")


def make_global_env(output):
    env = Frame()

    def reg(name, func, min_args, max_args=None):
        env.vars[name] = Builtin(func, name, min_args, max_args)

    # ── Arithmetic ──
    def b_add(args):
        for a in args:
            if not is_int(a):
                raise SchemeError("+: not a number")
        s = 0
        for a in args:
            s += a
        return s

    def b_mul(args):
        for a in args:
            if not is_int(a):
                raise SchemeError("*: not a number")
        r = 1
        for a in args:
            r *= a
        return r

    def b_sub(args):
        for a in args:
            if not is_int(a):
                raise SchemeError("-: not a number")
        if len(args) == 1:
            return -args[0]
        r = args[0]
        for a in args[1:]:
            r -= a
        return r

    def _quotient(a, b):
        q = abs(a) // abs(b)
        if (a < 0) != (b < 0):
            q = -q
        return q

    def b_quotient(args):
        a, b = args
        if not is_int(a) or not is_int(b):
            raise SchemeError("quotient: not a number")
        if b == 0:
            raise SchemeError("quotient: division by zero")
        return _quotient(a, b)

    def b_remainder(args):
        a, b = args
        if not is_int(a) or not is_int(b):
            raise SchemeError("remainder: not a number")
        if b == 0:
            raise SchemeError("remainder: division by zero")
        return a - b * _quotient(a, b)

    def b_modulo(args):
        a, b = args
        if not is_int(a) or not is_int(b):
            raise SchemeError("modulo: not a number")
        if b == 0:
            raise SchemeError("modulo: division by zero")
        return a % b

    def b_eq(args):
        for a in args:
            if not is_int(a):
                raise SchemeError("=: not a number")
        for i in range(len(args) - 1):
            if args[i] != args[i + 1]:
                return False
        return True

    def b_lt(args):
        for a in args:
            if not is_int(a):
                raise SchemeError("<: not a number")
        for i in range(len(args) - 1):
            if not (args[i] < args[i + 1]):
                return False
        return True

    def b_gt(args):
        for a in args:
            if not is_int(a):
                raise SchemeError(">: not a number")
        for i in range(len(args) - 1):
            if not (args[i] > args[i + 1]):
                return False
        return True

    def b_le(args):
        for a in args:
            if not is_int(a):
                raise SchemeError("<=: not a number")
        for i in range(len(args) - 1):
            if not (args[i] <= args[i + 1]):
                return False
        return True

    def b_ge(args):
        for a in args:
            if not is_int(a):
                raise SchemeError(">=: not a number")
        for i in range(len(args) - 1):
            if not (args[i] >= args[i + 1]):
                return False
        return True

    def b_number_to_string(args):
        n = args[0]
        radix = 10
        if len(args) == 2:
            radix = args[1]
        if not is_int(n):
            raise SchemeError("number->string: not a number")
        if not is_int(radix) or radix not in (2, 8, 10, 16):
            raise SchemeError("number->string: bad radix")
        return int_to_base(n, radix)

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
        return build_proper_list(args)

    def b_null(args):
        return args[0] is NIL

    def b_pair(args):
        return isinstance(args[0], Pair)

    def b_list_p(args):
        return is_proper_list(args[0])

    def b_length(args):
        l = args[0]
        count = 0
        while isinstance(l, Pair):
            count += 1
            l = l.cdr
        if l is not NIL:
            raise SchemeError("length: not a proper list")
        return count

    def b_append(args):
        if not args:
            return NIL
        result = args[-1]
        for i in range(len(args) - 2, -1, -1):
            l = args[i]
            if not is_proper_list(l):
                raise SchemeError("append: not a proper list")
            elements = []
            while isinstance(l, Pair):
                elements.append(l.car)
                l = l.cdr
            for e in reversed(elements):
                result = Pair(e, result)
        return result

    def b_reverse(args):
        l = args[0]
        if not is_proper_list(l):
            raise SchemeError("reverse: not a proper list")
        result = NIL
        while isinstance(l, Pair):
            result = Pair(l.car, result)
            l = l.cdr
        return result

    def b_apply(args):
        if len(args) < 2:
            raise SchemeError("apply: too few arguments")
        proc = args[0]
        individual = args[1:-1]
        lst = args[-1]
        py_args = individual + scheme_to_python_list(lst)
        return _call_procedure(proc, py_args)

    # ── Equality and predicates ──
    def b_eq_q(args):
        return scheme_eq(args[0], args[1])

    def b_equal_q(args):
        return scheme_equal(args[0], args[1])

    def b_not(args):
        return args[0] is False

    def b_number_p(args):
        return is_int(args[0])

    def b_symbol_p(args):
        return isinstance(args[0], Symbol)

    def b_string_p(args):
        return isinstance(args[0], str)

    def b_procedure_p(args):
        return isinstance(args[0], (Closure, Builtin))

    def b_string_append(args):
        for s in args:
            if not isinstance(s, str):
                raise SchemeError("string-append: not a string")
        return ''.join(args)

    # ── Output and errors ──
    def b_display(args):
        display_value(args[0], output, False)
        return UNSPEC

    def b_newline(args):
        output.write('\n')
        return UNSPEC

    def b_error(args):
        if not args:
            raise SchemeError("error: no arguments")
        msg = args[0]
        if not isinstance(msg, str):
            raise SchemeError(str(msg))
        parts = [msg]
        for irritant in args[1:]:
            parts.append(' ')
            parts.append(write_repr(irritant))
        raise SchemeError(''.join(parts))

    # ── Register all ──
    reg('+', b_add, 0)
    reg('*', b_mul, 0)
    reg('-', b_sub, 1)
    reg('quotient', b_quotient, 2, 2)
    reg('remainder', b_remainder, 2, 2)
    reg('modulo', b_modulo, 2, 2)
    reg('=', b_eq, 1)
    reg('<', b_lt, 1)
    reg('>', b_gt, 1)
    reg('<=', b_le, 1)
    reg('>=', b_ge, 1)
    reg('number->string', b_number_to_string, 1, 2)
    reg('cons', b_cons, 2, 2)
    reg('car', b_car, 1, 1)
    reg('cdr', b_cdr, 1, 1)
    reg('list', b_list, 0)
    reg('null?', b_null, 1, 1)
    reg('pair?', b_pair, 1, 1)
    reg('list?', b_list_p, 1, 1)
    reg('length', b_length, 1, 1)
    reg('append', b_append, 0)
    reg('reverse', b_reverse, 1, 1)
    reg('apply', b_apply, 2)
    reg('eq?', b_eq_q, 2, 2)
    reg('equal?', b_equal_q, 2, 2)
    reg('not', b_not, 1, 1)
    reg('number?', b_number_p, 1, 1)
    reg('symbol?', b_symbol_p, 1, 1)
    reg('string?', b_string_p, 1, 1)
    reg('procedure?', b_procedure_p, 1, 1)
    reg('string-append', b_string_append, 0)
    reg('display', b_display, 1, 1)
    reg('newline', b_newline, 0, 0)
    reg('error', b_error, 1)

    return env


# ─── Public API ────────────────────────────────────────────────────────────────

def run(source):
    output = OutputBuffer()
    try:
        forms = read_all(source)
    except SchemeError as e:
        e.output = ''
        raise
    except Exception as e:
        raise SchemeError(str(e))

    try:
        env = make_global_env(output)
        for form in forms:
            evaluate(form, env)
    except SchemeError as e:
        e.output = output.get()
        raise
    except RecursionError:
        raise SchemeError("stack overflow")
    except Exception as e:
        raise SchemeError(str(e))

    return output.get()
