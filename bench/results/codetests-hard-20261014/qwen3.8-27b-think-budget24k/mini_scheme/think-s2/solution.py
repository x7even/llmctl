import sys

try:
    sys.set_int_max_str_digits(0)
except AttributeError:
    pass

sys.setrecursionlimit(1000000)


class SchemeError(Exception):
    def __init__(self, msg, output=''):
        super().__init__(msg)
        self.output = output


# ─── Value classes ───────────────────────────────────────────────────────────

class _Unspecified:
    pass

UNSPECIFIED = _Unspecified()

class _Uninitialized:
    pass

UNINITIALIZED = _Uninitialized()

class _Symbol:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name
    def __repr__(self):
        return f"Symbol({self.name!r})"
    def __eq__(self, other):
        return isinstance(other, _Symbol) and self.name == other.name
    def __hash__(self):
        return hash(self.name)

class _Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr
    def __repr__(self):
        return f"Pair({self.car!r}, {self.cdr!r})"

class _Closure:
    __slots__ = ('formals', 'body', 'env')
    def __init__(self, formals, body, env):
        self.formals = formals  # ('fixed', [syms]) | ('dotted', [syms], sym) | ('varargs', sym)
        self.body = body        # list of forms
        self.env = env

class _Builtin:
    __slots__ = ('name', 'func')
    def __init__(self, name, func):
        self.name = name
        self.func = func

class _Env:
    __slots__ = ('frame', 'parent')
    def __init__(self, frame, parent=None):
        self.frame = frame
        self.parent = parent
    def lookup(self, name):
        e = self
        while e is not None:
            if name in e.frame:
                v = e.frame[name]
                if v is UNINITIALIZED:
                    raise SchemeError(f"Variable '{name}' is not yet initialized")
                return v
            e = e.parent
        raise SchemeError(f"Unbound variable: {name}")
    def set(self, name, value):
        e = self
        while e is not None:
            if name in e.frame:
                e.frame[name] = value
                return
            e = e.parent
        raise SchemeError(f"Unbound variable: {name}")
    def define(self, name, value):
        self.frame[name] = value

class _Body:
    __slots__ = ('forms',)
    def __init__(self, forms):
        self.forms = forms

class _TCO:
    __slots__ = ('expr', 'env')
    def __init__(self, expr, env):
        self.expr = expr
        self.env = env


# ─── Type helpers ────────────────────────────────────────────────────────────

def _is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)

def _is_bool(x):
    return isinstance(x, bool)

def _is_str(x):
    return isinstance(x, str)

def _is_symbol(x):
    return isinstance(x, _Symbol)

def _is_pair(x):
    return isinstance(x, _Pair)

def _is_null(x):
    return x == ()

def _is_procedure(x):
    return isinstance(x, (_Closure, _Builtin))

def _is_proper_list(x):
    while x != ():
        if not isinstance(x, _Pair):
            return False
        x = x.cdr
    return True

def _to_py_list(x):
    result = []
    while x != ():
        if not isinstance(x, _Pair):
            raise SchemeError("Not a proper list")
        result.append(x.car)
        x = x.cdr
    return result

def _from_py_list(lst):
    result = ()
    for e in reversed(lst):
        result = _Pair(e, result)
    return result

def _iter_proper_list(x):
    while x != ():
        if not isinstance(x, _Pair):
            raise SchemeError("Not a proper list")
        yield x.car
        x = x.cdr


# ─── Integer to string (arbitrary precision, no Python limit) ───────────────

def _int_to_str(n, radix=10):
    if n == 0:
        return '0'
    neg = n < 0
    n = abs(n)
    digits = '0123456789abcdef'
    out = []
    while n > 0:
        n, r = divmod(n, radix)
        out.append(digits[r])
    if neg:
        out.append('-')
    return ''.join(reversed(out))


# ─── Display / Write ─────────────────────────────────────────────────────────

def _display(x, out):
    if _is_int(x):
        out.append(_int_to_str(x, 10))
    elif x is True:
        out.append('#t')
    elif x is False:
        out.append('#f')
    elif _is_str(x):
        out.append(x)
    elif _is_symbol(x):
        out.append(x.name)
    elif _is_null(x):
        out.append('()')
    elif _is_pair(x):
        _display_pair(x, out)
    elif _is_procedure(x):
        out.append('#<procedure>')
    elif x is UNSPECIFIED:
        pass
    else:
        out.append('')

def _display_pair(pair, out):
    out.append('(')
    first = True
    while isinstance(pair, _Pair):
        if not first:
            out.append(' ')
        _display(pair.car, out)
        first = False
        if pair.cdr == ():
            break
        elif isinstance(pair.cdr, _Pair):
            pair = pair.cdr
        else:
            out.append(' . ')
            _display(pair.cdr, out)
            out.append(')')
            return
    out.append(')')

def _write(x):
    if _is_int(x):
        return _int_to_str(x, 10)
    elif x is True:
        return '#t'
    elif x is False:
        return '#f'
    elif _is_str(x):
        return '"' + _escape_str(x) + '"'
    elif _is_symbol(x):
        return x.name
    elif _is_null(x):
        return '()'
    elif _is_pair(x):
        return _write_pair(x)
    elif _is_procedure(x):
        return '#<procedure>'
    elif x is UNSPECIFIED:
        return ''
    return ''

def _escape_str(s):
    r = []
    for c in s:
        if c == '"':
            r.append('\\"')
        elif c == '\\':
            r.append('\\\\')
        elif c == '\n':
            r.append('\\n')
        else:
            r.append(c)
    return ''.join(r)

def _write_pair(pair):
    r = ['(']
    first = True
    while isinstance(pair, _Pair):
        if not first:
            r.append(' ')
        r.append(_write(pair.car))
        first = False
        if pair.cdr == ():
            break
        elif isinstance(pair.cdr, _Pair):
            pair = pair.cdr
        else:
            r.append(' . ')
            r.append(_write(pair.cdr))
            r.append(')')
            return ''.join(r)
    r.append(')')
    return ''.join(r)


# ─── Reader ──────────────────────────────────────────────────────────────────

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
            s = []
            terminated = False
            while i < n:
                if source[i] == '\\' and i + 1 < n:
                    nxt = source[i + 1]
                    if nxt == '"':
                        s.append('"')
                        i += 2
                    elif nxt == '\\':
                        s.append('\\')
                        i += 2
                    elif nxt == 'n':
                        s.append('\n')
                        i += 2
                    else:
                        raise SchemeError(f"Invalid escape sequence: \\{nxt}")
                elif source[i] == '"':
                    i += 1
                    terminated = True
                    break
                else:
                    s.append(source[i])
                    i += 1
            if not terminated:
                raise SchemeError("Unterminated string literal")
            tokens.append(('str', ''.join(s)))
        else:
            start = i
            while i < n and source[i] not in ' \t\n\r()";\'':
                i += 1
            tok = source[start:i]
            if tok == '.':
                tokens.append('.')
            elif tok == '#t':
                tokens.append('#t')
            elif tok == '#f':
                tokens.append('#f')
            elif tok.startswith('#'):
                raise SchemeError(f"Invalid token: {tok}")
            else:
                tokens.append(tok)
    return tokens

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

def _parse_atom(tok):
    if tok == '#t':
        return True
    if tok == '#f':
        return False
    if _is_int_token(tok):
        return int(tok)
    return _Symbol(tok)

def _parse_list(tokens, pos):
    """Parse a list starting at pos (which points to the token after '(').
    Returns (value, new_pos)."""
    elements = []
    dotted = None
    while True:
        if pos >= len(tokens):
            raise SchemeError("Unbalanced parenthesis")
        tok = tokens[pos]
        if tok == ')':
            if dotted is not None:
                if not elements:
                    raise SchemeError("Invalid dotted list")
                result = _Pair(elements[-1], dotted)
                for e in reversed(elements[:-1]):
                    result = _Pair(e, result)
                return result, pos + 1
            else:
                return _from_py_list(elements), pos + 1
        elif tok == '.':
            if not elements:
                raise SchemeError("Dot must be preceded by at least one element")
            pos += 1
            if pos >= len(tokens):
                raise SchemeError("Expected datum after dot")
            obj, pos = _parse_one(tokens, pos)
            if pos >= len(tokens) or tokens[pos] != ')':
                raise SchemeError("Expected ) after dotted datum")
            result = _Pair(elements[-1], obj)
            for e in reversed(elements[:-1]):
                result = _Pair(e, result)
            return result, pos + 1
        else:
            obj, pos = _parse_one(tokens, pos)
            elements.append(obj)

def _parse_one(tokens, pos):
    if pos >= len(tokens):
        raise SchemeError("Unexpected end of input")
    tok = tokens[pos]
    if tok == '(':
        return _parse_list(tokens, pos + 1)
    elif tok == ')':
        raise SchemeError("Unexpected )")
    elif tok == "'":
        if pos + 1 >= len(tokens):
            raise SchemeError("Quote not followed by datum")
        obj, new_pos = _parse_one(tokens, pos + 1)
        return _Pair(_Symbol('quote'), _Pair(obj, ())), new_pos
    elif tok == '.':
        raise SchemeError("Unexpected .")
    elif isinstance(tok, tuple):
        return tok[1], pos + 1
    else:
        return _parse_atom(tok), pos + 1

def _read_all(source):
    tokens = _tokenize(source)
    forms = []
    pos = 0
    while pos < len(tokens):
        if tokens[pos] == ')':
            raise SchemeError("Unbalanced )")
        obj, pos = _parse_one(tokens, pos)
        forms.append(obj)
    return forms


# ─── Evaluator ───────────────────────────────────────────────────────────────

_SPECIAL_FORMS = frozenset([
    'quote', 'if', 'define', 'set!', 'begin', 'cond',
    'and', 'or', 'let', 'let*', 'letrec', 'lambda'
])

_APPLY_BUILTIN = None  # set later

def _parse_formals(formals_expr):
    if _is_symbol(formals_expr):
        return ('varargs', formals_expr)
    if formals_expr == ():
        return ('fixed', [])
    if _is_pair(formals_expr):
        if _is_proper_list(formals_expr):
            syms = _to_py_list(formals_expr)
            for s in syms:
                if not _is_symbol(s):
                    raise SchemeError("Formals must be symbols")
            return ('fixed', syms)
        else:
            fixed = []
            f = formals_expr
            while isinstance(f, _Pair):
                if not _is_symbol(f.car):
                    raise SchemeError("Formals must be symbols")
                fixed.append(f.car)
                f = f.cdr
            if not _is_symbol(f):
                raise SchemeError("Malformed dotted formals")
            return ('dotted', fixed, f)
    raise SchemeError("Malformed formals")

def _make_call_env(closure, args):
    kind = closure.formals[0]
    if kind == 'varargs':
        sym = closure.formals[1]
        return _Env({sym.name: _from_py_list(args)}, closure.env)
    elif kind == 'fixed':
        syms = closure.formals[1]
        if len(args) != len(syms):
            raise SchemeError("Wrong number of arguments")
        frame = {}
        for s, v in zip(syms, args):
            frame[s.name] = v
        return _Env(frame, closure.env)
    elif kind == 'dotted':
        fixed_syms = closure.formals[1]
        rest_sym = closure.formals[2]
        if len(args) < len(fixed_syms):
            raise SchemeError("Wrong number of arguments")
        frame = {}
        for s, v in zip(fixed_syms, args):
            frame[s.name] = v
        frame[rest_sym.name] = _from_py_list(args[len(fixed_syms):])
        return _Env(frame, closure.env)

def _parse_let_bindings(bindings_expr):
    if bindings_expr == ():
        return []
    if not _is_proper_list(bindings_expr):
        raise SchemeError("Malformed let bindings")
    result = []
    for b in _to_py_list(bindings_expr):
        if not _is_pair(b):
            raise SchemeError("Malformed let binding")
        name = b.car
        rest = b.cdr
        if not _is_pair(rest) or rest.cdr != ():
            raise SchemeError("Malformed let binding")
        if not _is_symbol(name):
            raise SchemeError("Let binding name must be a symbol")
        result.append((name, rest.car))
    return result

def _get_define_name(define_args):
    """Extract the variable name from define arguments (the cdr of the define form)."""
    if define_args == ():
        raise SchemeError("Malformed define")
    first = define_args.car
    if _is_symbol(first):
        return first.name
    elif _is_pair(first):
        if not _is_proper_list(first):
            raise SchemeError("Malformed define")
        head_list = _to_py_list(first)
        if not head_list or not _is_symbol(head_list[0]):
            raise SchemeError("Malformed define")
        return head_list[0].name
    else:
        raise SchemeError("Malformed define")

def _do_define(define_args, env, output):
    """Execute a define. define_args is the cdr of the (define ...) form."""
    if define_args == ():
        raise SchemeError("Malformed define")
    first = define_args.car
    rest = define_args.cdr
    if _is_symbol(first):
        if rest == () or rest.cdr != ():
            raise SchemeError("Malformed define")
        name = first.name
        val = _eval(rest.car, env, output)
        env.define(name, val)
    elif _is_pair(first):
        if rest == ():
            raise SchemeError("Malformed define")
        if not _is_proper_list(first):
            raise SchemeError("Malformed define")
        head_list = _to_py_list(first)
        if not head_list or not _is_symbol(head_list[0]):
            raise SchemeError("Malformed define")
        name = head_list[0].name
        formals_expr = _from_py_list(head_list[1:])
        body = _to_py_list(rest)
        if not body:
            raise SchemeError("Empty body")
        formals = _parse_formals(formals_expr)
        closure = _Closure(formals, body, env)
        env.define(name, closure)
    else:
        raise SchemeError("Malformed define")
    return UNSPECIFIED

def _eval(expr, env, output):
    """Evaluate expr in non-tail position. Returns a value."""
    if _is_int(expr) or _is_str(expr) or _is_bool(expr):
        return expr
    if _is_symbol(expr):
        return env.lookup(expr.name)
    if expr == ():
        raise SchemeError("() is not a procedure")
    if _is_pair(expr):
        if not _is_proper_list(expr):
            raise SchemeError("Dotted form used as application")
        head = expr.car
        rest = expr.cdr
        if _is_symbol(head) and head.name in _SPECIAL_FORMS:
            return _eval_special(head.name, rest, env, output)
        op = _eval(head, env, output)
        arg_vals = []
        for a in _iter_proper_list(rest):
            arg_vals.append(_eval(a, env, output))
        return _apply(op, arg_vals, env, output)
    if expr is UNSPECIFIED:
        return UNSPECIFIED
    return expr

def _apply(op, args, env, output):
    if isinstance(op, _Closure):
        new_env = _make_call_env(op, args)
        return _eval_tail(_Body(op.body), new_env, output)
    elif isinstance(op, _Builtin):
        return op.func(args, output)
    else:
        raise SchemeError("Not a procedure")

def _eval_special(name, args, env, output):
    """Evaluate a special form in non-tail position. Returns a value."""
    if name == 'quote':
        if args == () or args.cdr != ():
            raise SchemeError("Malformed quote")
        return args.car
    elif name == 'define':
        return _do_define(args, env, output)
    elif name == 'set!':
        if args == () or args.cdr == () or args.cdr.cdr != ():
            raise SchemeError("Malformed set!")
        name_sym = args.car
        if not _is_symbol(name_sym):
            raise SchemeError("set! name must be a symbol")
        val = _eval(args.cdr.car, env, output)
        env.set(name_sym.name, val)
        return UNSPECIFIED
    elif name == 'if':
        if args == () or args.cdr == ():
            raise SchemeError("Malformed if")
        test_val = _eval(args.car, env, output)
        if test_val is not False:
            return _eval(args.cdr.car, env, output)
        else:
            rest = args.cdr.cdr
            if rest == ():
                return UNSPECIFIED
            if rest.cdr != ():
                raise SchemeError("Malformed if")
            return _eval(rest.car, env, output)
    elif name == 'begin':
        if args == ():
            raise SchemeError("Malformed begin")
        a = args
        while a.cdr != ():
            _eval(a.car, env, output)
            a = a.cdr
        return _eval(a.car, env, output)
    elif name == 'cond':
        clauses = _to_py_list(args)
        if not clauses:
            raise SchemeError("Malformed cond")
        for i, clause in enumerate(clauses):
            if not _is_pair(clause):
                raise SchemeError("Malformed cond clause")
            test = clause.car
            rest = clause.cdr
            if _is_symbol(test) and test.name == 'else':
                if i != len(clauses) - 1:
                    raise SchemeError("else must be last clause")
                exprs = _to_py_list(rest)
                if not exprs:
                    raise SchemeError("Malformed else clause")
                result = UNSPECIFIED
                for e in exprs:
                    result = _eval(e, env, output)
                return result
            else:
                test_val = _eval(test, env, output)
                if test_val is not False:
                    exprs = _to_py_list(rest)
                    if not exprs:
                        return test_val
                    result = UNSPECIFIED
                    for e in exprs:
                        result = _eval(e, env, output)
                    return result
        return UNSPECIFIED
    elif name == 'and':
        exprs = _to_py_list(args)
        if not exprs:
            return True
        result = True
        for e in exprs:
            result = _eval(e, env, output)
            if result is False:
                return False
        return result
    elif name == 'or':
        exprs = _to_py_list(args)
        if not exprs:
            return False
        for e in exprs:
            val = _eval(e, env, output)
            if val is not False:
                return val
        return False
    elif name == 'let':
        if args == ():
            raise SchemeError("Malformed let")
        first = args.car
        rest = args.cdr
        if _is_symbol(first):
            return _eval_named_let(first, rest, env, output)
        else:
            if rest == ():
                raise SchemeError("Empty body")
            if not _is_proper_list(rest):
                raise SchemeError("Malformed let body")
            bindings = _parse_let_bindings(first)
            body = _to_py_list(rest)
            new_frame = {}
            for nm, init in bindings:
                new_frame[nm.name] = _eval(init, env, output)
            inner_env = _Env(new_frame, env)
            return _eval_tail(_Body(body), inner_env, output)
    elif name == 'let*':
        if args == ():
            raise SchemeError("Malformed let*")
        bindings_expr = args.car
        body_exprs = args.cdr
        if body_exprs == ():
            raise SchemeError("Empty body")
        if not _is_proper_list(body_exprs):
            raise SchemeError("Malformed let* body")
        bindings = _parse_let_bindings(bindings_expr)
        body = _to_py_list(body_exprs)
        inner_env = env
        for nm, init in bindings:
            val = _eval(init, inner_env, output)
            inner_env = _Env({nm.name: val}, inner_env)
        return _eval_tail(_Body(body), inner_env, output)
    elif name == 'letrec':
        if args == ():
            raise SchemeError("Malformed letrec")
        bindings_expr = args.car
        body_exprs = args.cdr
        if body_exprs == ():
            raise SchemeError("Empty body")
        if not _is_proper_list(body_exprs):
            raise SchemeError("Malformed letrec body")
        bindings = _parse_let_bindings(bindings_expr)
        body = _to_py_list(body_exprs)
        frame = {nm.name: UNINITIALIZED for nm, _ in bindings}
        inner_env = _Env(frame, env)
        for nm, init in bindings:
            val = _eval(init, inner_env, output)
            inner_env.frame[nm.name] = val
        return _eval_tail(_Body(body), inner_env, output)
    elif name == 'lambda':
        if args == ():
            raise SchemeError("Malformed lambda")
        formals_expr = args.car
        body_exprs = args.cdr
        if body_exprs == ():
            raise SchemeError("Empty body")
        if not _is_proper_list(body_exprs):
            raise SchemeError("Malformed lambda body")
        formals = _parse_formals(formals_expr)
        body = _to_py_list(body_exprs)
        return _Closure(formals, body, env)
    else:
        raise SchemeError(f"Unknown special form: {name}")

def _eval_named_let(let_name, rest, env, output):
    if rest == ():
        raise SchemeError("Malformed named let")
    bindings_expr = rest.car
    body_exprs = rest.cdr
    if body_exprs == ():
        raise SchemeError("Empty body")
    if not _is_proper_list(body_exprs):
        raise SchemeError("Malformed named let body")
    bindings = _parse_let_bindings(bindings_expr)
    body = _to_py_list(body_exprs)
    init_vals = [_eval(init, env, output) for _, init in bindings]
    formals = [nm for nm, _ in bindings]
    formals_norm = ('fixed', formals)
    frame = {let_name.name: UNINITIALIZED}
    inner_env = _Env(frame, env)
    closure = _Closure(formals_norm, body, inner_env)
    inner_env.frame[let_name.name] = closure
    call_env = _make_call_env(closure, init_vals)
    return _eval_tail(_Body(body), call_env, output)


def _eval_tail(expr, env, output):
    """Evaluate expr in tail position. Returns a value. Uses loop for TCO."""
    while True:
        if isinstance(expr, _Body):
            forms = expr.forms
            if not forms:
                raise SchemeError("Empty body")
            internal_defs = []
            for f in forms:
                if _is_pair(f) and _is_symbol(f.car) and f.car.name == 'define':
                    internal_defs.append(f)
            if internal_defs:
                new_frame = {}
                for d in internal_defs:
                    nm = _get_define_name(d)
                    new_frame[nm] = UNINITIALIZED
                inner_env = _Env(new_frame, env)
                for f in forms[:-1]:
                    if _is_pair(f) and _is_symbol(f.car) and f.car.name == 'define':
                        _do_define(f, inner_env, output)
                    else:
                        _eval(f, inner_env, output)
                last = forms[-1]
                if _is_pair(last) and _is_symbol(last.car) and last.car.name == 'define':
                    _do_define(last, inner_env, output)
                    return UNSPECIFIED
                else:
                    expr = last
                    env = inner_env
                    continue
            else:
                for f in forms[:-1]:
                    _eval(f, env, output)
                expr = forms[-1]
                continue

        if _is_int(expr) or _is_str(expr) or _is_bool(expr):
            return expr
        if _is_symbol(expr):
            return env.lookup(expr.name)
        if expr == ():
            raise SchemeError("() is not a procedure")
        if _is_pair(expr):
            if not _is_proper_list(expr):
                raise SchemeError("Dotted form used as application")
            head = expr.car
            rest = expr.cdr
            if _is_symbol(head) and head.name in _SPECIAL_FORMS:
                result = _eval_special_tail(head.name, rest, env, output)
                if isinstance(result, _TCO):
                    expr = result.expr
                    env = result.env
                    continue
                return result
            # Application in tail position
            op = _eval(head, env, output)
            arg_vals = []
            for a in _iter_proper_list(rest):
                arg_vals.append(_eval(a, env, output))
            if op is _APPLY_BUILTIN:
                if len(arg_vals) < 2:
                    raise SchemeError("apply: requires at least 2 arguments")
                f_val = arg_vals[0]
                a_vals = arg_vals[1:-1]
                lst = arg_vals[-1]
                if not _is_proper_list(lst):
                    raise SchemeError("apply: last argument is not a proper list")
                all_args = a_vals + _to_py_list(lst)
                if isinstance(f_val, _Closure):
                    env = _make_call_env(f_val, all_args)
                    expr = _Body(f_val.body)
                    continue
                elif isinstance(f_val, _Builtin):
                    return f_val.func(all_args, output)
                else:
                    raise SchemeError("Not a procedure")
            elif isinstance(op, _Closure):
                env = _make_call_env(op, arg_vals)
                expr = _Body(op.body)
                continue
            elif isinstance(op, _Builtin):
                return op.func(arg_vals, output)
            else:
                raise SchemeError("Not a procedure")
        if expr is UNSPECIFIED:
            return UNSPECIFIED
        return expr


def _eval_special_tail(name, args, env, output):
    """Evaluate a special form in tail position. Returns value or _TCO."""
    if name == 'quote':
        if args == () or args.cdr != ():
            raise SchemeError("Malformed quote")
        return args.car
    elif name == 'define':
        _do_define(args, env, output)
        return UNSPECIFIED
    elif name == 'set!':
        if args == () or args.cdr == () or args.cdr.cdr != ():
            raise SchemeError("Malformed set!")
        name_sym = args.car
        if not _is_symbol(name_sym):
            raise SchemeError("set! name must be a symbol")
        val = _eval(args.cdr.car, env, output)
        env.set(name_sym.name, val)
        return UNSPECIFIED
    elif name == 'if':
        if args == () or args.cdr == ():
            raise SchemeError("Malformed if")
        test_val = _eval(args.car, env, output)
        if test_val is not False:
            return _TCO(args.cdr.car, env)
        else:
            rest = args.cdr.cdr
            if rest == ():
                return UNSPECIFIED
            if rest.cdr != ():
                raise SchemeError("Malformed if")
            return _TCO(rest.car, env)
    elif name == 'begin':
        if args == ():
            raise SchemeError("Malformed begin")
        a = args
        while a.cdr != ():
            _eval(a.car, env, output)
            a = a.cdr
        return _TCO(a.car, env)
    elif name == 'cond':
        clauses = _to_py_list(args)
        if not clauses:
            raise SchemeError("Malformed cond")
        for i, clause in enumerate(clauses):
            if not _is_pair(clause):
                raise SchemeError("Malformed cond clause")
            test = clause.car
            rest = clause.cdr
            if _is_symbol(test) and test.name == 'else':
                if i != len(clauses) - 1:
                    raise SchemeError("else must be last clause")
                exprs = _to_py_list(rest)
                if not exprs:
                    raise SchemeError("Malformed else clause")
                for e in exprs[:-1]:
                    _eval(e, env, output)
                return _TCO(exprs[-1], env)
            else:
                test_val = _eval(test, env, output)
                if test_val is not False:
                    exprs = _to_py_list(rest)
                    if not exprs:
                        return test_val
                    for e in exprs[:-1]:
                        _eval(e, env, output)
                    return _TCO(exprs[-1], env)
        return UNSPECIFIED
    elif name == 'and':
        exprs = _to_py_list(args)
        if not exprs:
            return True
        for e in exprs[:-1]:
            val = _eval(e, env, output)
            if val is False:
                return False
        return _TCO(exprs[-1], env)
    elif name == 'or':
        exprs = _to_py_list(args)
        if not exprs:
            return False
        for e in exprs[:-1]:
            val = _eval(e, env, output)
            if val is not False:
                return val
        return _TCO(exprs[-1], env)
    elif name == 'let':
        if args == ():
            raise SchemeError("Malformed let")
        first = args.car
        rest = args.cdr
        if _is_symbol(first):
            # Named let
            if rest == ():
                raise SchemeError("Malformed named let")
            bindings_expr = rest.car
            body_exprs = rest.cdr
            if body_exprs == ():
                raise SchemeError("Empty body")
            if not _is_proper_list(body_exprs):
                raise SchemeError("Malformed named let body")
            bindings = _parse_let_bindings(bindings_expr)
            body = _to_py_list(body_exprs)
            init_vals = [_eval(init, env, output) for _, init in bindings]
            formals = [nm for nm, _ in bindings]
            formals_norm = ('fixed', formals)
            frame = {first.name: UNINITIALIZED}
            inner_env = _Env(frame, env)
            closure = _Closure(formals_norm, body, inner_env)
            inner_env.frame[first.name] = closure
            call_env = _make_call_env(closure, init_vals)
            return _TCO(_Body(body), call_env)
        else:
            if rest == ():
                raise SchemeError("Empty body")
            if not _is_proper_list(rest):
                raise SchemeError("Malformed let body")
            bindings = _parse_let_bindings(first)
            body = _to_py_list(rest)
            new_frame = {}
            for nm, init in bindings:
                new_frame[nm.name] = _eval(init, env, output)
            inner_env = _Env(new_frame, env)
            return _TCO(_Body(body