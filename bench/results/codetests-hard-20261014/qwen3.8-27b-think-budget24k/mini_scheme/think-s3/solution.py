import sys
sys.set_int_max_str_digits(0)
sys.setrecursionlimit(100000)


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
        return f"Symbol({self.name!r})"

class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr

class _Null:
    pass

NULL = _Null()

class _Unspecified:
    pass

UNSPECIFIED = _Unspecified()

class _Uninitialized:
    pass

UNINITIALIZED = _Uninitialized()

class Closure:
    __slots__ = ('formals', 'body', 'env')
    def __init__(self, formals, body, env):
        self.formals = formals
        self.body = body
        self.env = env

class Builtin:
    __slots__ = ('name', 'func')
    def __init__(self, name, func):
        self.name = name
        self.func = func

class _Body:
    __slots__ = ('forms',)
    def __init__(self, forms):
        self.forms = forms

class TailCall:
    __slots__ = ('env', 'form')
    def __init__(self, env, form):
        self.env = env
        self.form = form


# ─── Type Helpers ─────────────────────────────────────────────────────────────

def is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)

def is_bool(x):
    return x is True or x is False

def is_str(x):
    return isinstance(x, str)

def is_sym(x):
    return isinstance(x, Symbol)

def is_pair(x):
    return isinstance(x, Pair)

def is_null(x):
    return x is NULL

def is_proc(x):
    return isinstance(x, (Closure, Builtin))

def is_true(x):
    return x is not False

def is_proper_list(x):
    if x is NULL:
        return True
    while isinstance(x, Pair):
        x = x.cdr
    return x is NULL


# ─── Reader ───────────────────────────────────────────────────────────────────

def _skip_ws_comments(source, pos):
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

def _is_term(source, pos):
    if pos >= len(source):
        return True
    return source[pos] in ' \t\n\r()";\''

def _read_string(source, pos):
    pos += 1
    n = len(source)
    chars = []
    while pos < n:
        c = source[pos]
        if c == '"':
            return (''.join(chars), pos + 1)
        elif c == '\\':
            if pos + 1 >= n:
                raise SchemeError("Syntax error: unterminated string")
            e = source[pos + 1]
            if e == '"':
                chars.append('"')
                pos += 2
            elif e == '\\':
                chars.append('\\')
                pos += 2
            elif e == 'n':
                chars.append('\n')
                pos += 2
            else:
                raise SchemeError(f"Syntax error: invalid escape \\{e}")
        else:
            chars.append(c)
            pos += 1
    raise SchemeError("Syntax error: unterminated string")

def _is_int_token(tok):
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

def _read_token(source, pos):
    n = len(source)
    start = pos
    while pos < n and source[pos] not in ' \t\n\r()";\'' :
        pos += 1
    tok = source[start:pos]
    if not tok:
        raise SchemeError("Syntax error: empty token")
    if tok[0] == '#':
        if tok == '#t':
            return (True, pos)
        elif tok == '#f':
            return (False, pos)
        else:
            raise SchemeError(f"Syntax error: invalid token {tok!r}")
    if _is_int_token(tok):
        return (int(tok), pos)
    return (Symbol(tok), pos)

def _read_one(source, pos):
    n = len(source)
    c = source[pos]
    if c == '(':
        return _read_list(source, pos)
    elif c == "'":
        pos += 1
        pos = _skip_ws_comments(source, pos)
        if pos >= n:
            raise SchemeError("Syntax error: ' not followed by datum")
        datum, pos = _read_one(source, pos)
        return (Pair(Symbol('quote'), Pair(datum, NULL)), pos)
    elif c == '"':
        return _read_string(source, pos)
    else:
        return _read_token(source, pos)

def _read_list(source, pos):
    pos += 1
    n = len(source)
    elements = []
    pos = _skip_ws_comments(source, pos)
    if pos >= n:
        raise SchemeError("Syntax error: unbalanced parenthesis")
    if source[pos] == ')':
        return (NULL, pos + 1)
    while True:
        pos = _skip_ws_comments(source, pos)
        if pos >= n:
            raise SchemeError("Syntax error: unbalanced parenthesis")
        if source[pos] == ')':
            result = NULL
            for e in reversed(elements):
                result = Pair(e, result)
            return (result, pos + 1)
        if source[pos] == '.' and (pos + 1 >= n or source[pos + 1] in ' \t\n\r()";\'' ):
            if not elements:
                raise SchemeError("Syntax error: dot must be preceded by at least one element")
            pos += 1
            pos = _skip_ws_comments(source, pos)
            if pos >= n:
                raise SchemeError("Syntax error: unbalanced parenthesis")
            last, pos = _read_one(source, pos)
            pos = _skip_ws_comments(source, pos)
            if pos >= n or source[pos] != ')':
                raise SchemeError("Syntax error: malformed dotted list")
            pos += 1
            result = last
            for e in reversed(elements):
                result = Pair(e, result)
            return (result, pos)
        elem, pos = _read_one(source, pos)
        elements.append(elem)

def read_all(source):
    forms = []
    pos = 0
    n = len(source)
    while pos < n:
        pos = _skip_ws_comments(source, pos)
        if pos >= n:
            break
        form, pos = _read_one(source, pos)
        forms.append(form)
    return forms


# ─── Environment ──────────────────────────────────────────────────────────────

class Env:
    __slots__ = ('bindings', 'parent')
    def __init__(self, bindings=None, parent=None):
        self.bindings = bindings if bindings is not None else {}
        self.parent = parent

    def lookup(self, name):
        env = self
        while env is not None:
            if name in env.bindings:
                val = env.bindings[name]
                if val is UNINITIALIZED:
                    raise SchemeError(f"Uninitialized variable: {name}")
                return val
            env = env.parent
        raise SchemeError(f"Unbound variable: {name}")

    def set(self, name, value):
        env = self
        while env is not None:
            if name in env.bindings:
                env.bindings[name] = value
                return
            env = env.parent
        raise SchemeError(f"Unbound variable: {name}")

    def define(self, name, value):
        self.bindings[name] = value


# ─── Display / Write ──────────────────────────────────────────────────────────

def display_repr(x):
    if is_int(x):
        return str(x)
    if x is True:
        return '#t'
    if x is False:
        return '#f'
    if is_str(x):
        return x
    if is_sym(x):
        return x.name
    if x is NULL:
        return '()'
    if x is UNSPECIFIED:
        return ''
    if is_proc(x):
        return '#<procedure>'
    if is_pair(x):
        return _display_pair(x)
    return ''

def _display_pair(p):
    parts = []
    cur = p
    while isinstance(cur, Pair):
        parts.append(display_repr(cur.car))
        cur = cur.cdr
    if cur is NULL:
        return '(' + ' '.join(parts) + ')'
    return '(' + ' '.join(parts) + ' . ' + display_repr(cur) + ')'

def write_repr(x):
    if is_int(x):
        return str(x)
    if x is True:
        return '#t'
    if x is False:
        return '#f'
    if is_str(x):
        return '"' + x.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'
    if is_sym(x):
        return x.name
    if x is NULL:
        return '()'
    if x is UNSPECIFIED:
        return ''
    if is_proc(x):
        return '#<procedure>'
    if is_pair(x):
        return _write_pair(x)
    return ''

def _write_pair(p):
    parts = []
    cur = p
    while isinstance(cur, Pair):
        parts.append(write_repr(cur.car))
        cur = cur.cdr
    if cur is NULL:
        return '(' + ' '.join(parts) + ')'
    return '(' + ' '.join(parts) + ' . ' + write_repr(cur) + ')'


# ─── Evaluator ────────────────────────────────────────────────────────────────

def eval_form(form, env):
    """Trampoline: evaluate form in env, resolving tail calls. Returns a value."""
    while True:
        result = eval_step(form, env, True)
        if isinstance(result, TailCall):
            form, env = result.form, result.env
            continue
        return result

def eval_value(form, env):
    """Evaluate form in a non-tail position. Always returns a value."""
    return eval_step(form, env, False)

def eval_step(form, env, tail):
    """One step of evaluation. Returns a value or TailCall."""
    # Self-evaluating
    if is_int(form) or is_bool(form) or is_str(form):
        return form
    if form is NULL:
        return NULL
    if form is UNSPECIFIED:
        return UNSPECIFIED

    # Symbol lookup
    if is_sym(form):
        return env.lookup(form.name)

    # Body form (internal to the evaluator)
    if isinstance(form, _Body):
        return _eval_body(form.forms, env)

    # Pair: special form or application
    if is_pair(form):
        head = form.car
        args = form.cdr

        if is_sym(head):
            name = head.name
            if name == 'quote':
                return _eval_quote(args)
            elif name == 'if':
                return _eval_if(args, env, tail)
            elif name == 'define':
                return _eval_define(args, env)
            elif name == 'set!':
                return _eval_set(args, env)
            elif name == 'begin':
                return _eval_begin(args, env, tail)
            elif name == 'cond':
                return _eval_cond(args, env, tail)
            elif name == 'and':
                return _eval_and(args, env, tail)
            elif name == 'or':
                return _eval_or(args, env, tail)
            elif name == 'let':
                return _eval_let(args, env)
            elif name == 'let*':
                return _eval_let_star(args, env)
            elif name == 'letrec':
                return _eval_letrec(args, env)
            elif name == 'lambda':
                return _eval_lambda(args, env)

        # General application
        return _eval_apply(form, env, tail)

    raise SchemeError(f"Invalid form")

def _eval_quote(args):
    if not is_pair(args) or args.cdr is not NULL:
        raise SchemeError("quote: expected exactly 1 argument")
    return args.car

def _eval_if(args, env, tail):
    if not is_pair(args):
        raise SchemeError("if: malformed")
    test = args.car
    rest = args.cdr
    if not is_pair(rest):
        raise SchemeError("if: malformed")
    then_form = rest.car
    rest2 = rest.cdr
    if rest2 is not NULL and not is_pair(rest2):
        raise SchemeError("if: malformed")
    has_else = rest2 is not NULL
    if has_else and rest2.cdr is not NULL:
        raise SchemeError("if: malformed")

    test_val = eval_value(test, env)
    if is_true(test_val):
        if tail:
            return eval_step(then_form, env, True)
        else:
            return eval_form(then_form, env)
    else:
        if has_else:
            else_form = rest2.car
            if tail:
                return eval_step(else_form, env, True)
            else:
                return eval_form(else_form, env)
        else:
            return UNSPECIFIED

def _eval_define(args, env):
    if not is_pair(args):
        raise SchemeError("define: malformed")
    first = args.car
    rest = args.cdr
    if rest is NULL:
        raise SchemeError("define: malformed")
    if is_sym(first):
        if rest.cdr is not NULL:
            raise SchemeError("define: malformed")
        val = eval_value(rest.car, env)
        env.define(first.name, val)
        return UNSPECIFIED
    elif is_pair(first):
        name = first.car
        if not is_sym(name):
            raise SchemeError("define: name must be a symbol")
        formals = first.cdr
        body = rest
        closure = _make_closure(formals, body, env)
        env.define(name.name, closure)
        return UNSPECIFIED
    else:
        raise SchemeError("define: malformed")

def _eval_set(args, env):
    if not is_pair(args) or args.cdr is NULL or args.cdr.cdr is not NULL:
        raise SchemeError("set!: malformed")
    name = args.car
    if not is_sym(name):
        raise SchemeError("set!: name must be a symbol")
    val = eval_value(args.cdr.car, env)
    env.set(name.name, val)
    return UNSPECIFIED

def _eval_begin(args, env, tail):
    if not is_pair(args):
        raise SchemeError("begin: malformed")
    current = args
    while current.cdr is not NULL:
        eval_value(current.car, env)
        current = current.cdr
    last = current.car
    if tail:
        return eval_step(last, env, True)
    else:
        return eval_form(last, env)

def _eval_cond(args, env, tail):
    current = args
    while is_pair(current):
        clause = current.car
        if not is_pair(clause):
            raise SchemeError("cond: malformed clause")
        test = clause.car
        rest = clause.cdr
        if is_sym(test) and test.name == 'else':
            if rest is NULL:
                raise SchemeError("cond: else clause must have expressions")
            r = rest
            while r.cdr is not NULL:
                eval_value(r.car, env)
                r = r.cdr
            if tail:
                return eval_step(r.car, env, True)
            else:
                return eval_form(r.car, env)
        else:
            test_val = eval_value(test, env)
            if is_true(test_val):
                if rest is NULL:
                    return test_val
                r = rest
                while r.cdr is not NULL:
                    eval_value(r.car, env)
                    r = r.cdr
                if tail:
                    return eval_step(r.car, env, True)
                else:
                    return eval_form(r.car, env)
        current = current.cdr
    return UNSPECIFIED

def _eval_and(args, env, tail):
    if args is NULL:
        return True
    current = args
    while current.cdr is not NULL:
        val = eval_value(current.car, env)
        if val is False:
            return False
        current = current.cdr
    last = current.car
    if tail:
        return eval_step(last, env, True)
    else:
        return eval_form(last, env)

def _eval_or(args, env, tail):
    if args is NULL:
        return False
    current = args
    while current.cdr is not NULL:
        val = eval_value(current.car, env)
        if val is not False:
            return val
        current = current.cdr
    last = current.car
    if tail:
        return eval_step(last, env, True)
    else:
        return eval_form(last, env)

def _eval_lambda(args, env):
    if not is_pair(args) or args.cdr is not NULL:
        raise SchemeError("lambda: malformed")
    formals = args.car
    body = args.cdr
    return _make_closure(formals, body, env)

def _make_closure(formals, body, env):
    if not is_pair(body):
        raise SchemeError("lambda: empty body")
    # Validate formals
    if is_sym(formals):
        pass  # rest args: (lambda args ...)
    elif is_pair(formals):
        # Check it's a proper list of symbols, or dotted (a b . rest)
        cur = formals
        while is_pair(cur):
            if not is_sym(cur.car):
                raise SchemeError("lambda: formals must be symbols")
            cur = cur.cdr
        # cur is NULL (proper list) or a symbol (dotted rest)
        if cur is not NULL and not is_sym(cur):
            raise SchemeError("lambda: invalid formals")
    else:
        raise SchemeError("lambda: invalid formals")
    return Closure(formals, body, env)

def _eval_let(args, env):
    # (let ((v init) ...) body...) or (let name ((v init) ...) body...)
    if not is_pair(args):
        raise SchemeError("let: malformed")
    first = args.car
    rest = args.cdr

    if is_sym(first):
        # Named let
        return _eval_named_let(first, rest, env)
    elif is_pair(first):
        # Regular let
        bindings = _parse_bindings(first)
        body = rest
        if not is_pair(body):
            raise SchemeError("let: empty body")
        # Evaluate inits in outer scope
        init_vals = []
        for _, init in bindings:
            init_vals.append(eval_value(init, env))
        new_env = Env(dict(zip([v.name for v, _ in bindings], init_vals)), env)
        return _eval_body(body, new_env)
    else:
        raise SchemeError("let: malformed")

def _eval_named_let(name, rest, env):
    if not is_pair(rest):
        raise SchemeError("let: malformed")
    bindings = _parse_bindings(rest.car)
    body = rest.cdr
    if not is_pair(body):
        raise SchemeError("let: empty body")
    # Evaluate inits in outer scope
    init_vals = []
    for _, init in bindings:
        init_vals.append(eval_value(init, env))
    formals = [v for v, _ in bindings]
    new_env = Env({}, env)
    closure = Closure(formals, body, new_env)
    new_env.define(name.name, closure)
    param_env = Env(dict(zip([v.name for v, _ in bindings], init_vals)), new_env)
    return TailCall(param_env, _Body(body))

def _eval_let_star(args, env):
    if not is_pair(args):
        raise SchemeError("let*: malformed")
    bindings = _parse_bindings(args.car)
    body = args.cdr
    if not is_pair(body):
        raise SchemeError("let*: empty body")
    new_env = Env({}, env)
    for v, init in bindings:
        val = eval_value(init, new_env)
        new_env.define(v.name, val)
    return _eval_body(body, new_env)

def _eval_letrec(args, env):
    if not is_pair(args):
        raise SchemeError("letrec: malformed")
    bindings = _parse_bindings(args.car)
    body = args.cdr
    if not is_pair(body):
        raise SchemeError("letrec: empty body")
    new_env = Env({v.name: UNINITIALIZED for v, _ in bindings}, env)
    for v, init in bindings:
        val = eval_value(init, new_env)
        new_env.bindings[v.name] = val
    return _eval_body(body, new_env)

def _parse_bindings(pairs):
    bindings = []
    cur = pairs
    while is_pair(cur):
        b = cur.car
        if not is_pair(b) or not is_pair(b.cdr) or b.cdr.cdr is not NULL:
            raise SchemeError("malformed binding")
        v = b.car
        if not is_sym(v):
            raise SchemeError("binding name must be a symbol")
        init = b.cdr.car
        bindings.append((v, init))
        cur = cur.cdr
    if cur is not NULL:
        raise SchemeError("malformed bindings")
    return bindings

def _eval_body(forms, env):
    """Evaluate a body (linked list of forms). Returns value or TailCall."""
    # Scan for internal defines
    internal_names = []
    cur = forms
    while cur is not NULL:
        f = cur.car
        if is_pair(f) and is_sym(f.car) and f.car.name == 'define':
            nm = _extract_define_name(f.cdr)
            if nm is not None:
                internal_names.append(nm)
        cur = cur.cdr

    if internal_names:
        env = Env({nm: UNINITIALIZED for nm in internal_names}, env)

    # Evaluate all but last (non-tail)
    cur = forms
    while cur.cdr is not NULL:
        f = cur.car
        if _is_internal_define(f):
            _handle_internal_define(f.cdr, env)
        else:
            eval_value(f, env)
        cur = cur.cdr

    # Last form (tail position)
    last = cur.car
    if _is_internal_define(last):
        _handle_internal_define(last.cdr, env)
        return UNSPECIFIED
    else:
        return eval_step(last, env, True)

def _is_internal_define(f):
    return is_pair(f) and is_sym(f.car) and f.car.name == 'define'

def _extract_define_name(args):
    if not is_pair(args):
        return None
    first = args.car
    if is_sym(first):
        return first.name
    elif is_pair(first):
        if is_sym(first.car):
            return first.car.name
    return None

def _handle_internal_define(args, env):
    if not is_pair(args):
        raise SchemeError("define: malformed")
    first = args.car
    rest = args.cdr
    if rest is NULL:
        raise SchemeError("define: malformed")
    if is_sym(first):
        if rest.cdr is not NULL:
            raise SchemeError("define: malformed")
        val = eval_value(rest.car, env)
        env.bindings[first.name] = val
    elif is_pair(first):
        name = first.car
        if not is_sym(name):
            raise SchemeError("define: name must be a symbol")
        formals = first.cdr
        body = rest
        closure = _make_closure(formals, body, env)
        env.bindings[name.name] = closure
    else:
        raise SchemeError("define: malformed")

def _eval_apply(form, env, tail):
    head = form.car
    args = form.cdr

    # Check dotted
    if args is not NULL and not is_pair(args):
        raise SchemeError("Dotted form used as application")

    # Evaluate operator
    op_val = eval_value(head, env)

    # Evaluate arguments left to right
    arg_vals = []
    cur = args
    while is_pair(cur):
        arg_vals.append(eval_value(cur.car, env))
        cur = cur.cdr

    if not is_proc(op_val):
        raise SchemeError("Attempt to apply non-procedure")

    # Special case: apply builtin in tail position
    if isinstance(op_val, Builtin) and op_val.name == 'apply' and tail:
        # (apply f a ... lst) in tail position
        if len(arg_vals) < 2:
            raise SchemeError("apply: expected at least 2 arguments")
        f = arg_vals[0]
        middle = arg_vals[1:-1]
        lst = arg_vals[-1]
        if not is_proc(f):
            raise SchemeError("apply: first argument must be a procedure")
        if not is_proper_list(lst):
            raise SchemeError("apply: last argument must be a proper list")
        all_args = middle + _list_to_py(lst)
        return _call_proc(f, all_args, env, True)

    return _call_proc(op_val, arg_vals, env, tail)

def _list_to_py(l):
    result = []
    cur = l
    while cur is not NULL:
        result.append(cur.car)
        cur = cur.cdr
    return result

def _call_proc(proc, arg_vals, env, tail):
    if isinstance(proc, Closure):
        new_env = _bind_params(proc.formals, arg_vals, proc.env)
        if tail:
            return TailCall(new_env, _Body(proc.body))
        else:
            return eval_form(_Body(proc.body), new_env)
    elif isinstance(proc, Builtin):
        return proc.func(arg_vals)
    else:
        raise SchemeError("Attempt to apply non-procedure")

def _bind_params(formals, arg_vals, closure_env):
    if is_sym(formals):
        # Rest args: all collected into a list
        lst = NULL
        for a in reversed(arg_vals):
            lst = Pair(a, lst)
        return Env({formals.name: lst}, closure_env)
    elif is_pair(formals):
        # Fixed or dotted
        fixed = []
        cur = formals
        while is_pair(cur):
            fixed.append(cur.car)
            cur = cur.cdr
        # cur is NULL (fixed) or Symbol (dotted rest)
        if cur is NULL:
            if len(arg_vals) != len(fixed):
                raise SchemeError(f"Wrong number of arguments: expected {len(fixed)}, got {len(arg_vals)}")
            bindings = {v.name: a for v, a in zip(fixed, arg_vals)}
        else:
            rest_sym = cur
            if len(arg_vals) < len(fixed):
                raise SchemeError(f"Wrong number of arguments: expected at least {len(fixed)}, got {len(arg_vals)}")
            bindings = {v.name: a for v, a in zip(fixed, arg_vals[:len(fixed)])}
            rest_list = NULL
            for a in reversed(arg_vals[len(fixed):]):
                rest_list = Pair(a, rest_list)
            bindings[rest_sym.name] = rest_list
        return Env(bindings, closure_env)
    else:
        raise SchemeError("Invalid formals")


# ─── Builtins ─────────────────────────────────────────────────────────────────

def _builtin_plus(args):
    for a in args:
        if not is_int(a):
            raise SchemeError("+: all arguments must be integers")
    return sum(args)

def _builtin_star(args):
    for a in args:
        if not is_int(a):
            raise SchemeError("*: all arguments must be integers")
    result = 1
    for a in args:
        result *= a
    return result

def _builtin_minus(args):
    if len(args) < 1:
        raise SchemeError("-: expected at least 1 argument")
    for a in args:
        if not is_int(a):
            raise SchemeError("-: all arguments must be integers")
    if len(args) == 1:
        return -args[0]
    result = args[0]
    for a in args[1:]:
        result -= a
    return result

def _builtin_quotient(args):
    if len(args) != 2:
        raise SchemeError("quotient: expected 2 arguments")
    a, b = args
    if not is_int(a) or not is_int(b):
        raise SchemeError("quotient: arguments must be integers")
    if b == 0:
        raise SchemeError("quotient: division by zero")
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        q = -q
    return q

def _builtin_remainder(args):
    if len(args) != 2:
        raise SchemeError("remainder: expected 2 arguments")
    a, b = args
    if not is_int(a) or not is_int(b):
        raise SchemeError("remainder: arguments must be integers")
    if b == 0:
        raise SchemeError("remainder: division by zero")
    q = _builtin_quotient([a, b])
    return a - q * b

def _builtin_modulo(args):
    if len(args) != 2:
        raise SchemeError("modulo: expected 2 arguments")
    a, b = args
    if not is_int(a) or not is_int(b):
        raise SchemeError("modulo: arguments must be integers")
    if b == 0:
        raise SchemeError("modulo: division by zero")
    r = _builtin_remainder([a, b])
    if r != 0 and (r < 0) != (b < 0):
        r += b
    return r

def _make_cmp(name, func):
    def _cmp(args):
        if len(args) == 0:
            raise SchemeError(f"{name}: expected at least 1 argument")
        for a in args:
            if not is_int(a):
                raise SchemeError(f"{name}: all arguments must be integers")
        for i in range(len(args) - 1):
            if not func(args[i], args[i + 1]):
                return False
        return True
    return _cmp

def _builtin_eq(args):
    if len(args) != 2:
        raise SchemeError("eq?: expected 2 arguments")
    a, b = args
    if is_int(a):
        return is_int(b) and a == b
    if is_bool(a):
        return a is b
    if is_str(a):
        return a is b
    if is_sym(a):
        return is_sym(b) and a.name == b.name
    if a is NULL:
        return b is NULL
    if a is UNSPECIFIED:
        return b is UNSPECIFIED
    return a is b

def _scheme_equal(a, b):
    if is_int(a):
        return is_int(b) and a == b
    if is_bool(a):
        return a is b
    if is_str(a):
        return is_str(b) and a == b
    if is_sym(a):
        return is_sym(b) and a.name == b.name
    if a is NULL:
        return b is NULL
    if a is UNSPECIFIED:
        return b is UNSPECIFIED
    if is_proc(a):
        return a is b
    if is_pair(a):
        if not is_pair(b):
            return False
        # Iterative for flat lists, recursive for nested
        while is_pair(a) and is_pair(b):
            if not _scheme_equal(a.car, b.car):
                return False
            a = a.cdr
            b = b.cdr
        return _scheme_equal(a, b)
    return False

def _builtin_equal(args):
    if len(args) != 2:
        raise SchemeError("equal?: expected 2 arguments")
    return _scheme_equal(args[0], args[1])

def _builtin_not(args):
    if len(args) != 1:
        raise SchemeError("not: expected 1 argument")
    return args[0] is False

def _builtin_number_p(args):
    if len(args) != 1:
        raise SchemeError("number?: expected 1 argument")
    return is_int(args[0])

def _builtin_symbol_p(args):
    if len(args) != 1:
        raise SchemeError("symbol?: expected 1 argument")
    return is_sym(args[0])

def _builtin_string_p(args):
    if len(args) != 1:
        raise SchemeError("string?: expected 1 argument")
    return is_str(args[0])

def _builtin_procedure_p(args):
    if len(args) != 1:
        raise SchemeError("procedure?: expected 1 argument")
    return is_proc(args[0])

def _builtin_null_p(args):
    if len(args) != 1:
        raise SchemeError("null?: expected 1 argument")
    return args[0] is NULL

def _builtin_pair_p(args):
    if len(args) != 1:
        raise SchemeError("pair?: expected 1 argument")
    return is_pair(args[0])

def _builtin_list_p(args):
    if len(args) != 1:
        raise SchemeError("list?: expected 1 argument")
    return is_proper_list(args[0])

def _builtin_cons(args):
    if len(args) != 2:
        raise SchemeError("cons: expected 2 arguments")
    return Pair(args[0], args[1])

def _builtin_car(args):
    if len(args) != 1:
        raise SchemeError("car: expected 1 argument")
    if not is_pair(args[0]):
        raise SchemeError("car: not a pair")
    return args[0].car

def _builtin_cdr(args):
    if len(args) != 1:
        raise SchemeError("cdr: expected 1 argument")
    if not is_pair(args[0]):
        raise SchemeError("cdr: not a pair")
    return args[0].cdr

def _builtin_list(args):
    result = NULL
    for a in reversed(args):
        result = Pair(a, result)
    return result

def _builtin_length(args):
    if len(args) != 1