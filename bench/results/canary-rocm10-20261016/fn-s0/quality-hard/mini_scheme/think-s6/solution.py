import sys

sys.setrecursionlimit(200000)
try:
    sys.set_int_max_str_digits(0)
except AttributeError:
    pass


class SchemeError(Exception):
    def __init__(self, msg, output=''):
        super().__init__(msg)
        self.output = output


# ─── Data Types ───────────────────────────────────────────────────────────────

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

class Nil:
    def __repr__(self):
        return '()'

NIL = Nil()

class Unspecified:
    pass
UNSPECIFIED = Unspecified()

class Unbound:
    pass
UNBOUND = Unbound()

class Closure:
    __slots__ = ('formals', 'body', 'env')
    def __init__(self, formals, body, env):
        self.formals = formals
        self.body = body
        self.env = env

class Builtin:
    __slots__ = ('name', 'func', 'min_args', 'max_args')
    def __init__(self, name, func, min_args, max_args=None):
        self.name = name
        self.func = func
        self.min_args = min_args
        self.max_args = max_args

class TailCall:
    __slots__ = ('proc', 'args')
    def __init__(self, proc, args):
        self.proc = proc
        self.args = args


# ─── Symbol Interning ─────────────────────────────────────────────────────────

_symbol_table = {}
def make_symbol(name):
    s = _symbol_table.get(name)
    if s is None:
        s = Symbol(name)
        _symbol_table[name] = s
    return s


# ─── Environment ──────────────────────────────────────────────────────────────

class Frame:
    __slots__ = ('vars', 'parent')
    def __init__(self, parent=None):
        self.vars = {}
        self.parent = parent


# ─── Reader ───────────────────────────────────────────────────────────────────

def tokenize(source):
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
            tokens.append(('(', '('))
            i += 1
        elif c == ')':
            tokens.append((')', ')'))
            i += 1
        elif c == "'":
            tokens.append(("'", "'"))
            i += 1
        elif c == '"':
            i += 1
            chars = []
            while i < n and source[i] != '"':
                if source[i] == '\\':
                    i += 1
                    if i >= n:
                        raise SchemeError("unterminated string")
                    nc = source[i]
                    if nc == '"':
                        chars.append('"')
                    elif nc == '\\':
                        chars.append('\\')
                    elif nc == 'n':
                        chars.append('\n')
                    else:
                        raise SchemeError("bad escape character")
                    i += 1
                else:
                    chars.append(source[i])
                    i += 1
            if i >= n:
                raise SchemeError("unterminated string")
            i += 1
            tokens.append(('string', ''.join(chars)))
        else:
            start = i
            while i < n and source[i] not in ' \t\n\r()";\'':
                i += 1
            tokens.append(('atom', source[start:i]))
    return tokens


def parse(tokens):
    pos = [0]
    forms = []
    while pos[0] < len(tokens):
        if tokens[pos[0]][0] == ')':
            raise SchemeError("unexpected )")
        forms.append(parse_expr(tokens, pos))
    return forms


def parse_expr(tokens, pos):
    if pos[0] >= len(tokens):
        raise SchemeError("unexpected end of input")
    ttype, tval = tokens[pos[0]]
    if ttype == '(':
        pos[0] += 1
        return parse_list_body(tokens, pos)
    elif ttype == ')':
        raise SchemeError("unexpected )")
    elif ttype == "'":
        pos[0] += 1
        if pos[0] >= len(tokens):
            raise SchemeError("quote not followed by datum")
        if tokens[pos[0]][0] == ')':
            raise SchemeError("quote not followed by datum")
        datum = parse_expr(tokens, pos)
        return Pair(make_symbol('quote'), Pair(datum, NIL))
    elif ttype == 'string':
        pos[0] += 1
        return tval
    elif ttype == 'atom':
        pos[0] += 1
        return parse_atom(tval)
    else:
        raise SchemeError("unexpected token")


def parse_list_body(tokens, pos):
    elements = []
    while True:
        if pos[0] >= len(tokens):
            raise SchemeError("unbalanced (")
        ttype = tokens[pos[0]][0]
        if ttype == ')':
            pos[0] += 1
            return build_list(elements, NIL)
        if ttype == 'atom' and tokens[pos[0]][1] == '.':
            pos[0] += 1
            if not elements:
                raise SchemeError("dot with no preceding element")
            if pos[0] >= len(tokens) or tokens[pos[0]][0] == ')':
                raise SchemeError("dot not followed by datum")
            dotted = parse_expr(tokens, pos)
            if pos[0] >= len(tokens) or tokens[pos[0]][0] != ')':
                raise SchemeError("expected ) after dotted pair")
            pos[0] += 1
            return build_list(elements, dotted)
        elements.append(parse_expr(tokens, pos))


def build_list(elements, tail):
    result = tail
    for elem in reversed(elements):
        result = Pair(elem, result)
    return result


def parse_atom(token):
    if token == '#t':
        return True
    if token == '#f':
        return False
    if token.startswith('#'):
        raise SchemeError("invalid # token: " + token)
    if is_integer_token(token):
        return int(token)
    return make_symbol(token)


def is_integer_token(s):
    if not s:
        return False
    i = 0
    if s[0] in '+-':
        i = 1
    if i >= len(s):
        return False
    while i < len(s):
        if not ('0' <= s[i] <= '9'):
            return False
        i += 1
    return True


# ─── Helpers ──────────────────────────────────────────────────────────────────

def is_true(x):
    return x is not False

def to_list(scheme_list):
    result = []
    current = scheme_list
    while isinstance(current, Pair):
        result.append(current.car)
        current = current.cdr
    if not isinstance(current, Nil):
        raise SchemeError("improper list")
    return result

def list_to_scheme(items):
    result = NIL
    for item in reversed(items):
        result = Pair(item, result)
    return result

def is_proper(x):
    while isinstance(x, Pair):
        x = x.cdr
    return isinstance(x, Nil)

def lookup(name, env):
    frame = env
    while frame is not None:
        if name in frame.vars:
            val = frame.vars[name]
            if isinstance(val, Unbound):
                raise SchemeError("unbound variable: " + name)
            return val
        frame = frame.parent
    raise SchemeError("unbound variable: " + name)

def set_var(name, val, env):
    frame = env
    while frame is not None:
        if name in frame.vars:
            frame.vars[name] = val
            return
        frame = frame.parent
    raise SchemeError("unbound variable: " + name)


# ─── Display / Write ──────────────────────────────────────────────────────────

def display_repr(val):
    if isinstance(val, Unspecified):
        return ''
    if isinstance(val, Nil):
        return '()'
    if isinstance(val, Pair):
        return display_pair(val)
    if type(val) is bool:
        return '#t' if val else '#f'
    if type(val) is str:
        return val
    if isinstance(val, Symbol):
        return val.name
    if type(val) is int:
        return str(val)
    if isinstance(val, (Closure, Builtin)):
        return '#<procedure>'
    return str(val)

def display_pair(val):
    elements = []
    current = val
    while isinstance(current, Pair):
        elements.append(display_repr(current.car))
        current = current.cdr
    if isinstance(current, Nil):
        return '(' + ' '.join(elements) + ')'
    else:
        elements.append('. ' + display_repr(current))
        return '(' + ' '.join(elements) + ')'

def write_repr(val):
    if isinstance(val, str):
        escaped = val.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        return '"' + escaped + '"'
    if isinstance(val, Pair):
        return write_pair(val)
    return display_repr(val)

def write_pair(val):
    elements = []
    current = val
    while isinstance(current, Pair):
        elements.append(write_repr(current.car))
        current = current.cdr
    if isinstance(current, Nil):
        return '(' + ' '.join(elements) + ')'
    else:
        elements.append('. ' + write_repr(current))
        return '(' + ' '.join(elements) + ')'


# ─── Evaluator ────────────────────────────────────────────────────────────────

def run_trampoline(result, output):
    while isinstance(result, TailCall):
        result = apply_proc(result.proc, result.args, output)
    return result

def eval_non_tail(expr, env, output):
    result = eval_expr(expr, env, output)
    return run_trampoline(result, output)

def eval_expr(expr, env, output):
    if type(expr) is int:
        return expr
    if type(expr) is bool:
        return expr
    if type(expr) is str:
        return expr
    if isinstance(expr, Symbol):
        return lookup(expr.name, env)
    if isinstance(expr, Nil):
        raise SchemeError("cannot evaluate ()")
    if isinstance(expr, Pair):
        head = expr.car
        if isinstance(head, Symbol):
            name = head.name
            if name == 'quote':
                return handle_quote(expr)
            if name == 'if':
                return handle_if(expr, env, output)
            if name == 'define':
                return handle_define(expr, env, output)
            if name == 'set!':
                return handle_set(expr, env, output)
            if name == 'begin':
                return handle_begin(expr, env, output)
            if name == 'cond':
                return handle_cond(expr, env, output)
            if name == 'and':
                return handle_and(expr, env, output)
            if name == 'or':
                return handle_or(expr, env, output)
            if name == 'let':
                return handle_let(expr, env, output)
            if name == 'let*':
                return handle_letstar(expr, env, output)
            if name == 'letrec':
                return handle_letrec(expr, env, output)
            if name == 'lambda':
                return handle_lambda(expr, env)
            if name == 'apply':
                return handle_apply(expr, env, output)
        return handle_application(expr, env, output)
    raise SchemeError("cannot evaluate")


def handle_quote(expr):
    rest = expr.cdr
    if not isinstance(rest, Pair):
        raise SchemeError("malformed quote")
    return rest.car

def handle_if(expr, env, output):
    args = to_list(expr.cdr)
    if len(args) < 2 or len(args) > 3:
        raise SchemeError("malformed if")
    test = eval_non_tail(args[0], env, output)
    if is_true(test):
        return eval_expr(args[1], env, output)
    elif len(args) == 3:
        return eval_expr(args[2], env, output)
    else:
        return UNSPECIFIED

def handle_define(expr, env, output):
    rest = expr.cdr
    if not isinstance(rest, Pair):
        raise SchemeError("malformed define")
    target = rest.car
    if isinstance(target, Symbol):
        expr_part = rest.cdr
        if not isinstance(expr_part, Pair):
            raise SchemeError("malformed define")
        value = eval_non_tail(expr_part.car, env, output)
        env.vars[target.name] = value
        return UNSPECIFIED
    elif isinstance(target, Pair):
        name = target.car
        if not isinstance(name, Symbol):
            raise SchemeError("malformed define")
        formals = target.cdr
        body = to_list(rest.cdr)
        if not body:
            raise SchemeError("define body must be non-empty")
        closure = Closure(formals, body, env)
        env.vars[name.name] = closure
        return UNSPECIFIED
    else:
        raise SchemeError("malformed define")

def handle_set(expr, env, output):
    rest = expr.cdr
    if not isinstance(rest, Pair):
        raise SchemeError("malformed set!")
    target = rest.car
    if not isinstance(target, Symbol):
        raise SchemeError("set! expects a symbol")
    expr_part = rest.cdr
    if not isinstance(expr_part, Pair):
        raise SchemeError("malformed set!")
    value = eval_non_tail(expr_part.car, env, output)
    set_var(target.name, value, env)
    return UNSPECIFIED

def handle_begin(expr, env, output):
    body = to_list(expr.cdr)
    if not body:
        raise SchemeError("malformed begin")
    for form in body[:-1]:
        eval_non_tail(form, env, output)
    return eval_expr(body[-1], env, output)

def handle_cond(expr, env, output):
    clauses = to_list(expr.cdr)
    for i, clause in enumerate(clauses):
        if not isinstance(clause, Pair):
            raise SchemeError("malformed cond clause")
        test = clause.car
        body = to_list(clause.cdr)
        if isinstance(test, Symbol) and test.name == 'else':
            if i != len(clauses) - 1:
                raise SchemeError("else must be last clause")
            if not body:
                return UNSPECIFIED
            for form in body[:-1]:
                eval_non_tail(form, env, output)
            return eval_expr(body[-1], env, output)
        test_val = eval_non_tail(test, env, output)
        if is_true(test_val):
            if not body:
                return test_val
            for form in body[:-1]:
                eval_non_tail(form, env, output)
            return eval_expr(body[-1], env, output)
    return UNSPECIFIED

def handle_and(expr, env, output):
    args = to_list(expr.cdr)
    if not args:
        return True
    for form in args[:-1]:
        val = eval_non_tail(form, env, output)
        if not is_true(val):
            return False
    return eval_expr(args[-1], env, output)

def handle_or(expr, env, output):
    args = to_list(expr.cdr)
    if not args:
        return False
    for form in args[:-1]:
        val = eval_non_tail(form, env, output)
        if is_true(val):
            return val
    return eval_expr(args[-1], env, output)

def handle_lambda(expr, env):
    rest = expr.cdr
    if not isinstance(rest, Pair):
        raise SchemeError("malformed lambda")
    formals = rest.car
    body = to_list(rest.cdr)
    if not body:
        raise SchemeError("lambda body must be non-empty")
    return Closure(formals, body, env)

def handle_let(expr, env, output):
    rest = expr.cdr
    if not isinstance(rest, Pair):
        raise SchemeError("malformed let")
    first = rest.car
    if isinstance(first, Symbol):
        # Named let
        name = first
        bindings_expr = rest.cdr
        if not isinstance(bindings_expr, Pair):
            raise SchemeError("malformed named let")
        bindings = to_list(bindings_expr.car)
        body = to_list(bindings_expr.cdr)
        if not body:
            raise SchemeError("named let body must be non-empty")
        inits = []
        for b in bindings:
            if not isinstance(b, Pair):
                raise SchemeError("malformed let binding")
            var = b.car
            if not isinstance(var, Symbol):
                raise SchemeError("let binding variable must be a symbol")
            init = b.cdr
            if not isinstance(init, Pair):
                raise SchemeError("malformed let binding")
            inits.append((var, eval_non_tail(init.car, env, output)))
        new_frame = Frame(env)
        new_frame.vars[name.name] = UNBOUND
        formals = list_to_scheme([b[0] for b in inits])
        closure = Closure(formals, body, new_frame)
        new_frame.vars[name.name] = closure
        args = [val for _, val in inits]
        return TailCall(closure, args)
    else:
        # Regular let
        bindings = to_list(first)
        body = to_list(rest.cdr)
        if not body:
            raise SchemeError("let body must be non-empty")
        inits = []
        for b in bindings:
            if not isinstance(b, Pair):
                raise SchemeError("malformed let binding")
            var = b.car
            if not isinstance(var, Symbol):
                raise SchemeError("let binding variable must be a symbol")
            init = b.cdr
            if not isinstance(init, Pair):
                raise SchemeError("malformed let binding")
            inits.append((var, eval_non_tail(init.car, env, output)))
        new_frame = Frame(env)
        for var, val in inits:
            new_frame.vars[var.name] = val
        return eval_body(body, new_frame, output)

def handle_letstar(expr, env, output):
    rest = expr.cdr
    if not isinstance(rest, Pair):
        raise SchemeError("malformed let*")
    bindings = to_list(rest.car)
    body = to_list(rest.cdr)
    if not body:
        raise SchemeError("let* body must be non-empty")
    new_frame = Frame(env)
    for b in bindings:
        if not isinstance(b, Pair):
            raise SchemeError("malformed let* binding")
        var = b.car
        if not isinstance(var, Symbol):
            raise SchemeError("let* binding variable must be a symbol")
        init = b.cdr
        if not isinstance(init, Pair):
            raise SchemeError("malformed let* binding")
        val = eval_non_tail(init.car, new_frame, output)
        new_frame.vars[var.name] = val
    return eval_body(body, new_frame, output)

def handle_letrec(expr, env, output):
    rest = expr.cdr
    if not isinstance(rest, Pair):
        raise SchemeError("malformed letrec")
    bindings = to_list(rest.car)
    body = to_list(rest.cdr)
    if not body:
        raise SchemeError("letrec body must be non-empty")
    new_frame = Frame(env)
    for b in bindings:
        if not isinstance(b, Pair):
            raise SchemeError("malformed letrec binding")
        var = b.car
        if not isinstance(var, Symbol):
            raise SchemeError("letrec binding variable must be a symbol")
        new_frame.vars[var.name] = UNBOUND
    for b in bindings:
        var = b.car
        init = b.cdr
        if not isinstance(init, Pair):
            raise SchemeError("malformed letrec binding")
        val = eval_non_tail(init.car, new_frame, output)
        new_frame.vars[var.name] = val
    return eval_body(body, new_frame, output)

def handle_apply(expr, env, output):
    args = to_list(expr.cdr)
    if len(args) < 2:
        raise SchemeError("apply: too few arguments")
    f = eval_non_tail(args[0], env, output)
    mid_args = [eval_non_tail(a, env, output) for a in args[1:-1]]
    lst = eval_non_tail(args[-1], env, output)
    if not isinstance(f, (Closure, Builtin)):
        raise SchemeError("apply: not a procedure")
    elements = []
    current = lst
    while isinstance(current, Pair):
        elements.append(current.car)
        current = current.cdr
    if not isinstance(current, Nil):
        raise SchemeError("apply: last argument is not a proper list")
    full_args = mid_args + elements
    return TailCall(f, full_args)

def handle_application(expr, env, output):
    operator = eval_non_tail(expr.car, env, output)
    args = []
    current = expr.cdr
    while isinstance(current, Pair):
        args.append(eval_non_tail(current.car, env, output))
        current = current.cdr
    if not isinstance(current, Nil):
        raise SchemeError("dotted form used as application")
    if not isinstance(operator, (Closure, Builtin)):
        raise SchemeError("not a procedure")
    return TailCall(operator, args)


def scan_internal_defines(body):
    names = []
    for form in body:
        if isinstance(form, Pair) and isinstance(form.car, Symbol) and form.car.name == 'define':
            rest = form.cdr
            if isinstance(rest, Pair):
                target = rest.car
                if isinstance(target, Symbol):
                    names.append(target.name)
                elif isinstance(target, Pair):
                    nm = target.car
                    if isinstance(nm, Symbol):
                        names.append(nm.name)
    return names

def eval_body(body, env, output):
    define_names = scan_internal_defines(body)
    for name in define_names:
        env.vars[name] = UNBOUND
    for i, form in enumerate(body):
        if i == len(body) - 1:
            return eval_expr(form, env, output)
        else:
            eval_non_tail(form, env, output)


def apply_proc(proc, args, output):
    if isinstance(proc, Builtin):
        if len(args) < proc.min_args:
            raise SchemeError(proc.name + ": too few arguments")
        if proc.max_args is not None and len(args) > proc.max_args:
            raise SchemeError(proc.name + ": too many arguments")
        return proc.func(args, output)
    elif isinstance(proc, Closure):
        new_frame = Frame(proc.env)
        bind_formals(proc.formals, args, new_frame)
        return eval_body(proc.body, new_frame, output)
    else:
        raise SchemeError("not a procedure")

def bind_formals(formals, args, frame):
    if isinstance(formals, Symbol):
        frame.vars[formals.name] = list_to_scheme(args)
    elif isinstance(formals, Nil):
        if args:
            raise SchemeError("too many arguments")
    elif isinstance(formals, Pair):
        fixed = []
        rest = None
        current = formals
        while isinstance(current, Pair):
            fixed.append(current.car)
            current = current.cdr
        if isinstance(current, Symbol):
            rest = current
        elif not isinstance(current, Nil):
            raise SchemeError("bad formals")
        if rest is None:
            if len(args) != len(fixed):
                raise SchemeError("wrong number of arguments")
            for sym, arg in zip(fixed, args):
                if not isinstance(sym, Symbol):
                    raise SchemeError("formal must be a symbol")
                frame.vars[sym.name] = arg
        else:
            if len(args) < len(fixed):
                raise SchemeError("too few arguments")
            for sym, arg in zip(fixed, args):
                if not isinstance(sym, Symbol):
                    raise SchemeError("formal must be a symbol")
                frame.vars[sym.name] = arg
            frame.vars[rest.name] = list_to_scheme(args[len(fixed):])
    else:
        raise SchemeError("bad formals")


# ─── Builtins ─────────────────────────────────────────────────────────────────

def check_int(x, name):
    if type(x) is not int:
        raise SchemeError(name + ": expected integer")

def int_to_radix(n, radix):
    if n == 0:
        return '0'
    digits = []
    while n > 0:
        digits.append('0123456789abcdef'[n % radix])
        n //= radix
    return ''.join(reversed(digits))

def b_add(args, output):
    result = 0
    for a in args:
        check_int(a, '+')
        result += a
    return result

def b_mul(args, output):
    result = 1
    for a in args:
        check_int(a, '*')
        result *= a
    return result

def b_sub(args, output):
    check_int(args[0], '-')
    if len(args) == 1:
        return -args[0]
    result = args[0]
    for a in args[1:]:
        check_int(a, '-')
        result -= a
    return result

def b_quotient(args, output):
    check_int(args[0], 'quotient')
    check_int(args[1], 'quotient')
    if args[1] == 0:
        raise SchemeError("quotient: division by zero")
    q = abs(args[0]) // abs(args[1])
    if (args[0] < 0) != (args[1] < 0):
        q = -q
    return q

def b_remainder(args, output):
    check_int(args[0], 'remainder')
    check_int(args[1], 'remainder')
    if args[1] == 0:
        raise SchemeError("remainder: division by zero")
    q = abs(args[0]) // abs(args[1])
    if (args[0] < 0) != (args[1] < 0):
        q = -q
    return args[0] - q * args[1]

def b_modulo(args, output):
    check_int(args[0], 'modulo')
    check_int(args[1], 'modulo')
    if args[1] == 0:
        raise SchemeError("modulo: division by zero")
    return args[0] % args[1]

def b_num_eq(args, output):
    for a in args:
        check_int(a, '=')
    for i in range(len(args) - 1):
        if args[i] != args[i + 1]:
            return False
    return True

def b_num_lt(args, output):
    for a in args:
        check_int(a, '<')
    for i in range(len(args) - 1):
        if not (args[i] < args[i + 1]):
            return False
    return True

def b_num_gt(args, output):
    for a in args:
        check_int(a, '>')
    for i in range(len(args) - 1):
        if not (args[i] > args[i + 1]):
            return False
    return True

def b_num_le(args, output):
    for a in args:
        check_int(a, '<=')
    for i in range(len(args) - 1):
        if not (args[i] <= args[i + 1]):
            return False
    return True

def b_num_ge(args, output):
    for a in args:
        check_int(a, '>=')
    for i in range(len(args) - 1):
        if not (args[i] >= args[i + 1]):
            return False
    return True

def b_num_to_str(args, output):
    n = args[0]
    check_int(n, 'number->string')
    if len(args) == 1:
        return str(n)
    radix = args[1]
    check_int(radix, 'number->string')
    if radix not in (2, 8, 10, 16):
        raise SchemeError("number->string: invalid radix")
    if n < 0:
        return '-' + int_to_radix(-n, radix)
    return int_to_radix(n, radix)

def b_cons(args, output):
    return Pair(args[0], args[1])

def b_car(args, output):
    p = args[0]
    if not isinstance(p, Pair):
        raise SchemeError("car: not a pair")
    return p.car

def b_cdr(args, output):
    p = args[0]
    if not isinstance(p, Pair):
        raise SchemeError("cdr: not a pair")
    return p.cdr

def b_list(args, output):
    return list_to_scheme(args)

def b_null(args, output):
    return isinstance(args[0], Nil)

def b_pair(args, output):
    return isinstance(args[0], Pair)

def b_listp(args, output):
    return is_proper(args[0])

def b_length(args, output):
    count = 0
    current = args[0]
    while isinstance(current, Pair):
        count += 1
        current = current.cdr
    if not isinstance(current, Nil):
        raise SchemeError("length: not a proper list")
    return count

def b_append(args, output):
    if not args:
        return NIL
    result = args[-1]
    for lst in reversed(args[:-1]):
        if not is_proper(lst):
            raise SchemeError("append: not a proper list")
        elements = []
        current = lst
        while isinstance(current, Pair):
            elements.append(current.car)
            current = current.cdr
        for elem in reversed(elements):
            result = Pair(elem, result)
    return result

def b_reverse(args, output):
    result = NIL
    current = args[0]
    while isinstance(current, Pair):
        result = Pair(current.car, result)
        current = current.cdr
    if not isinstance(current, Nil):
        raise SchemeError("reverse: not a proper list")
    return result

def scheme_eq(a, b):
    if type(a) is int and type(b) is int:
        return a == b
    if type(a) is bool and type(b) is bool:
        return a is b
    if isinstance(a, Symbol) and isinstance(b, Symbol):
        return a is b
    if isinstance(a, Nil) and isinstance(b, Nil):
        return True
    return a is b

def b_eq(args, output):
    return scheme_eq(args[0], args[1])

def scheme_equal(a, b):
    stack = [(a, b)]
    while stack:
        a, b = stack.pop()
        if a is b:
            continue
        if type(a) is int and type(b) is int:
            if a != b:
                return False
        elif type(a) is bool and type(b) is bool:
            if a is not b:
                return False
        elif isinstance(a, str) and isinstance(b, str):
            if a != b:
                return False
        elif isinstance(a, Symbol) and isinstance(b, Symbol):
            if a is not b:
                return False
        elif isinstance(a, Nil) and isinstance(b, Nil):
            pass
        elif isinstance(a, Pair) and isinstance(b, Pair):
            stack.append((a.car, b.car))
            stack.append((a.cdr, b.cdr))
        else:
            return False
    return True

def b_equal(args, output):
    return scheme_equal(args[0], args[1])

def b_not(args, output):
    return args[0] is False

def b_number(args, output):
    return type(args[0]) is int

def b_symbol(args, output):
    return isinstance(args[0], Symbol)

def b_string(args, output):
    return type(args[0]) is str

def b_procedure(args, output):
    return isinstance(args[0], (Closure, Builtin))

def b_str_append(args, output):
    for s in args:
        if type(s) is not str:
            raise SchemeError("string-append: expected string")
    return ''.join(args)

def b_display(args, output):
    output.append(display_repr(args[0]))
    return UNSPECIFIED

def b_newline(args, output):
    output.append('\n')
    return UNSPECIFIED

def b_error(args, output):
    msg = args[0]
    if not isinstance(msg, str):
        raise SchemeError("error: message must be a string")
    full_msg = msg
    for irritant in args[1:]:
        full_msg += ' ' + write_repr(irritant)
    raise SchemeError(full_msg)


def make_global_env():
    env = Frame()

    def add(name, func, min_args, max_args=None):
        env.vars[name] = Builtin(name, func, min_args, max_args)

    add('+', b_add, 0)
    add('*', b_mul, 0)
    add('-', b_sub, 1)
    add('quotient', b_quotient, 2, 2)
    add('remainder', b_remainder, 2, 2)
    add('modulo', b_modulo, 2, 2)
    add('=', b_num_eq, 1)
    add('<', b_num_lt, 1)
    add('>', b_num_gt, 1)
    add('<=', b_num_le, 1)
    add('>=', b_num_ge, 1)
    add('number->string', b_num_to_str, 1, 2)

    add('cons', b_cons, 2, 2)
    add('car', b_car, 1, 1)
    add('cdr', b_cdr, 1, 1)
    add('list', b_list, 0)
    add('null?', b_null, 1, 1)
    add('pair?', b_pair, 1, 1)
    add('list?', b_listp, 1, 1)
    add('length', b_length, 1, 1)
    add('append', b_append, 0)
    add('reverse', b_reverse, 1, 1)

    add('eq?', b_eq, 2, 2)
    add('equal?', b_equal, 2, 2)
    add('not', b_not, 1, 1)
    add('number?', b_number, 1, 1)
    add('symbol?', b_symbol, 1, 1)
    add('string?', b_string, 1, 1)
    add('procedure?', b_procedure, 1, 1)
    add('string-append', b_str_append, 0)

    add('display', b_display, 1, 1)
    add('newline', b_newline, 0, 0)
    add('error', b_error, 1)

    return env


# ─── Public API ───────────────────────────────────────────────────────────────

def run(source: str) -> str:
    output = []
    try:
        tokens = tokenize(source)
        forms = parse(tokens)
        global_env = make_global_env()
        for form in forms:
            eval_non_tail(form, global_env, output)
    except SchemeError as e:
        e.output = ''.join(output)
        raise
    except RecursionError:
        raise SchemeError("stack overflow", ''.join(output))
    except Exception as e:
        raise SchemeError(str(e), ''.join(output))
    return ''.join(output)
