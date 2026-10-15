import sys
import re

try:
    sys.set_int_max_str_digits(0)
except (AttributeError, ValueError):
    pass

# ─── Data Types ───────────────────────────────────────────────────────────────

class SchemeError(Exception):
    def __init__(self, msg='', output=''):
        super().__init__(msg)
        self.output = output

class Symbol:
    __slots__ = ('name',)
    _interned = {}
    def __new__(cls, name):
        if name in cls._interned:
            return cls._interned[name]
        obj = super().__new__(cls)
        obj.name = name
        cls._interned[name] = obj
        return obj
    def __repr__(self):
        return f"Symbol({self.name!r})"

class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr

class _Nil:
    _instance = None
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    def __repr__(self):
        return "()"

NIL = _Nil()

class _Unspecified:
    _instance = None
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    def __repr__(self):
        return "#<unspecified>"

UNSPECIFIED = _Unspecified()

class _Uninitialized:
    _instance = None
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

UNINITIALIZED = _Uninitialized()

class Box:
    __slots__ = ('value',)
    def __init__(self, value):
        self.value = value

class Closure:
    __slots__ = ('formals', 'body', 'env')
    def __init__(self, formals, body, env):
        self.formals = formals
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

# ─── Environment ──────────────────────────────────────────────────────────────

class Env:
    __slots__ = ('vars', 'parent')
    def __init__(self, parent=None):
        self.vars = {}
        self.parent = parent

    def lookup(self, name):
        env = self
        while env is not None:
            if name in env.vars:
                box = env.vars[name]
                if box.value is UNINITIALIZED:
                    raise SchemeError(f"uninitialized variable: {name.name}")
                return box.value
            env = env.parent
        raise SchemeError(f"unbound variable: {name.name}")

    def define(self, name, box):
        self.vars[name] = box

    def set(self, name, value):
        env = self
        while env is not None:
            if name in env.vars:
                env.vars[name].value = value
                return
            env = env.parent
        raise SchemeError(f"unbound variable: {name.name}")

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
            tokens.append(('(', None))
            i += 1
        elif c == ')':
            tokens.append((')', None))
            i += 1
        elif c == "'":
            tokens.append(("'", None))
            i += 1
        elif c == '"':
            i += 1
            parts = []
            while i < n and source[i] != '"':
                if source[i] == '\\':
                    i += 1
                    if i >= n:
                        raise SchemeError("unterminated string escape")
                    ec = source[i]
                    if ec == '"':
                        parts.append('"')
                    elif ec == '\\':
                        parts.append('\\')
                    elif ec == 'n':
                        parts.append('\n')
                    else:
                        raise SchemeError(f"invalid escape: \\{ec}")
                    i += 1
                else:
                    parts.append(source[i])
                    i += 1
            if i >= n:
                raise SchemeError("unterminated string")
            i += 1  # skip closing "
            tokens.append(('string', ''.join(parts)))
        else:
            j = i
            while j < n and source[j] not in ' \t\n\r()";\'':
                j += 1
            tok = source[i:j]
            i = j
            if _INT_RE.match(tok):
                tokens.append(('int', int(tok)))
            elif tok == '#t':
                tokens.append(('bool', True))
            elif tok == '#f':
                tokens.append(('bool', False))
            elif tok.startswith('#'):
                raise SchemeError(f"syntax error: {tok}")
            elif tok == '.':
                tokens.append(('dot', None))
            else:
                tokens.append(('symbol', tok))
    return tokens

def _parse_all(tokens):
    pos = [0]

    def peek():
        if pos[0] < len(tokens):
            return tokens[pos[0]]
        return None

    def advance():
        t = tokens[pos[0]]
        pos[0] += 1
        return t

    def parse_datum():
        t = peek()
        if t is None:
            raise SchemeError("unexpected end of input")
        if t[0] == '(':
            advance()
            return parse_list()
        if t[0] == ')':
            raise SchemeError("unexpected )")
        if t[0] == "'":
            advance()
            datum = parse_datum()
            return Pair(Symbol('quote'), Pair(datum, NIL))
        if t[0] == 'int':
            advance()
            return t[1]
        if t[0] == 'bool':
            advance()
            return t[1]
        if t[0] == 'string':
            advance()
            return t[1]
        if t[0] == 'symbol':
            advance()
            return Symbol(t[1])
        if t[0] == 'dot':
            raise SchemeError("unexpected .")
        raise SchemeError("unexpected token")

    def parse_list():
        elements = []
        while True:
            t = peek()
            if t is None:
                raise SchemeError("unbalanced (")
            if t[0] == ')':
                advance()
                result = NIL
                for e in reversed(elements):
                    result = Pair(e, result)
                return result
            if t[0] == 'dot':
                advance()
                if len(elements) == 0:
                    raise SchemeError("dot must be preceded by at least one element")
                rest = parse_datum()
                t2 = peek()
                if t2 is None or t2[0] != ')':
                    raise SchemeError("dot must be followed by one datum and )")
                advance()
                result = rest
                for e in reversed(elements):
                    result = Pair(e, result)
                return result
            elements.append(parse_datum())

    forms = []
    while pos[0] < len(tokens):
        forms.append(parse_datum())
    return forms

def read_all(source):
    tokens = _tokenize(source)
    return _parse_all(tokens)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def is_integer(x):
    return isinstance(x, int) and not isinstance(x, bool)

def to_list(scheme_list):
    result = []
    cur = scheme_list
    while isinstance(cur, Pair):
        result.append(cur.car)
        cur = cur.cdr
    if cur is not NIL:
        raise SchemeError("not a proper list")
    return result

def from_list(lst):
    result = NIL
    for item in reversed(lst):
        result = Pair(item, result)
    return result

def is_proper_list(x):
    while isinstance(x, Pair):
        x = x.cdr
    return x is NIL

def cdr_list(pair):
    """Get elements of a proper list as Python list (no error check)."""
    result = []
    cur = pair
    while isinstance(cur, Pair):
        result.append(cur.car)
        cur = cur.cdr
    return result

# ─── Display ──────────────────────────────────────────────────────────────────

def _display_repr(x, write_mode):
    if isinstance(x, bool):
        return '#t' if x else '#f'
    if isinstance(x, int):
        return str(x)
    if isinstance(x, str):
        if write_mode:
            return _escape_str(x)
        return x
    if isinstance(x, Symbol):
        return x.name
    if x is NIL:
        return '()'
    if isinstance(x, Pair):
        parts = ['(']
        first = True
        cur = x
        while True:
            if not first:
                parts.append(' ')
            first = False
            if isinstance(cur, Pair):
                parts.append(_display_repr(cur.car, write_mode))
                cur = cur.cdr
            else:
                if cur is not NIL:
                    parts.append('. ')
                    parts.append(_display_repr(cur, write_mode))
                break
        parts.append(')')
        return ''.join(parts)
    if isinstance(x, (Closure, Builtin)):
        return '#<procedure>'
    if x is UNSPECIFIED:
        return ''
    return str(x)

def _escape_str(s):
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

# ─── Evaluator ────────────────────────────────────────────────────────────────

def force(result):
    while isinstance(result, TailCall):
        result = _apply(result.proc, result.args)
    return result

def _apply(proc, args):
    if isinstance(proc, Builtin):
        return proc.func(args)
    if isinstance(proc, Closure):
        return _call_closure(proc, args)
    raise SchemeError("not a procedure")

def _call_closure(closure, args):
    env = Env(closure.env)
    formals = closure.formals
    if isinstance(formals, Symbol):
        env.define(formals, Box(from_list(args)))
    elif formals is NIL:
        if args:
            raise SchemeError("too many arguments")
    elif isinstance(formals, Pair):
        params = []
        rest = None
        f = formals
        while isinstance(f, Pair):
            params.append(f.car)
            f = f.cdr
        if f is not NIL:
            if not isinstance(f, Symbol):
                raise SchemeError("malformed lambda formals")
            rest = f
        if rest is None:
            if len(args) != len(params):
                raise SchemeError("wrong number of arguments")
        else:
            if len(args) < len(params):
                raise SchemeError("too few arguments")
        for p, a in zip(params, args):
            if not isinstance(p, Symbol):
                raise SchemeError("malformed lambda formals")
            env.define(p, Box(a))
        if rest is not None:
            env.define(rest, Box(from_list(args[len(params):])))
    else:
        raise SchemeError("malformed lambda formals")
    return _eval_body(closure.body, env)

def _eval_body(body, env):
    if not body:
        raise SchemeError("empty body")
    # Collect internal define names
    define_names = []
    for form in body:
        if _is_define_form(form):
            define_names.append(_define_name(form))
    # Pre-bind
    for name in define_names:
        env.define(name, Box(UNINITIALIZED))
    # Evaluate forms
    for i, form in enumerate(body):
        is_last = (i == len(body) - 1)
        if is_last and not _is_define_form(form):
            return _eval(form, env)
        else:
            force(_eval(form, env))
    return UNSPECIFIED

def _is_define_form(form):
    return (isinstance(form, Pair) and isinstance(form.car, Symbol)
            and form.car.name == 'define')

def _define_name(form):
    target = form.cdr.car
    if isinstance(target, Symbol):
        return target
    if isinstance(target, Pair):
        return target.car
    raise SchemeError("malformed define")

def _eval(expr, env):
    # Self-evaluating
    if isinstance(expr, bool):
        return expr
    if isinstance(expr, int):
        return expr
    if isinstance(expr, str):
        return expr
    if isinstance(expr, Symbol):
        return env.lookup(expr)
    if expr is NIL:
        raise SchemeError("cannot evaluate ()")
    if expr is UNSPECIFIED or expr is UNINITIALIZED:
        raise SchemeError("cannot evaluate this")

    if not isinstance(expr, Pair):
        raise SchemeError("cannot evaluate")

    head = expr.car

    if isinstance(head, Symbol):
        nm = head.name
        if nm == 'quote':
            return _eval_quote(expr, env)
        if nm == 'if':
            return _eval_if(expr, env)
        if nm == 'lambda':
            return _eval_lambda(expr, env)
        if nm == 'define':
            return _eval_define(expr, env)
        if nm == 'set!':
            return _eval_set(expr, env)
        if nm == 'begin':
            return _eval_begin(expr, env)
        if nm == 'cond':
            return _eval_cond(expr, env)
        if nm == 'and':
            return _eval_and(expr, env)
        if nm == 'or':
            return _eval_or(expr, env)
        if nm == 'let':
            return _eval_let(expr, env)
        if nm == 'let*':
            return _eval_letstar(expr, env)
        if nm == 'letrec':
            return _eval_letrec(expr, env)
        if nm == 'apply':
            return _eval_apply(expr, env)

    # Application
    proc = force(_eval(head, env))
    args = []
    cur = expr.cdr
    while cur is not NIL:
        if not isinstance(cur, Pair):
            raise SchemeError("dotted form in application")
        args.append(force(_eval(cur.car, env)))
        cur = cur.cdr
    if not isinstance(proc, (Closure, Builtin)):
        raise SchemeError("not a procedure")
    return _apply(proc, args)

def _eval_quote(expr, env):
    rest = expr.cdr
    if rest is NIL or not isinstance(rest, Pair) or rest.cdr is not NIL:
        raise SchemeError("malformed quote")
    return rest.car

def _eval_if(expr, env):
    rest = to_list(expr.cdr)
    if len(rest) < 2 or len(rest) > 3:
        raise SchemeError("malformed if")
    test = force(_eval(rest[0], env))
    if test is False:
        if len(rest) == 3:
            return _eval(rest[2], env)
        return UNSPECIFIED
    return _eval(rest[1], env)

def _eval_lambda(expr, env):
    rest = expr.cdr
    if rest is NIL or not isinstance(rest, Pair):
        raise SchemeError("malformed lambda")
    formals = rest.car
    body_forms = rest.cdr
    if body_forms is NIL:
        raise SchemeError("empty body")
    if not is_proper_list(body_forms):
        raise SchemeError("malformed lambda body")
    body = to_list(body_forms)
    return Closure(formals, body, env)

def _eval_define(expr, env):
    rest = expr.cdr
    if rest is NIL or not isinstance(rest, Pair):
        raise SchemeError("malformed define")
    target = rest.car
    if isinstance(target, Symbol):
        val_rest = rest.cdr
        if val_rest is NIL or not isinstance(val_rest, Pair):
            raise SchemeError("malformed define")
        if val_rest.cdr is not NIL:
            raise SchemeError("malformed define")
        val = force(_eval(val_rest.car, env))
        env.define(target, Box(val))
    elif isinstance(target, Pair):
        name = target.car
        if not isinstance(name, Symbol):
            raise SchemeError("malformed define")
        formals = target.cdr
        body_forms = rest.cdr
        if body_forms is NIL:
            raise SchemeError("empty body")
        if not is_proper_list(body_forms):
            raise SchemeError("malformed define")
        body = to_list(body_forms)
        closure = Closure(formals, body, env)
        env.define(name, Box(closure))
    else:
        raise SchemeError("malformed define")
    return UNSPECIFIED

def _eval_set(expr, env):
    rest = expr.cdr
    if rest is NIL or not isinstance(rest, Pair):
        raise SchemeError("malformed set!")
    name = rest.car
    if not isinstance(name, Symbol):
        raise SchemeError("malformed set!")
    val_rest = rest.cdr
    if val_rest is NIL or not isinstance(val_rest, Pair):
        raise SchemeError("malformed set!")
    if val_rest.cdr is not NIL:
        raise SchemeError("malformed set!")
    val = force(_eval(val_rest.car, env))
    env.set(name, val)
    return UNSPECIFIED

def _eval_begin(expr, env):
    forms = to_list(expr.cdr)
    if not forms:
        raise SchemeError("empty begin")
    for f in forms[:-1]:
        force(_eval(f, env))
    return _eval(forms[-1], env)

def _eval_cond(expr, env):
    clauses = to_list(expr.cdr)
    if not clauses:
        raise SchemeError("malformed cond")
    for i, clause in enumerate(clauses):
        if not isinstance(clause, Pair):
            raise SchemeError("malformed cond clause")
        parts = to_list(clause)
        if not parts:
            raise SchemeError("malformed cond clause")
        test = parts[0]
        exprs = parts[1:]
        is_else = isinstance(test, Symbol) and test.name == 'else'
        if is_else:
            if i != len(clauses) - 1:
                raise SchemeError("else not last in cond")
            if not exprs:
                raise SchemeError("malformed else clause")
            for e in exprs[:-1]:
                force(_eval(e, env))
            return _eval(exprs[-1], env)
        else:
            val = force(_eval(test, env))
            if val is not False:
                if not exprs:
                    return val
                for e in exprs[:-1]:
                    force(_eval(e, env))
                return _eval(exprs[-1], env)
    return UNSPECIFIED

def _eval_and(expr, env):
    forms = to_list(expr.cdr)
    if not forms:
        return True
    for f in forms[:-1]:
        val = force(_eval(f, env))
        if val is False:
            return False
    return _eval(forms[-1], env)

def _eval_or(expr, env):
    forms = to_list(expr.cdr)
    if not forms:
        return False
    for f in forms[:-1]:
        val = force(_eval(f, env))
        if val is not False:
            return val
    return _eval(forms[-1], env)

def _eval_let(expr, env):
    rest = expr.cdr
    if rest is NIL or not isinstance(rest, Pair):
        raise SchemeError("malformed let")
    bindings_or_name = rest.car
    if isinstance(bindings_or_name, Symbol):
        return _eval_named_let(expr, env)
    # Regular let
    bindings = to_list(bindings_or_name)
    body_forms = rest.cdr
    if body_forms is NIL:
        raise SchemeError("empty body")
    if not is_proper_list(body_forms):
        raise SchemeError("malformed let body")
    body = to_list(body_forms)
    # Evaluate inits in outer env
    inits = []
    names = []
    for b in bindings:
        if not isinstance(b, Pair):
            raise SchemeError("malformed let binding")
        v = b.car
        if not isinstance(v, Symbol):
            raise SchemeError("malformed let binding")
        init_rest = b.cdr
        if init_rest is NIL or not isinstance(init_rest, Pair):
            raise SchemeError("malformed let binding")
        if init_rest.cdr is not NIL:
            raise SchemeError("malformed let binding")
        names.append(v)
        inits.append(force(_eval(init_rest.car, env)))
    new_env = Env(env)
    for v, val in zip(names, inits):
        new_env.define(v, Box(val))
    return _eval_body(body, new_env)

def _eval_named_let(expr, env):
    rest = expr.cdr
    name = rest.car  # Symbol
    bindings_form = rest.cdr.car
    bindings = to_list(bindings_form)
    body_forms = rest.cdr.cdr
    if body_forms is NIL:
        raise SchemeError("empty body")
    if not is_proper_list(body_forms):
        raise SchemeError("malformed let body")
    body = to_list(body_forms)
    # Evaluate inits in outer env
    inits = []
    params = []
    for b in bindings:
        if not isinstance(b, Pair):
            raise SchemeError("malformed let binding")
        v = b.car
        if not isinstance(v, Symbol):
            raise SchemeError("malformed let binding")
        init_rest = b.cdr
        if init_rest is NIL or not isinstance(init_rest, Pair):
            raise SchemeError("malformed let binding")
        if init_rest.cdr is not NIL:
            raise SchemeError("malformed let binding")
        params.append(v)
        inits.append(force(_eval(init_rest.car, env)))
    # Create env
    new_env = Env(env)
    new_env.define(name, Box(UNINITIALIZED))
    formals = from_list(params)
    closure = Closure(formals, body, new_env)
    new_env.set(name, closure)
    return _apply(closure, inits)

def _eval_letstar(expr, env):
    rest = expr.cdr
    if rest is NIL or not isinstance(rest, Pair):
        raise SchemeError("malformed let*")
    bindings = to_list(rest.car)
    body_forms = rest.cdr
    if body_forms is NIL:
        raise SchemeError("empty body")
    if not is_proper_list(body_forms):
        raise SchemeError("malformed let* body")
    body = to_list(body_forms)
    cur_env = env
    for b in bindings:
        if not isinstance(b, Pair):
            raise SchemeError("malformed let* binding")
        v = b.car
        if not isinstance(v, Symbol):
            raise SchemeError("malformed let* binding")
        init_rest = b.cdr
        if init_rest is NIL or not isinstance(init_rest, Pair):
            raise SchemeError("malformed let* binding")
        if init_rest.cdr is not NIL:
            raise SchemeError("malformed let* binding")
        val = force(_eval(init_rest.car, cur_env))
        new_env = Env(cur_env)
        new_env.define(v, Box(val))
        cur_env = new_env
    return _eval_body(body, cur_env)

def _eval_letrec(expr, env):
    rest = expr.cdr
    if rest is NIL or not isinstance(rest, Pair):
        raise SchemeError("malformed letrec")
    bindings = to_list(rest.car)
    body_forms = rest.cdr
    if body_forms is NIL:
        raise SchemeError("empty body")
    if not is_proper_list(body_forms):
        raise SchemeError("malformed letrec body")
    body = to_list(body_forms)
    new_env = Env(env)
    names = []
    inits = []
    for b in bindings:
        if not isinstance(b, Pair):
            raise SchemeError("malformed letrec binding")
        v = b.car
        if not isinstance(v, Symbol):
            raise SchemeError("malformed letrec binding")
        init_rest = b.cdr
        if init_rest is NIL or not isinstance(init_rest, Pair):
            raise SchemeError("malformed letrec binding")
        if init_rest.cdr is not NIL:
            raise SchemeError("malformed letrec binding")
        names.append(v)
        inits.append(init_rest.car)
        new_env.define(v, Box(UNINITIALIZED))
    for v, init in zip(names, inits):
        val = force(_eval(init, new_env))
        new_env.set(v, val)
    return _eval_body(body, new_env)

def _eval_apply(expr, env):
    args_forms = to_list(expr.cdr)
    if len(args_forms) < 2:
        raise SchemeError("apply: requires at least 2 arguments")
    proc = force(_eval(args_forms[0], env))
    fixed = []
    for af in args_forms[1:-1]:
        fixed.append(force(_eval(af, env)))
    last = force(_eval(args_forms[-1], env))
    if not is_proper_list(last):
        raise SchemeError("apply: last argument must be a proper list")
    all_args = fixed + to_list(last)
    if not isinstance(proc, (Closure, Builtin)):
        raise SchemeError("apply: not a procedure")
    return _apply(proc, all_args)

# ─── Builtins ─────────────────────────────────────────────────────────────────

def _make_global_env(output):
    env = Env()

    def _define(name, func):
        env.define(Symbol(name), Box(Builtin(func, name)))

    # ── Numbers ──
    def _plus(args):
        for a in args:
            if not is_integer(a):
                raise SchemeError("+: requires numbers")
        r = 0
        for a in args:
            r += a
        return r

    def _times(args):
        for a in args:
            if not is_integer(a):
                raise SchemeError("*: requires numbers")
        r = 1
        for a in args:
            r *= a
        return r

    def _minus(args):
        for a in args:
            if not is_integer(a):
                raise SchemeError("-: requires numbers")
        if len(args) == 1:
            return -args[0]
        r = args[0]
        for a in args[1:]:
            r -= a
        return r

    def _quotient(args):
        if len(args) != 2:
            raise SchemeError("quotient: requires 2 arguments")
        a, b = args
        if not is_integer(a) or not is_integer(b):
            raise SchemeError("quotient: requires integers")
        if b == 0:
            raise SchemeError("quotient: division by zero")
        q = abs(a) // abs(b)
        if (a < 0) != (b < 0):
            q = -q
        return q

    def _remainder(args):
        if len(args) != 2:
            raise SchemeError("remainder: requires 2 arguments")
        a, b = args
        if not is_integer(a) or not is_integer(b):
            raise SchemeError("remainder: requires integers")
        if b == 0:
            raise SchemeError("remainder: division by zero")
        return a - _quotient_val(a, b) * b

    def _modulo(args):
        if len(args) != 2:
            raise SchemeError("modulo: requires 2 arguments")
        a, b = args
        if not is_integer(a) or not is_integer(b):
            raise SchemeError("modulo: requires integers")
        if b == 0:
            raise SchemeError("modulo: division by zero")
        r = a - _quotient_val(a, b) * b
        if r != 0 and (r < 0) != (b < 0):
            r += b
        return r

    def _quotient_val(a, b):
        q = abs(a) // abs(b)
        if (a < 0) != (b < 0):
            q = -q
        return q

    def _make_cmp(op_name, cmp_func):
        def proc(args):
            if len(args) < 1:
                raise SchemeError(f"{op_name}: requires at least 1 argument")
            for a in args:
                if not is_integer(a):
                    raise SchemeError(f"{op_name}: requires numbers")
            for i in range(len(args) - 1):
                if not cmp_func(args[i], args[i+1]):
                    return False
            return True
        return proc

    def _number_to_string(args):
        if len(args) < 1 or len(args) > 2:
            raise SchemeError("number->string: requires 1 or 2 arguments")
        n = args[0]
        if not is_integer(n):
            raise SchemeError("number->string: requires an integer")
        radix = 10
        if len(args) == 2:
            radix = args[1]
            if not is_integer(radix):
                raise SchemeError("number->string: radix must be an integer")
            if radix not in (2, 8, 10, 16):
                raise SchemeError("number->string: invalid radix")
        if radix == 10:
            return str(n)
        if n == 0:
            return "0"
        neg = n < 0
        n = abs(n)
        digits = []
        while n > 0:
            digits.append("0123456789abcdef"[n % radix])
            n //= radix
        if neg:
            digits.append('-')
        return ''.join(reversed(digits))

    # ── Pairs and Lists ──
    def _cons(args):
        if len(args) != 2:
            raise SchemeError("cons: requires 2 arguments")
        return Pair(args[0], args[1])

    def _car(args):
        if len(args) != 1:
            raise SchemeError("car: requires 1 argument")
        if not isinstance(args[0], Pair):
            raise SchemeError("car: requires a pair")
        return args[0].car

    def _cdr(args):
        if len(args) != 1:
            raise SchemeError("cdr: requires 1 argument")
        if not isinstance(args[0], Pair):
            raise SchemeError("cdr: requires a pair")
        return args[0].cdr

    def _list(args):
        return from_list(args)

    def _null(args):
        if len(args) != 1:
            raise SchemeError("null?: requires 1 argument")
        return args[0] is NIL

    def _pair(args):
        if len(args) != 1:
            raise SchemeError("pair?: requires 1 argument")
        return isinstance(args[0], Pair)

    def _listp(args):
        if len(args) != 1:
            raise SchemeError("list?: requires 1 argument")
        return is_proper_list(args[0])

    def _length(args):
        if len(args) != 1:
            raise SchemeError("length: requires 1 argument")
        x = args[0]
        n = 0
        while isinstance(x, Pair):
            n += 1
            x = x.cdr
        if x is not NIL:
            raise SchemeError("length: not a proper list")
        return n

    def _append(args):
        if not args:
            return NIL
        result_parts = []
        for i, a in enumerate(args[:-1]):
            if not is_proper_list(a):
                raise SchemeError("append: argument is not a proper list")
            result_parts.append(a)
        last = args[-1]
        # Build result
        all_elements = []
        for part in result_parts:
            cur = part
            while isinstance(cur, Pair):
                all_elements.append(cur.car)
                cur = cur.cdr
        result = last
        for e in reversed(all_elements):
            result = Pair(e, result)
        return result

    def _reverse(args):
        if len(args) != 1:
            raise SchemeError("reverse: requires 1 argument")
        x = args[0]
        if not is_proper_list(x):
            raise SchemeError("reverse: not a proper list")
        result = NIL
        cur = x
        while isinstance(cur, Pair):
            result = Pair(cur.car, result)
            cur = cur.cdr
        return result

    # ── Equality and Predicates ──
    def _eq(args):
        if len(args) != 2:
            raise SchemeError("eq?: requires 2 arguments")
        a, b = args
        if isinstance(a, bool) or isinstance(b, bool):
            return a is b
        if is_integer(a) and is_integer(b):
            return a == b
        if isinstance(a, Symbol) and isinstance(b, Symbol):
            return a is b
        if a is NIL and b is NIL:
            return True
        if a is NIL or b is NIL:
            return False
        return a is b

    def _equal(args):
        if len(args) != 2:
            raise SchemeError("equal?: requires 2 arguments")
        return _equal_impl(args[0], args[1])

    def _equal_impl(a, b):
        stack = [(a, b)]
        while stack:
            a, b = stack.pop()
            if a is b:
                continue
            if isinstance(a, bool) or isinstance(b, bool):
                if a is not b:
                    return False
                continue
            if is_integer(a) and is_integer(b):
                if a != b:
                    return False
                continue
            if isinstance(a, str) and isinstance(b, str):
                if a != b:
                    return False
                continue
            if isinstance(a, Symbol) and isinstance(b, Symbol):
                if a is not b:
                    return False
                continue
            if a is NIL and b is NIL:
                continue
            if isinstance(a, Pair) and isinstance(b, Pair):
                stack.append((a.cdr, b.cdr))
                stack.append((a.car, b.car))
                continue
            return False
        return True

    def _not(args):
        if len(args) != 1:
            raise SchemeError("not: requires 1 argument")
        return args[0] is False

    def _numberp(args):
        if len(args) != 1:
            raise SchemeError("number?: requires 1 argument")
        return is_integer(args[0])

    def _symbolp(args):
        if len(args) != 1:
            raise SchemeError("symbol?: requires 1 argument")
        return isinstance(args[0], Symbol)

    def _stringp(args):
        if len(args) != 1:
            raise SchemeError("string?: requires 1 argument")
        return isinstance(args[0], str)

    def _procedurep(args):
        if len(args) != 1:
            raise SchemeError("procedure?: requires 1 argument")
        return isinstance(args[0], (Closure, Builtin))

    def _string_append(args):
        for a in args:
            if not isinstance(a, str):
                raise SchemeError("string-append: requires strings")
        return ''.join(args)

    # ── Output ──
    def _display(args):
        if len(args) != 1:
            raise SchemeError("display: requires 1 argument")
        output.append(_display_repr(args[0], False))
        return UNSPECIFIED

    def _newline(args):
        if len(args) != 0:
            raise SchemeError("newline: requires 0 arguments")
        output.append('\n')
        return UNSPECIFIED

    def _error(args):
        if len(args) < 1:
            raise SchemeError("error: requires at least 1 argument")
        msg = args[0]
        if not isinstance(msg, str):
            raise SchemeError(str(msg))
        parts = [msg]
        for irr in args[1:]:
            parts.append(' ')
            parts.append(_display_repr(irr, True))
        raise SchemeError(''.join(parts))

    # Register all builtins
    _define('+', _plus)
    _define('*', _times)
    _define('-', _minus)
    _define('quotient', _quotient)
    _define('remainder', _remainder)
    _define('modulo', _modulo)
    _define('=', _make_cmp('=', lambda a, b: a == b))
    _define('<', _make_cmp('<', lambda a, b: a < b))
    _define('>', _make_cmp('>', lambda a, b: a > b))
    _define('<=', _make_cmp('<=', lambda a, b: a <= b))
    _define('>=', _make_cmp('>=', lambda a, b: a >= b))
    _define('number->string', _number_to_string)
    _define('cons', _cons)
    _define('car', _car)
    _define('cdr', _cdr)
    _define('list', _list)
    _define('null?', _null)
    _define('pair?', _pair)
    _define('list?', _listp)
    _define('length', _length)
    _define('append', _append)
    _define('reverse', _reverse)
    _define('eq?', _eq)
    _define('equal?', _equal)
    _define('not', _not)
    _define('number?', _numberp)
    _define('symbol?', _symbolp)
    _define('string?', _stringp)
    _define('procedure?', _procedurep)
    _define('string-append', _string_append)
    _define('display', _display)
    _define('newline', _newline)
    _define('error', _error)

    return env

# ─── Main ─────────────────────────────────────────────────────────────────────

def run(source):
    output = []
    try:
        forms = read_all(source)
    except SchemeError as e:
        e.output = ''
        raise
    except Exception as e:
        raise SchemeError(str(e), '')

    env = _make_global_env(output)

    try:
        for form in forms:
            result = _eval(form, env)
            force(result)
    except SchemeError as e:
        e.output = ''.join(output)
        raise
    except RecursionError:
        raise SchemeError("stack overflow", ''.join(output))
    except Exception as e:
        raise SchemeError(str(e), ''.join(output))

    return ''.join(output)
