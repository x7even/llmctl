import sys
import threading

try:
    sys.set_int_max_str_digits(0)
except (AttributeError, ValueError):
    pass


class SchemeError(Exception):
    def __init__(self, message=''):
        super().__init__(message)
        self.output = ''


class Symbol:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name
    def __repr__(self):
        return self.name
    def __eq__(self, other):
        return isinstance(other, Symbol) and self.name == other.name
    def __hash__(self):
        return hash(('Symbol', self.name))


class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr


class _EmptyList:
    def __repr__(self):
        return '()'
    def __bool__(self):
        return True

EMPTY = _EmptyList()


class _Unspecified:
    def __repr__(self):
        return '<unspecified>'
    def __bool__(self):
        return True

UNSPECIFIED = _Unspecified()


class _Uninitialized:
    pass

UNINIT = _Uninitialized()


class Closure:
    __slots__ = ('formals', 'body', 'env')
    def __init__(self, formals, body, env):
        self.formals = formals
        self.body = body
        self.env = env


class Builtin:
    __slots__ = ('func', 'name', 'min_args', 'max_args')
    def __init__(self, func, name, min_args=None, max_args=None):
        self.func = func
        self.name = name
        self.min_args = min_args
        self.max_args = max_args


class Env:
    __slots__ = ('vars', 'parent')
    def __init__(self, vars=None, parent=None):
        self.vars = vars if vars is not None else {}
        self.parent = parent

    def lookup(self, sym):
        env = self
        while env is not None:
            if sym in env.vars:
                val = env.vars[sym]
                if isinstance(val, _Uninitialized):
                    raise SchemeError(f"uninitialized variable: {sym.name}")
                return val
            env = env.parent
        raise SchemeError(f"unbound variable: {sym.name}")

    def set(self, sym, val):
        env = self
        while env is not None:
            if sym in env.vars:
                env.vars[sym] = val
                return
            env = env.parent
        raise SchemeError(f"unbound variable: {sym.name}")

    def define(self, sym, val):
        self.vars[sym] = val


_output = []


# --- Reader ---

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
            while i < n and source[i] != '"':
                if source[i] == '\\':
                    i += 1
                    if i >= n:
                        raise SchemeError("unterminated string")
                    ec = source[i]
                    if ec == '"':
                        chars.append('"')
                    elif ec == '\\':
                        chars.append('\\')
                    elif ec == 'n':
                        chars.append('\n')
                    else:
                        raise SchemeError(f"invalid escape: \\{ec}")
                    i += 1
                else:
                    chars.append(source[i])
                    i += 1
            if i >= n:
                raise SchemeError("unterminated string")
            i += 1
            tokens.append(('string', ''.join(chars)))
            continue
        j = i
        while j < n and source[j] not in ' \t\n\r()";\'':
            j += 1
        token = source[i:j]
        tokens.append(('atom', token))
        i = j
    return tokens


def is_integer_token(s):
    if not s:
        return False
    start = 0
    if s[0] in '+-':
        start = 1
        if start >= len(s):
            return False
    for c in s[start:]:
        if c < '0' or c > '9':
            return False
    return True


def parse_atom(token):
    if token == '#t':
        return True
    if token == '#f':
        return False
    if token.startswith('#'):
        raise SchemeError(f"invalid syntax: {token}")
    if is_integer_token(token):
        return int(token)
    return Symbol(token)


def read_all(source):
    tokens = tokenize(source)
    forms = []
    pos = [0]
    while pos[0] < len(tokens):
        forms.append(read_datum(tokens, pos))
    return forms


def read_datum(tokens, pos):
    if pos[0] >= len(tokens):
        raise SchemeError("unexpected end of input")
    ttype, tval = tokens[pos[0]]
    if ttype == '(':
        pos[0] += 1
        return read_list(tokens, pos)
    elif ttype == ')':
        raise SchemeError("unexpected )")
    elif ttype == "'":
        pos[0] += 1
        datum = read_datum(tokens, pos)
        return Pair(Symbol('quote'), Pair(datum, EMPTY))
    elif ttype == 'string':
        pos[0] += 1
        return tval
    elif ttype == 'atom':
        pos[0] += 1
        return parse_atom(tval)
    else:
        raise SchemeError("unexpected token")


def read_list(tokens, pos):
    elements = []
    while True:
        if pos[0] >= len(tokens):
            raise SchemeError("unbalanced (")
        ttype, tval = tokens[pos[0]]
        if ttype == ')':
            pos[0] += 1
            result = EMPTY
            for elem in reversed(elements):
                result = Pair(elem, result)
            return result
        if ttype == 'atom' and tval == '.':
            pos[0] += 1
            if not elements:
                raise SchemeError("dot without preceding element")
            if pos[0] >= len(tokens):
                raise SchemeError("expected datum after dot")
            tail = read_datum(tokens, pos)
            if pos[0] >= len(tokens) or tokens[pos[0]][0] != ')':
                raise SchemeError("expected ) after dot datum")
            pos[0] += 1
            result = tail
            for elem in reversed(elements):
                result = Pair(elem, result)
            return result
        elements.append(read_datum(tokens, pos))


# --- Helpers ---

def list_to_python(lst):
    result = []
    while isinstance(lst, Pair):
        result.append(lst.car)
        lst = lst.cdr
    if lst is not EMPTY:
        raise SchemeError("improper list")
    return result


def list_to_scheme(items):
    result = EMPTY
    for item in reversed(items):
        result = Pair(item, result)
    return result


def is_proper_list(x):
    while isinstance(x, Pair):
        x = x.cdr
    return x is EMPTY


# --- Display / Write representations ---

def int_to_str(n, radix=10):
    if n == 0:
        return '0'
    negative = n < 0
    n = abs(n)
    digits = '0123456789abcdef'
    result = []
    while n > 0:
        result.append(digits[n % radix])
        n //= radix
    s = ''.join(reversed(result))
    if negative:
        return '-' + s
    return s


def display_repr(x):
    if isinstance(x, bool):
        return '#t' if x else '#f'
    if isinstance(x, int):
        return int_to_str(x, 10)
    if isinstance(x, str):
        return x
    if isinstance(x, Symbol):
        return x.name
    if x is EMPTY:
        return '()'
    if isinstance(x, Pair):
        return display_pair(x)
    if isinstance(x, (Closure, Builtin)):
        return '#<procedure>'
    if isinstance(x, _Unspecified):
        return ''
    return str(x)


def display_pair(p):
    parts = []
    current = p
    while isinstance(current, Pair):
        parts.append(display_repr(current.car))
        current = current.cdr
    if current is EMPTY:
        return '(' + ' '.join(parts) + ')'
    else:
        return '(' + ' '.join(parts) + ' . ' + display_repr(current) + ')'


def write_repr(x):
    if isinstance(x, bool):
        return '#t' if x else '#f'
    if isinstance(x, int):
        return int_to_str(x, 10)
    if isinstance(x, str):
        return write_string(x)
    if isinstance(x, Symbol):
        return x.name
    if x is EMPTY:
        return '()'
    if isinstance(x, Pair):
        return write_pair(x)
    if isinstance(x, (Closure, Builtin)):
        return '#<procedure>'
    if isinstance(x, _Unspecified):
        return ''
    return str(x)


def write_string(s):
    out = ['"']
    for c in s:
        if c == '"':
            out.append('\\"')
        elif c == '\\':
            out.append('\\\\')
        elif c == '\n':
            out.append('\\n')
        else:
            out.append(c)
    out.append('"')
    return ''.join(out)


def write_pair(p):
    parts = []
    current = p
    while isinstance(current, Pair):
        parts.append(write_repr(current.car))
        current = current.cdr
    if current is EMPTY:
        return '(' + ' '.join(parts) + ')'
    else:
        return '(' + ' '.join(parts) + ' . ' + write_repr(current) + ')'


# --- Evaluator ---

class TailCall:
    __slots__ = ('proc', 'args')
    def __init__(self, proc, args):
        self.proc = proc
        self.args = args


def eval_expr(expr, env, tail=False):
    if isinstance(expr, bool):
        return expr
    if isinstance(expr, int):
        return expr
    if isinstance(expr, str):
        return expr
    if expr is EMPTY:
        raise SchemeError("cannot evaluate ()")
    if isinstance(expr, Symbol):
        return env.lookup(expr)
    if isinstance(expr, Pair):
        return eval_form(expr, env, tail)
    return expr


def eval_form(expr, env, tail):
    head = expr.car
    if isinstance(head, Symbol):
        name = head.name
        if name == 'quote':
            return eval_quote(expr)
        elif name == 'if':
            return eval_if(expr, env, tail)
        elif name == 'define':
            return eval_define(expr, env)
        elif name == 'set!':
            return eval_set(expr, env)
        elif name == 'begin':
            return eval_begin(expr, env, tail)
        elif name == 'cond':
            return eval_cond(expr, env, tail)
        elif name == 'and':
            return eval_and(expr, env, tail)
        elif name == 'or':
            return eval_or(expr, env, tail)
        elif name == 'lambda':
            return eval_lambda(expr, env)
        elif name == 'let':
            return eval_let(expr, env, tail)
        elif name == 'let*':
            return eval_letstar(expr, env, tail)
        elif name == 'letrec':
            return eval_letrec(expr, env, tail)
        elif name == 'apply':
            return eval_apply_form(expr, env, tail)

    # Procedure application
    return eval_application(expr, env, tail)


def eval_quote(expr):
    rest = expr.cdr
    if not isinstance(rest, Pair) or not isinstance(rest.cdr, _EmptyList):
        raise SchemeError("malformed quote")
    return rest.car


def eval_if(expr, env, tail):
    args = list_to_python(expr.cdr)
    if len(args) < 2 or len(args) > 3:
        raise SchemeError("malformed if")
    test = eval_expr(args[0], env, tail=False)
    if test is False:
        if len(args) == 3:
            return eval_expr(args[2], env, tail=tail)
        return UNSPECIFIED
    else:
        return eval_expr(args[1], env, tail=tail)


def eval_define(expr, env):
    rest = expr.cdr
    if not isinstance(rest, Pair):
        raise SchemeError("malformed define")
    target = rest.car
    if isinstance(target, Symbol):
        exprs = list_to_python(rest.cdr)
        if len(exprs) != 1:
            raise SchemeError("malformed define")
        val = eval_expr(exprs[0], env, tail=False)
        env.define(target, val)
        return UNSPECIFIED
    elif isinstance(target, Pair):
        name = target.car
        if not isinstance(name, Symbol):
            raise SchemeError("malformed define")
        formals = target.cdr
        body = list_to_python(rest.cdr)
        if not body:
            raise SchemeError("malformed define")
        closure = Closure(formals, body, env)
        env.define(name, closure)
        return UNSPECIFIED
    else:
        raise SchemeError("malformed define")


def eval_set(expr, env):
    rest = expr.cdr
    if not isinstance(rest, Pair):
        raise SchemeError("malformed set!")
    name = rest.car
    if not isinstance(name, Symbol):
        raise SchemeError("malformed set!")
    exprs = list_to_python(rest.cdr)
    if len(exprs) != 1:
        raise SchemeError("malformed set!")
    val = eval_expr(exprs[0], env, tail=False)
    env.set(name, val)
    return UNSPECIFIED


def eval_begin(expr, env, tail):
    forms = list_to_python(expr.cdr)
    if not forms:
        raise SchemeError("empty begin")
    for form in forms[:-1]:
        eval_expr(form, env, tail=False)
    return eval_expr(forms[-1], env, tail=tail)


def eval_cond(expr, env, tail):
    clauses = list_to_python(expr.cdr)
    if not clauses:
        raise SchemeError("malformed cond")
    for i, clause in enumerate(clauses):
        if not isinstance(clause, Pair):
            raise SchemeError("malformed cond clause")
        test = clause.car
        body = list_to_python(clause.cdr)
        if isinstance(test, Symbol) and test.name == 'else':
            if i != len(clauses) - 1:
                raise SchemeError("else not last clause")
            if not body:
                return UNSPECIFIED
            for form in body[:-1]:
                eval_expr(form, env, tail=False)
            return eval_expr(body[-1], env, tail=tail)
        val = eval_expr(test, env, tail=False)
        if val is not False:
            if not body:
                return val
            for form in body[:-1]:
                eval_expr(form, env, tail=False)
            return eval_expr(body[-1], env, tail=tail)
    return UNSPECIFIED


def eval_and(expr, env, tail):
    args = list_to_python(expr.cdr)
    if not args:
        return True
    for arg in args[:-1]:
        val = eval_expr(arg, env, tail=False)
        if val is False:
            return False
    return eval_expr(args[-1], env, tail=tail)


def eval_or(expr, env, tail):
    args = list_to_python(expr.cdr)
    if not args:
        return False
    for arg in args[:-1]:
        val = eval_expr(arg, env, tail=False)
        if val is not False:
            return val
    return eval_expr(args[-1], env, tail=tail)


def eval_lambda(expr, env):
    rest = expr.cdr
    if not isinstance(rest, Pair):
        raise SchemeError("malformed lambda")
    formals = rest.car
    body = list_to_python(rest.cdr)
    if not body:
        raise SchemeError("empty lambda body")
    return Closure(formals, body, env)


def eval_let(expr, env, tail):
    rest = expr.cdr
    if not isinstance(rest, Pair):
        raise SchemeError("malformed let")
    first = rest.car
    if isinstance(first, Symbol):
        return eval_named_let(expr, env, tail)
    bindings_form = first
    body = list_to_python(rest.cdr)
    if not body:
        raise SchemeError("empty let body")
    bindings = list_to_python(bindings_form) if bindings_form is not EMPTY else []
    inits = []
    for b in bindings:
        if not isinstance(b, Pair):
            raise SchemeError("malformed let binding")
        var = b.car
        if not isinstance(var, Symbol):
            raise SchemeError("malformed let binding")
        init_expr = b.cdr
        if not isinstance(init_expr, Pair):
            raise SchemeError("malformed let binding")
        val = eval_expr(init_expr.car, env, tail=False)
        inits.append((var, val))
    new_env = Env({v: val for v, val in inits}, parent=env)
    return eval_body(body, new_env, tail)


def eval_letstar(expr, env, tail):
    rest = expr.cdr
    if not isinstance(rest, Pair):
        raise SchemeError("malformed let*")
    bindings_form = rest.car
    body = list_to_python(rest.cdr)
    if not body:
        raise SchemeError("empty let* body")
    bindings = list_to_python(bindings_form) if bindings_form is not EMPTY else []
    current_env = env
    for b in bindings:
        if not isinstance(b, Pair):
            raise SchemeError("malformed let* binding")
        var = b.car
        if not isinstance(var, Symbol):
            raise SchemeError("malformed let* binding")
        init_expr = b.cdr
        if not isinstance(init_expr, Pair):
            raise SchemeError("malformed let* binding")
        val = eval_expr(init_expr.car, current_env, tail=False)
        current_env = Env({var: val}, parent=current_env)
    return eval_body(body, current_env, tail)


def eval_letrec(expr, env, tail):
    rest = expr.cdr
    if not isinstance(rest, Pair):
        raise SchemeError("malformed letrec")
    bindings_form = rest.car
    body = list_to_python(rest.cdr)
    if not body:
        raise SchemeError("empty letrec body")
    bindings = list_to_python(bindings_form) if bindings_form is not EMPTY else []
    new_env = Env({}, parent=env)
    for b in bindings:
        if not isinstance(b, Pair):
            raise SchemeError("malformed letrec binding")
        var = b.car
        if not isinstance(var, Symbol):
            raise SchemeError("malformed letrec binding")
        new_env.define(var, UNINIT)
    for b in bindings:
        var = b.car
        init_expr = b.cdr
        if not isinstance(init_expr, Pair):
            raise SchemeError("malformed letrec binding")
        val = eval_expr(init_expr.car, new_env, tail=False)
        new_env.vars[var] = val
    return eval_body(body, new_env, tail)


def eval_named_let(expr, env, tail):
    rest = expr.cdr
    name = rest.car
    bindings_form = rest.cdr.car
    body = list_to_python(rest.cdr.cdr)
    if not body:
        raise SchemeError("empty named let body")
    bindings = list_to_python(bindings_form) if bindings_form is not EMPTY else []
    init_vals = []
    formals = []
    for b in bindings:
        if not isinstance(b, Pair):
            raise SchemeError("malformed named let binding")
        var = b.car
        if not isinstance(var, Symbol):
            raise SchemeError("malformed named let binding")
        init_expr = b.cdr
        if not isinstance(init_expr, Pair):
            raise SchemeError("malformed named let binding")
        val = eval_expr(init_expr.car, env, tail=False)
        init_vals.append(val)
        formals.append(var)
    new_env = Env({}, parent=env)
    formals_list = list_to_scheme(formals)
    closure = Closure(formals_list, body, new_env)
    new_env.define(name, closure)
    if tail:
        return TailCall(closure, init_vals)
    else:
        return apply_proc(closure, init_vals, tail=False)


def is_define(form):
    return (isinstance(form, Pair) and isinstance(form.car, Symbol)
            and form.car.name == 'define')


def get_define_name(form):
    rest = form.cdr
    if not isinstance(rest, Pair):
        raise SchemeError("malformed define")
    target = rest.car
    if isinstance(target, Symbol):
        return target
    elif isinstance(target, Pair):
        if isinstance(target.car, Symbol):
            return target.car
    raise SchemeError("malformed define")


def eval_body(body, env, tail):
    defines = [f for f in body if is_define(f)]
    if defines:
        for d in defines:
            name = get_define_name(d)
            env.define(name, UNINIT)
    for i, form in enumerate(body):
        is_last = (i == len(body) - 1)
        if is_define(form):
            eval_define(form, env)
            if is_last:
                return UNSPECIFIED
        else:
            if is_last:
                return eval_expr(form, env, tail=tail)
            else:
                eval_expr(form, env, tail=False)
    return UNSPECIFIED


def check_closure_arity(formals, nargs):
    if isinstance(formals, Symbol):
        return
    count = 0
    current = formals
    while isinstance(current, Pair):
        count += 1
        current = current.cdr
    if isinstance(current, Symbol):
        if nargs < count:
            raise SchemeError("too few arguments")
    else:
        if nargs != count:
            raise SchemeError("wrong number of arguments")


def bind_formals(formals, args, parent_env):
    if isinstance(formals, Symbol):
        return Env({formals: list_to_scheme(args)}, parent=parent_env)
    params = []
    current = formals
    while isinstance(current, Pair):
        p = current.car
        if not isinstance(p, Symbol):
            raise SchemeError("malformed formals")
        params.append(p)
        current = current.cdr
    if isinstance(current, Symbol):
        if len(args) < len(params):
            raise SchemeError("too few arguments")
        env_vars = {}
        for p, a in zip(params, args[:len(params)]):
            env_vars[p] = a
        env_vars[current] = list_to_scheme(args[len(params):])
        return Env(env_vars, parent=parent_env)
    else:
        if len(args) != len(params):
            raise SchemeError("wrong number of arguments")
        env_vars = {}
        for p, a in zip(params, args):
            env_vars[p] = a
        return Env(env_vars, parent=parent_env)


def apply_proc(proc, args, tail):
    if isinstance(proc, Closure):
        check_closure_arity(proc.formals, len(args))
        new_env = bind_formals(proc.formals, args, proc.env)
        return eval_body(proc.body, new_env, tail)
    elif isinstance(proc, Builtin):
        return proc.func(args)
    else:
        raise SchemeError("not a procedure")


def eval_application(expr, env, tail):
    op = eval_expr(expr.car, env, tail=False)
    args = []
    current = expr.cdr
    while isinstance(current, Pair):
        args.append(eval_expr(current.car, env, tail=False))
        current = current.cdr
    if current is not EMPTY:
        raise SchemeError("dotted form used as application")
    if not isinstance(op, (Closure, Builtin)):
        raise SchemeError("not a procedure")
    if isinstance(op, Builtin):
        check_arity(op, len(args))
    else:
        check_closure_arity(op.formals, len(args))
    if tail:
        return TailCall(op, args)
    else:
        return apply_proc(op, args, tail=False)


def eval_apply_form(expr, env, tail):
    args_forms = list_to_python(expr.cdr)
    if len(args_forms) < 2:
        raise SchemeError("apply: needs at least 2 arguments")
    f = eval_expr(args_forms[0], env, tail=False)
    evaluated = []
    for af in args_forms[1:]:
        evaluated.append(eval_expr(af, env, tail=False))
    lst = evaluated[-1]
    if not is_proper_list(lst):
        raise SchemeError("apply: last argument must be a proper list")
    full_args = evaluated[:-1] + list_to_python(lst)
    if not isinstance(f, (Closure, Builtin)):
        raise SchemeError("apply: not a procedure")
    if isinstance(f, Builtin):
        check_arity(f, len(full_args))
    else:
        check_closure_arity(f.formals, len(full_args))
    if tail:
        return TailCall(f, full_args)
    else:
        return apply_proc(f, full_args, tail=False)


def check_arity(proc, nargs):
    if isinstance(proc, Builtin):
        if proc.min_args is not None and nargs < proc.min_args:
            raise SchemeError(f"{proc.name}: too few arguments")
        if proc.max_args is not None and nargs > proc.max_args:
            raise SchemeError(f"{proc.name}: too many arguments")


# --- Builtins ---

def make_global_env():
    env = Env()

    def def_builtin(name, func, min_args=None, max_args=None):
        env.define(Symbol(name), Builtin(func, name, min_args, max_args))

    def require_int(x, fname):
        if isinstance(x, bool) or not isinstance(x, int):
            raise SchemeError(f"{fname}: expected integer")

    def require_string(x, fname):
        if not isinstance(x, str):
            raise SchemeError(f"{fname}: expected string")

    def require_pair(x, fname):
        if not isinstance(x, Pair):
            raise SchemeError(f"{fname}: expected pair")

    # Numbers
    def b_add(args):
        s = 0
        for a in args:
            require_int(a, '+')
            s += a
        return s

    def b_mul(args):
        s = 1
        for a in args:
            require_int(a, '*')
            s *= a
        return s

    def b_sub(args):
        if not args:
            raise SchemeError("-: needs at least 1 argument")
        require_int(args[0], '-')
        if len(args) == 1:
            return -args[0]
        s = args[0]
        for a in args[1:]:
            require_int(a, '-')
            s -= a
        return s

    def b_quotient(args):
        require_int(args[0], 'quotient')
        require_int(args[1], 'quotient')
        if args[1] == 0:
            raise SchemeError("quotient: division by zero")
        q = abs(args[0]) // abs(args[1])
        if (args[0] < 0) != (args[1] < 0):
            q = -q
        return q

    def b_remainder(args):
        require_int(args[0], 'remainder')
        require_int(args[1], 'remainder')
        if args[1] == 0:
            raise SchemeError("remainder: division by zero")
        q = abs(args[0]) // abs(args[1])
        if (args[0] < 0) != (args[1] < 0):
            q = -q
        return args[0] - q * args[1]

    def b_modulo(args):
        require_int(args[0], 'modulo')
        require_int(args[1], 'modulo')
        if args[1] == 0:
            raise SchemeError("modulo: division by zero")
        return args[0] - (args[0] // args[1]) * args[1]

    def make_cmp(op):
        def cmp(args):
            for a in args:
                require_int(a, op)
            for i in range(len(args) - 1):
                if not compare(args[i], args[i + 1], op):
                    return False
            return True
        return cmp

    def compare(a, b, op):
        if op == '=':
            return a == b
        elif op == '<':
            return a < b
        elif op == '>':
            return a > b
        elif op == '<=':
            return a <= b
        elif op == '>=':
            return a >= b

    def b_num_to_str(args):
        require_int(args[0], 'number->string')
        radix = 10
        if len(args) == 2:
            require_int(args[1], 'number->string')
            radix = args[1]
            if radix not in (2, 8, 10, 16):
                raise SchemeError("number->string: invalid radix")
        return int_to_str(args[0], radix)

    def b_eq(args):
        for a in args:
            require_int(a, '=')
        for i in range(len(args) - 1):
            if args[i] != args[i + 1]:
                return False
        return True

    def b_lt(args):
        for a in args:
            require_int(a, '<')
        for i in range(len(args) - 1):
            if not (args[i] < args[i + 1]):
                return False
        return True

    def b_gt(args):
        for a in args:
            require_int(a, '>')
        for i in range(len(args) - 1):
            if not (args[i] > args[i + 1]):
                return False
        return True

    def b_le(args):
        for a in args:
            require_int(a, '<=')
        for i in range(len(args) - 1):
            if not (args[i] <= args[i + 1]):
                return False
        return True

    def b_ge(args):
        for a in args:
            require_int(a, '>=')
        for i in range(len(args) - 1):
            if not (args[i] >= args[i + 1]):
                return False
        return True

    def b_num_to_str2(args):
        require_int(args[0], 'number->string')
        radix = 10
        if len(args) == 2:
            require_int(args[1], 'number->string')
            radix = args[1]
            if radix not in (2, 8, 10, 16):
                raise SchemeError("number->string: invalid radix")
        return int_to_str(args[0], radix)

    def_def = def_builtin
    def_def('+', b_add, 0, None)
    def_def('*', b_mul, 0, None)
    def_def('-', b_sub, 1, None)
    def_def('quotient', b_quotient, 2, 2)
    def_def('remainder', b_remainder, 2, 2)
    def_def('modulo', b_modulo, 2, 2)
    def_def('=', b_eq, 1, None)
    def_def('<', b_lt, 1, None)
    def_def('>', b_gt, 1, None)
    def_def('<=', b_le, 1, None)
    def_def('>=', b_ge, 1, None)
    def_def('number->string', b_num_to_str2, 1, 2)

    # Lists and pairs
    def b_cons(args):
        return Pair(args[0], args[1])

    def b_car(args):
        require_pair(args[0], 'car')
        return args[0].car

    def b_cdr(args):
        require_pair(args[0], 'cdr')
        return args[0].cdr

    def b_list(args):
        return list_to_scheme(args)

    def b_null(args):
        return args[0] is EMPTY

    def b_pair(args):
        return isinstance(args[0], Pair)

    def b_listp(args):
        return is_proper_list(args[0])

    def b_length(args):
        x = args[0]
        count = 0
        while isinstance(x, Pair):
            count += 1
            x = x.cdr
        if x is not EMPTY:
            raise SchemeError("length: not a proper list")
        return count

    def b_append(args):
        if not args:
            return EMPTY
        result_parts = []
        for i, a in enumerate(args[:-1]):
            if not is_proper_list(a):
                raise SchemeError("append: not a proper list")
            current = a
            while isinstance(current, Pair):
                result_parts.append(current.car)
                current = current.cdr
        tail = args[-1]
        result = tail
        for part in reversed(result_parts):
            result = Pair(part, result)
        return result

    def b_reverse(args):
        x = args[0]
        items = []
        while isinstance(x, Pair):
            items.append(x.car)
            x = x.cdr
        if x is not EMPTY:
            raise SchemeError("reverse: not a proper list")
        return list_to_scheme(items)

    def b_apply(args):
        f = args[0]
        lst = args[-1]
        if not is_proper_list(lst):
            raise SchemeError("apply: last argument must be a proper list")
        full_args = list(args[1:-1]) + list_to_python(lst)
        if not isinstance(f, (Closure, Builtin)):
            raise SchemeError("apply: not a procedure")
        if isinstance(f, Builtin):
            check_arity(f, len(full_args))
        else:
            check_closure_arity(f.formals, len(full_args))
        return apply_proc(f, full_args, tail=False)

    def_def('cons', b_cons, 2, 2)
    def_def('car', b_car, 1, 1)
    def_def('cdr', b_cdr, 1, 1)
    def_def('list', b_list, 0, None)
    def_def('null?', b_null, 1, 1)
    def_def('pair?', b_pair, 1, 1)
    def_def('list?', b_listp, 1, 1)
    def_def('length', b_length, 1, 1)
    def_def('append', b_append, 0, None)
    def_def('reverse', b_reverse, 1, 1)
    def_def('apply', b_apply, 2, None)

    # Equality and predicates
    def b_eqq(args):
        a, b = args[0], args[1]
        if isinstance(a, bool) or isinstance(b, bool):
            return a is b
        if isinstance(a, int) and isinstance(b, int):
            return a == b
        if isinstance(a, Symbol) and isinstance(b, Symbol):
            return a.name == b.name
        if a is EMPTY and b is EMPTY:
            return True
        return a is b

    def b_equal(args):
        return equal_check(args[0], args[1])

    def b_not(args):
        return args[0] is False

    def b_number(args):
        return isinstance(args[0], int) and not isinstance(args[0], bool)

    def b_symbol(args):
        return isinstance(args[0], Symbol)

    def b_string(args):
        return isinstance(args[0], str)

    def b_procedure(args):
        return isinstance(args[0], (Closure, Builtin))

    def b_string_append(args):
        parts = []
        for a in args:
            require_string(a, 'string-append')
            parts.append(a)
        return ''.join(parts)

    def_def('eq?', b_eqq, 2, 2)
    def_def('equal?', b_equal, 2, 2)
    def_def('not', b_not, 1, 1)
    def_def('number?', b_number, 1, 1)
    def_def('symbol?', b_symbol, 1, 1)
    def_def('string?', b_string, 1, 1)
    def_def('procedure?', b_procedure, 1, 1)
    def_def('string-append', b_string_append, 0, None)

    # Output and errors
    def b_display(args):
        _output.append(display_repr(args[0]))
        return UNSPECIFIED

    def b_newline(args):
        _output.append('\n')
        return UNSPECIFIED

    def b_error(args):
        msg = args[0]
        if isinstance(msg, str):
            parts = [msg]
        else:
            parts = [str(msg)]
        for irr in args[1:]:
            parts.append(' ' + write_repr(irr))
        raise SchemeError(''.join(parts))

    def_def('display', b_display, 1, 1)
    def_def('newline', b_newline, 0, 0)
    def_def('error', b_error, 1, None)

    return env


def equal_check(a, b):
    stack = [(a, b)]
    while stack:
        a, b = stack.pop()
        if isinstance(a, Pair) and isinstance(b, Pair):
            stack.append((a.cdr, b.cdr))
            stack.append((a.car, b.car))
        elif isinstance(a, bool) and isinstance(b, bool):
            if a is not b:
                return False
        elif isinstance(a, int) and isinstance(b, int):
            if a != b:
                return False
        elif isinstance(a, str) and isinstance(b, str):
            if a != b:
                return False
        elif isinstance(a, Symbol) and isinstance(b, Symbol):
            if a.name != b.name:
                return False
        elif a is EMPTY and b is EMPTY:
            pass
        elif isinstance(a, (Closure, Builtin)) and isinstance(b, (Closure, Builtin)):
            if a is not b:
                return False
        elif isinstance(a, _Unspecified) and isinstance(b, _Unspecified):
            pass
        else:
            return False
    return True


# --- Trampoline ---

def run_expr(expr, env):
    result = eval_expr(expr, env, tail=True)
    while isinstance(result, TailCall):
        result = apply_proc(result.proc, result.args, tail=True)
    return result


# --- Public API ---

def run(source):
    global _output
    _output = []
    result = ['']
    error = [None]

    def _do_work():
        try:
            forms = read_all(source)
            global_env = make_global_env()
            for form in forms:
                run_expr(form, global_env)
            result[0] = ''.join(_output)
        except SchemeError as e:
            error[0] = e
        except RecursionError as e:
            error[0] = SchemeError("stack overflow")
        except Exception as e:
            error[0] = SchemeError(str(e))

    old_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(1000000)
    try:
        threading.stack_size(64 * 1024 * 1024)
    except (ValueError, RuntimeError):
        pass

    t = threading.Thread(target=_do_work)
    t.start()
    t.join()
    sys.setrecursionlimit(old_limit)

    if error[0] is not None:
        error[0].output = ''.join(_output)
        raise error[0]
    return result[0]
