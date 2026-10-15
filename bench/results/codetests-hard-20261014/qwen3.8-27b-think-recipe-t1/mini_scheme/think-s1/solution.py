import sys

try:
    sys.set_int_max_str_digits(0)
except (AttributeError, ValueError):
    pass

sys.setrecursionlimit(1000000)


class SchemeError(Exception):
    def __init__(self, msg):
        super().__init__(msg)
        self.output = ''


# --- Data types ---

class _Singleton:
    def __init__(self, name):
        self._name = name
    def __repr__(self):
        return self._name

NIL = _Singleton("NIL")
UNSPECIFIED = _Singleton("UNSPECIFIED")
UNBOUND = _Singleton("UNBOUND")

class Symbol:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name

class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr

class Closure:
    __slots__ = ('formals_type', 'formals', 'body', 'env')
    def __init__(self, formals_type, formals, body, env):
        self.formals_type = formals_type
        self.formals = formals
        self.body = body
        self.env = env

class Builtin:
    __slots__ = ('name', 'func')
    def __init__(self, name, func):
        self.name = name
        self.func = func

class Env:
    __slots__ = ('mappings', 'parent')
    def __init__(self, mappings=None, parent=None):
        self.mappings = mappings if mappings is not None else {}
        self.parent = parent

    def lookup(self, symbol):
        env = self
        while env is not None:
            if symbol in env.mappings:
                val = env.mappings[symbol]
                if val is UNBOUND:
                    raise SchemeError(f"unbound variable: {symbol.name}")
                return val
            env = env.parent
        raise SchemeError(f"unbound variable: {symbol.name}")

    def define(self, symbol, value):
        self.mappings[symbol] = value

    def set(self, symbol, value):
        env = self
        while env is not None:
            if symbol in env.mappings:
                env.mappings[symbol] = value
                return
            env = env.parent
        raise SchemeError(f"unbound variable for set!: {symbol.name}")

# --- Helpers ---

def is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)

def is_bool(x):
    return x is True or x is False

def is_symbol(x):
    return isinstance(x, Symbol)

def is_str(x):
    return isinstance(x, str)

def is_pair(x):
    return isinstance(x, Pair)

def is_nil(x):
    return x is NIL

def is_proper_list(x):
    while True:
        if x is NIL:
            return True
        if isinstance(x, Pair):
            x = x.cdr
        else:
            return False

def to_pylist(x):
    if x is NIL:
        return []
    result = []
    while True:
        if x is NIL:
            return result
        if not isinstance(x, Pair):
            raise SchemeError("expected a proper list")
        result.append(x.car)
        x = x.cdr

def make_list(elems):
    result = NIL
    for e in reversed(elems):
        result = Pair(e, result)
    return result

def make_dotted(elems, tail):
    result = tail
    for e in reversed(elems):
        result = Pair(e, result)
    return result

# --- Reader ---

class _SyntaxError(Exception):
    pass

_DELIMS = set(' \t\n\r()";\'')

def _skip_ws(source, pos):
    n = len(source)
    while pos < n:
        c = source[pos]
        if c in ' \t\n\r':
            pos += 1
        elif c == ';':
            while pos < n and source[pos] != '\n':
                pos += 1
        else:
            break
    return pos

def _is_int_token(token):
    if not token:
        return False
    i = 0
    if token[0] in '+-':
        i = 1
    if i >= len(token):
        return False
    for ch in token[i:]:
        if ch < '0' or ch > '9':
            return False
    return True

def _read_string(source, pos):
    # source[pos] == '"'
    pos += 1
    n = len(source)
    chars = []
    while pos < n:
        c = source[pos]
        if c == '"':
            return ''.join(chars), pos + 1
        elif c == '\\':
            if pos + 1 >= n:
                raise _SyntaxError("unterminated string")
            nc = source[pos + 1]
            if nc == '"':
                chars.append('"')
                pos += 2
            elif nc == '\\':
                chars.append('\\')
                pos += 2
            elif nc == 'n':
                chars.append('\n')
                pos += 2
            else:
                raise _SyntaxError(f"invalid escape: \\{nc}")
        else:
            chars.append(c)
            pos += 1
    raise _SyntaxError("unterminated string")

def _read_form(source, pos):
    n = len(source)
    pos = _skip_ws(source, pos)
    if pos >= n:
        raise _SyntaxError("unexpected end of input")
    c = source[pos]
    if c == '(':
        return _read_list(source, pos)
    if c == ')':
        raise _SyntaxError("unexpected )")
    if c == "'":
        pos += 1
        datum, pos = _read_form(source, pos)
        return make_list([Symbol('quote'), datum]), pos
    if c == '"':
        return _read_string(source, pos)
    if c == '#':
        start = pos
        pos += 1
        while pos < n and source[pos] not in ' \t\n\r()";\'':
            pos += 1
        token = source[start:pos]
        if token == '#t':
            return True, pos
        elif token == '#f':
            return False, pos
        else:
            raise _SyntaxError(f"invalid # token: {token}")
    # Read a token
    start = pos
    while pos < n and source[pos] not in ' \t\n\r()";\'':
        pos += 1
    token = source[start:pos]
    if not token:
        raise _SyntaxError("empty token")
    if _is_int_token(token):
        return int(token), pos
    return Symbol(token), pos

def _read_list(source, pos):
    # source[pos] == '('
    pos += 1
    n = len(source)
    elements = []
    while True:
        pos = _skip_ws(source, pos)
        if pos >= n:
            raise _SyntaxError("unbalanced (")
        if source[pos] == ')':
            pos += 1
            return make_list(elements), pos
        if source[pos] == '.':
            # Check if it's exactly the token "."
            np = pos + 1
            if np < n and source[np] not in ' \t\n\r()";\'':
                # Not a standalone dot; it's part of a symbol like .foo
                elem, pos = _read_form(source, pos)
                elements.append(elem)
                continue
            # It's the dot token
            if not elements:
                raise _SyntaxError("dot without preceding elements")
            # Check no second dot
            pos += 1  # skip the dot
            pos = _skip_ws(source, pos)
            if pos >= n:
                raise _SyntaxError("unterminated dotted list")
            tail, pos = _read_form(source, pos)
            pos = _skip_ws(source, pos)
            if pos >= n or source[pos] != ')':
                raise _SyntaxError("dotted list must end with )")
            pos += 1
            return make_dotted(elements, tail), pos
        elem, pos = _read_form(source, pos)
        elements.append(elem)

def read_all(source):
    pos = 0
    n = len(source)
    forms = []
    while pos < n:
        pos = _skip_ws(source, pos)
        if pos >= n:
            break
        form, pos = _read_form(source, pos)
        forms.append(form)
    return forms

# --- Display / Write ---

def _int_to_str(n, radix=10):
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

def _display_obj(obj):
    if is_int(obj):
        return _int_to_str(obj, 10)
    if obj is True:
        return "#t"
    if obj is False:
        return "#f"
    if is_str(obj):
        return obj
    if is_symbol(obj):
        return obj.name
    if obj is NIL:
        return "()"
    if obj is UNSPECIFIED:
        return ""
    if isinstance(obj, (Closure, Builtin)):
        return "#<procedure>"
    if isinstance(obj, Pair):
        return _display_list(obj)
    return ""

def _display_list(pair):
    parts = []
    current = pair
    while isinstance(current, Pair):
        parts.append(_display_obj(current.car))
        current = current.cdr
    if current is NIL:
        return "(" + " ".join(parts) + ")"
    else:
        parts.append(".")
        parts.append(_display_obj(current))
        return "(" + " ".join(parts) + ")"

def _write_str(s):
    out = ['"']
    for ch in s:
        if ch == '"':
            out.append('\\"')
        elif ch == '\\':
            out.append('\\\\')
        elif ch == '\n':
            out.append('\\n')
        else:
            out.append(ch)
    out.append('"')
    return ''.join(out)

def _write_obj(obj):
    if is_int(obj):
        return _int_to_str(obj, 10)
    if obj is True:
        return "#t"
    if obj is False:
        return "#f"
    if is_str(obj):
        return _write_str(obj)
    if is_symbol(obj):
        return obj.name
    if obj is NIL:
        return "()"
    if obj is UNSPECIFIED:
        return ""
    if isinstance(obj, (Closure, Builtin)):
        return "#<procedure>"
    if isinstance(obj, Pair):
        return _write_list(obj)
    return ""

def _write_list(pair):
    parts = []
    current = pair
    while isinstance(current, Pair):
        parts.append(_write_obj(current.car))
        current = current.cdr
    if current is NIL:
        return "(" + " ".join(parts) + ")"
    else:
        parts.append(".")
        parts.append(_write_obj(current))
        return "(" + " ".join(parts) + ")"

# --- Evaluator ---

class TAIL:
    __slots__ = ('form', 'env')
    def __init__(self, form, env):
        self.form = form
        self.env = env

_output = []

def _is_truthy(x):
    return x is not False

def _eval_loop(form, env):
    while True:
        r = _eval_tail(form, env)
        if isinstance(r, TAIL):
            form, env = r.form, r.env
        else:
            return r

def _eval_tail(form, env):
    """Evaluate form in tail position. Returns value or TAIL."""
    if is_int(form) or is_str(form) or is_bool(form):
        return form
    if is_symbol(form):
        return env.lookup(form)
    if form is NIL:
        raise SchemeError("() is not a valid expression")
    if is_pair(form):
        if not is_proper_list(form):
            raise SchemeError("dotted form cannot be used as an application")
        if form.car is NIL or is_str(form.car) or is_int(form.car) or is_bool(form.car):
            # Non-symbol head that's not a special form → application
            return _eval_app_tail(form, env)
        if is_symbol(form.car):
            name = form.car.name
            if name in _SPECIAL_FORMS:
                return _eval_special_tail(form, env)
        return _eval_app_tail(form, env)
    if isinstance(form, Pair):
        raise SchemeError("dotted form cannot be used as an application")
    raise SchemeError("invalid form")

def _eval_app_tail(form, env):
    """Evaluate a proper list application in tail position."""
    op_expr = form.car
    args_scheme = form.cdr
    op = eval_non_tail(op_expr, env)
    arg_vals = [eval_non_tail(a, env) for a in to_pylist(args_scheme)]
    return _call_procedure(op, arg_vals, True)

def _call_procedure(op, args, tail):
    global _apply_ref
    if op is _apply_ref:
        if len(args) < 2:
            raise SchemeError("apply: at least 2 arguments required")
        f = args[0]
        direct = args[1:-1]
        lst = args[-1]
        if not is_proper_list(lst):
            raise SchemeError("apply: last argument must be a proper list")
        all_args = direct + to_pylist(lst)
        return _call_procedure(f, all_args, tail)
    if isinstance(op, Builtin):
        return op.func(args)
    if isinstance(op, Closure):
        new_env = _bind_closure(op, args)
        if tail:
            return TAIL(op.body, new_env)
        else:
            return _eval_body_non_tail(op.body, new_env)
    raise SchemeError("not a procedure")

def _bind_closure(closure, args):
    ft = closure.formals_type
    if ft == 'fixed':
        if len(args) != len(closure.formals):
            raise SchemeError(f"wrong number of arguments (expected {len(closure.formals)}, got {len(args)})")
        mappings = {}
        for s, v in zip(closure.formals, args):
            mappings[s] = v
    elif ft == 'rest':
        syms, rest_sym = closure.formals
        if len(args) < len(syms):
            raise SchemeError(f"wrong number of arguments (expected at least {len(syms)}, got {len(args)})")
        mappings = {}
        for s, v in zip(syms, args[:len(syms)]):
            mappings[s] = v
        rest_list = make_list(args[len(syms):])
        mappings[rest_sym] = rest_list
    elif ft == 'all':
        mappings = {closure.formals: make_list(args)}
    else:
        raise SchemeError("invalid formals")
    return Env(mappings, closure.env)

def eval_non_tail(form, env):
    """Evaluate form in non-tail position. Returns a value."""
    if is_int(form) or is_str(form) or is_bool(form):
        return form
    if is_symbol(form):
        return env.lookup(form)
    if form is NIL:
        raise SchemeError("() is not a valid expression")
    if is_pair(form):
        if not is_proper_list(form):
            raise SchemeError("dotted form cannot be used as an application")
        if is_symbol(form.car) and form.car.name in _SPECIAL_FORMS:
            return _eval_special_non_tail(form, env)
        # Application
        op_expr = form.car
        args_scheme = form.cdr
        op = eval_non_tail(op_expr, env)
        arg_vals = [eval_non_tail(a, env) for a in to_pylist(args_scheme)]
        return _call_procedure(op, arg_vals, False)
    raise SchemeError("invalid form")

def _eval_body_non_tail(body, env):
    """Evaluate a body (Python list of forms) in non-tail position."""
    # Pre-bind internal definitions
    int_names = []
    for f in body:
        if _is_define_form(f):
            nm = _parse_define_name(f)
            int_names.append(nm)
    if int_names:
        env = Env({n: UNBOUND for n in int_names}, env)
    last_val = UNSPECIFIED
    for f in body:
        if _is_define_form(f):
            nm, expr = _parse_define(f)
            env.define(nm, eval_non_tail(expr, env))
        else:
            last_val = eval_non_tail(f, env)
    return last_val

def _eval_body_tail(body, env):
    """Evaluate a body (Python list of forms) in tail position. Returns value or TAIL."""
    int_names = []
    for f in body:
        if _is_define_form(f):
            nm = _parse_define_name(f)
            int_names.append(nm)
    if int_names:
        env = Env({n: UNBOUND for n in int_names}, env)
    n = len(body)
    for i, f in enumerate(body):
        if _is_define_form(f):
            nm, expr = _parse_define(f)
            env.define(nm, eval_non_tail(expr, env))
            if i == n - 1:
                return UNSPECIFIED
        else:
            if i == n - 1:
                return _eval_tail(f, env)
            else:
                eval_non_tail(f, env)
    return UNSPECIFIED

def _is_define_form(form):
    if not isinstance(form, Pair) or not is_proper_list(form):
        return False
    if form.car is NIL:
        return False
    if not is_symbol(form.car):
        return False
    if form.car.name != 'define':
        return False
    return True

def _parse_define_name(form):
    """Extract the name from a define form. Returns a Symbol."""
    rest = form.cdr  # cdr of (define ...)
    if rest is NIL:
        raise SchemeError("malformed define")
    first = rest.car
    if isinstance(first, Pair) and is_proper_list(first):
        # (define (name ...) ...)
        return first.car
    elif isinstance(first, Pair) and not is_proper_list(first):
        # (define (name . rest) ...)
        return first.car
    elif is_symbol(first):
        return first
    else:
        raise SchemeError("malformed define")

def _parse_define(form):
    """Parse a define form. Returns (name, expr) or (name, lambda_closure_body)."""
    rest = form.cdr
    if rest is NIL:
        raise SchemeError("malformed define")
    first = rest.car
    if isinstance(first, Pair):
        # (define (name formals...) body...)
        if not is_proper_list(first) and first.cdr is not NIL:
            # It's a dotted list: (name . formals)
            name = first.car
            formals = first.cdr
        elif is_proper_list(first):
            name = first.car
            formals = first.cdr
        else:
            name = first.car
            formals = first.cdr
        if not is_symbol(name):
            raise SchemeError("define name must be a symbol")
        # Validate formals
        _validate_formals(formals)
        body = rest.cdr  # (body...) as a scheme list
        if body is NIL:
            raise SchemeError("empty body in define")
        body_py = to_pylist(body)
        return (name, ('_lambda', formals, body_py))
    elif is_symbol(first):
        # (define name expr)
        name = first
        rest2 = rest.cdr
        if rest2 is NIL:
            raise SchemeError("malformed define")
        expr = rest2.car
        return (name, expr)
    else:
        raise SchemeError("malformed define")

def _validate_formals(formals):
    if is_symbol(formals):
        return
    if formals is NIL:
        return
    if isinstance(formals, Pair):
        if is_proper_list(formals):
            for s in to_pylist(formals):
                if not is_symbol(s):
                    raise SchemeError("formals must be symbols")
            return
        else:
            cur = formals
            while isinstance(cur, Pair):
                if not is_symbol(cur.car):
                    raise SchemeError("formals must be symbols")
                cur = cur.cdr
            if not is_symbol(cur):
                raise SchemeError("rest of formals must be a symbol")
            return
    raise SchemeError("invalid formals")

def _parse_formals(formals):
    """Returns (type, data)."""
    if is_symbol(formals):
        return ('all', formals)
    if formals is NIL:
        return ('fixed', [])
    if isinstance(formals, Pair):
        if is_proper_list(formals):
            return ('fixed', to_pylist(formals))
        else:
            syms = []
            cur = formals
            while isinstance(cur, Pair):
                syms.append(cur.car)
                cur = cur.cdr
            return ('rest', (syms, cur))
    raise SchemeError("invalid formals")

# Special form dispatch

_SPECIAL_FORMS = {'quote', 'if', 'define', 'set!', 'begin', 'cond', 'and', 'or', 'let', 'let*', 'letrec', 'lambda'}

def _eval_special_tail(form, env):
    """Evaluate a special form in tail position."""
    name = form.car.name
    rest = form.cdr
    if name == 'quote':
        return _eval_quote(rest)
    elif name == 'if':
        return _eval_if_tail(rest, env)
    elif name == 'define':
        return _eval_define(rest, env)
    elif name == 'set!':
        return _eval_set(rest, env)
    elif name == 'begin':
        return _eval_begin_tail(rest, env)
    elif name == 'cond':
        return _eval_cond_tail(rest, env)
    elif name == 'and':
        return _eval_and_tail(rest, env)
    elif name == 'or':
        return _eval_or_tail(rest, env)
    elif name == 'let':
        return _eval_let_tail(rest, env)
    elif name == 'let*':
        return _eval_letstar_tail(rest, env)
    elif name == 'letrec':
        return _eval_letrec_tail(rest, env)
    elif name == 'lambda':
        return _eval_lambda(rest, env)
    else:
        raise SchemeError(f"unknown special form: {name}")

def _eval_special_non_tail(form, env):
    """Evaluate a special form in non-tail position."""
    name