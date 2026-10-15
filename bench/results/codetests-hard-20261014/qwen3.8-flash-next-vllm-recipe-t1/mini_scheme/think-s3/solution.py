import sys
sys.setrecursionlimit(300000)
try:
    sys.set_int_max_str_digits(0)
except (AttributeError, ValueError):
    pass


# ===== Data Types =====

_symbol_table = {}
class Symbol:
    __slots__ = ('name',)
    def __new__(cls, name):
        s = _symbol_table.get(name)
        if s is not None:
            return s
        obj = object.__new__(cls)
        obj.name = name
        _symbol_table[name] = obj
        return obj
    def __repr__(self):
        return self.name
    def __hash__(self):
        return hash(('sym', self.name))
    def __eq__(self, other):
        return self is other

class Bool:
    __slots__ = ('val',)
    def __init__(self, val):
        self.val = val
TRUE = Bool(True)
FALSE = Bool(False)

class Nil:
    __slots__ = ()
NIL = Nil()

class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr

class Unspecified:
    __slots__ = ()
UNSPECIFIED = Unspecified()

class Uninitialized:
    __slots__ = ()
UNINITIALIZED = Uninitialized()

class Closure:
    __slots__ = ('formals_type', 'formals_fixed', 'formals_rest', 'formals_lone', 'body', 'env')
    def __init__(self, formals_type, formals_fixed, formals_rest, formals_lone, body, env):
        self.formals_type = formals_type  # 'fixed', 'dotted', 'lone'
        self.formals_fixed = formals_fixed
        self.formals_rest = formals_rest
        self.formals_lone = formals_lone
        self.body = body
        self.env = env

class Builtin:
    __slots__ = ('name', 'func', 'min_args', 'max_args')
    def __init__(self, name, func, min_args, max_args):
        self.name = name
        self.func = func
        self.min_args = min_args
        self.max_args = max_args

class SchemeError(Exception):
    def __init__(self, msg, output=''):
        super().__init__(msg)
        self.output = output

class Frame:
    __slots__ = ('vars', 'parent')
    def __init__(self, vars=None, parent=None):
        self.vars = vars if vars is not None else {}
        self.parent = parent


# ===== Reader =====

class ReaderError(Exception):
    pass

def _int_to_string(n, radix=10):
    if n == 0:
        return '0'
    digits = '0123456789abcdef'
    negative = n < 0
    n = abs(n)
    parts = []
    while n > 0:
        parts.append(digits[n % radix])
        n //= radix
    if negative:
        parts.append('-')
    return ''.join(reversed(parts))


def _is_integer_token(tok):
    if not tok:
        return False
    i = 0
    if tok[0] in '+-':
        i = 1
    if i >= len(tok):
        return False
    while i < len(tok):
        if not ('0' <= tok[i] <= '9'):
            return False
        i += 1
    return True


def _read_source(src):
    """Tokenize and parse source into list of Scheme forms."""
    pos = [0]
    forms = []
    n = len(src)
    while True:
        _skip_ws(src, pos, n)
        if pos[0] >= n:
            break
        ch = src[pos[0]]
        if ch == ')':
            raise ReaderError("unexpected ')'")
        forms.append(_read_one(src, pos, n))
    return forms


def _skip_ws(src, pos, n):
    while pos[0] < n:
        ch = src[pos[0]]
        if ch in ' \t\n\r':
            pos[0] += 1
        elif ch == ';':
            while pos[0] < n and src[pos[0]] != '\n':
                pos[0] += 1
        else:
            break


def _read_one(src, pos, n):
    _skip_ws(src, pos, n)
    if pos[0] >= n:
        raise ReaderError("unexpected end of input")
    ch = src[pos[0]]
    if ch == '(':
        return _read_list(src, pos, n)
    elif ch == ')':
        raise ReaderError("unexpected ')'")
    elif ch == "'":
        pos[0] += 1
        datum = _read_one(src, pos, n)
        return Pair(Symbol('quote'), Pair(datum, NIL))
    elif ch == '"':
        return _read_string(src, pos, n)
    elif ch == '#':
        return _read_hash(src, pos, n)
    else:
        tok = _read_token(src, pos, n)
        if tok is None:
            raise ReaderError("unexpected character")
        return _parse_token(tok)


def _read_token(src, pos, n):
    start = pos[0]
    while pos[0] < n:
        ch = src[pos[0]]
        if ch in ' \t\n\r()";\'':
            break
        pos[0] += 1
    if pos[0] == start:
        return None
    return src[start:pos[0]]


def _parse_token(tok):
    if tok == '#t':
        return TRUE
    if tok == '#f':
        return FALSE
    if tok.startswith('#'):
        raise ReaderError(f"unknown datum starting with #: {tok}")
    if _is_integer_token(tok):
        return int(tok)
    return Symbol(tok)


def _read_hash(src, pos, n):
    pos[0] += 1  # skip '#'
    start = pos[0]
    while pos[0] < n:
        ch = src[pos[0]]
        if ch in ' \t\n\r()";\'':
            break
        pos[0] += 1
    rest = src[start:pos[0]]
    if rest == 't':
        return TRUE
    if rest == 'f':
        return FALSE
    raise ReaderError(f"unknown datum starting with #: #{rest}")


def _read_string(src, pos, n):
    pos[0] += 1  # skip opening "
    parts = []
    while pos[0] < n:
        ch = src[pos[0]]
        if ch == '"':
            pos[0] += 1
            return ''.join(parts)
        elif ch == '\\':
            pos[0] += 1
            if pos[0] >= n:
                raise ReaderError("unterminated string escape")
            ec = src[pos[0]]
            if ec == '"':
                parts.append('"')
            elif ec == '\\':
                parts.append('\\')
            elif ec == 'n':
                parts.append('\n')
            else:
                raise ReaderError(f"invalid escape: \\{ec}")
            pos[0] += 1
        else:
            parts.append(ch)
            pos[0] += 1
    raise ReaderError("unterminated string")


def _read_list(src, pos, n):
    pos[0] += 1  # skip '('
    elements = []
    dot_seen = False
    dot_value = None
    while True:
        _skip_ws(src, pos, n)
        if pos[0] >= n:
            raise ReaderError("unexpected end of input in list")
        ch = src[pos[0]]
        if ch == ')':
            pos[0] += 1
            break
        if ch == '(':
            item = _read_list(src, pos, n)
        elif ch == ')':
            raise ReaderError("unexpected ')'")
        elif ch == "'":
            pos[0] += 1
            datum = _read_one(src, pos, n)
            item = Pair(Symbol('quote'), Pair(datum, NIL))
        elif ch == '"':
            item = _read_string(src, pos, n)
        elif ch == '#':
            item = _read_hash(src, pos, n)
        else:
            tok = _read_token(src, pos, n)
            if tok is None:
                raise ReaderError("unexpected character")
            if tok == '.' and not dot_seen:
                # Check it's exactly '.'
                dot_seen = True
                _skip_ws(src, pos, n)
                if pos[0] >= n:
                    raise ReaderError("unexpected end of input after dot")
                if src[pos[0]] == ')':
                    raise ReaderError("dot not followed by datum")
                dot_value = _read_one(src, pos, n)
                _skip_ws(src, pos, n)
                if pos[0] < n and src[pos[0]] == ')':
                    pos[0] += 1
                    break
                elif pos[0] < n:
                    raise ReaderError("expected ')' after dotted pair")
                else:
                    raise ReaderError("unexpected end of input after dotted pair")
            else:
                item = _parse_token(tok)
                if dot_seen:
                    raise ReaderError("element after dot")
        if dot_seen:
            raise ReaderError("element after dot")
        elements.append(item)
    if dot_seen:
        # Build dotted list
        result = dot_value
        for i in range(len(elements) - 1, -1, -1):
            result = Pair(elements[i], result)
        return result
    # Build proper list
    result = NIL
    for i in range(len(elements) - 1, -1, -1):
        result = Pair(elements[i], result)
    return result


# ===== Utility =====

def _is_pair(x):
    return isinstance(x, Pair)

def _is_proper_list(x):
    while isinstance(x, Pair):
        x = x.cdr
    return x is NIL

def _list_to_py(x):
    result = []
    while isinstance(x, Pair):
        result.append(x.car)
        x = x.cdr
    return result

def _py_to_list(lst):
    result = NIL
    for item in reversed(lst):
        result = Pair(item, result)
    return result

def _truthy(x):
    return x is not FALSE


# ===== Environment =====

def _lookup(name, env):
    frame = env
    while frame is not None:
        if name in frame.vars:
            v = frame.vars[name]
            if v is UNINITIALIZED:
                raise SchemeError(f"uninitialized variable: {name.name}")
            return v
        frame = frame.parent
    raise SchemeError(f"unbound variable: {name.name}")

def _set_binding(name, value, env):
    frame = env
    while frame is not None:
        if name in frame.vars:
            frame.vars[name] = value
            return
        frame = frame.parent
    raise SchemeError(f"set!: unbound variable: {name.name}")


# ===== Interp =====

class Interp:
    def __init__(self):
        self.output = []
        self.globals = Frame()
        self._setup_builtins()

    def _display(self, s):
        self.output.append(s)

    def _format(self, x, write_mode=False):
        parts = []
        stack = [('v', x)]
        while stack:
            tag, item = stack.pop()
            if tag == 's':
                parts.append(item)
            elif tag == 'v':
                if item is NIL:
                    parts.append('()')
                elif isinstance(item, bool):
                    parts.append('#t' if item else '#f')
                elif item is TRUE:
                    parts.append('#t')
                elif item is FALSE:
                    parts.append('#f')
                elif isinstance(item, int):
                    parts.append(_int_to_string(item))
                elif isinstance(item, Symbol):
                    parts.append(item.name)
                elif isinstance(item, str):
                    if write_mode:
                        parts.append('"' + item.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"')
                    else:
                        parts.append(item)
                elif isinstance(item, Unspecified):
                    parts.append('')
                elif isinstance(item, (Closure, Builtin)):
                    parts.append('#<procedure>')
                elif isinstance(item, Pair):
                    # Collect chain iteratively
                    elements = []
                    current = item
                    is_dotted = False
                    tail = None
                    while isinstance(current, Pair):
                        elements.append(current.car)
                        current = current.cdr
                    if current is NIL:
                        pass
                    else:
                        is_dotted = True
                        tail = current
                    # Push in reverse: we want ( e1 e2 ... en [. tail] )
                    stack.append(('s', ')'))
                    if is_dotted:
                        stack.append(('v', tail))
                        stack.append(('s', ' . '))
                    for i in range(len(elements) - 1, -1, -1):
                        stack.append(('v', elements[i]))
                        if i > 0:
                            stack.append(('s', ' '))
                    stack.append(('s', '('))
                else:
                    parts.append(str(item))
        return ''.join(parts)

    def _display_val(self, x):
        return self._format(x, False)

    def _write_val(self, x):
        return self._format(x, True)

    # --- Evaluator ---

    def eval_top(self, expr):
        """Evaluate a top-level form."""
        if isinstance(expr, Pair) and isinstance(expr.car, Symbol):
            head = expr.car.name
            if head == 'define':
                self._eval_define_top(expr.cdr)
                return
            elif head == 'begin':
                forms = _list_to_py(expr.cdr)
                if not forms:
                    raise SchemeError("empty begin")
                for f in forms:
                    self.eval_top(f)
                return
        self.eval_tail(expr, self.globals)

    def _eval_define_top(self, cdr):
        if not _is_pair(cdr):
            raise SchemeError("malformed define")
        target = cdr.car
        rest = cdr.cdr
        if isinstance(target, Symbol):
            # (define name expr)
            if not _is_pair(rest):
                raise SchemeError("malformed define")
            expr = rest.car
            if _is_pair(rest.cdr):
                raise SchemeError("malformed define: extra expressions")
            val = self.eval_expr(expr, self.globals)
            self.globals.vars[target] = val
        elif _is_pair(target):
            # (define (name . formals) body...)
            name = target.car
            if not isinstance(name, Symbol):
                raise SchemeError("malformed define: head not a symbol")
            formals = target.cdr
            if not _is_pair(rest):
                raise SchemeError("malformed define")
            body = _list_to_py(rest)
            if not body:
                raise SchemeError("malformed define: empty body")
            # formals can be NIL (empty list = no params), a symbol, or a pair
            closure = self._make_closure(formals, body, self.globals)
            self.globals.vars[name] = closure
        else:
            raise SchemeError("malformed define")

    def _make_closure(self, formals_spec, body, env):
        if isinstance(formals_spec, Symbol):
            # lone symbol: (lambda args body)
            return Closure('lone', None, None, formals_spec, body, env)
        elif formals_spec is NIL:
            # no params
            return Closure('fixed', [], None, None, body, env)
        elif isinstance(formals_spec, Pair):
            # proper or dotted list
            params = []
            current = formals_spec
            while isinstance(current, Pair):
                p = current.car
                if not isinstance(p, Symbol):
                    raise SchemeError("lambda formals: non-symbol parameter")
                params.append(p)
                current = current.cdr
            if current is NIL:
                return Closure('fixed', params, None, None, body, env)
            elif isinstance(current, Symbol):
                return Closure('dotted', params, current, None, body, env)
            else:
                raise SchemeError("malformed lambda formals")
        else:
            raise SchemeError("malformed lambda formals")

    def _make_call_env(self, closure, args):
        params_env = Frame({}, closure.env)
        if closure.formals_type == 'lone':
            params_env.vars[closure.formals_lone] = _py_to_list(args)
        elif closure.formals_type == 'fixed':
            for p, a in zip(closure.formals_fixed, args):
                params_env.vars[p] = a
        elif closure.formals_type == 'dotted':
            for p, a in zip(closure.formals_fixed, args):
                params_env.vars[p] = a
            remaining = args[len(closure.formals_fixed):]
            params_env.vars[closure.formals_rest] = _py_to_list(remaining)
        return params_env

    def _validate_call(self, proc, nargs, args):
        if isinstance(proc, Closure):
            if proc.formals_type == 'lone':
                return
            elif proc.formals_type == 'fixed':
                if nargs != len(proc.formals_fixed):
                    raise SchemeError(f"wrong number of arguments: expected {len(proc.formals_fixed)}, got {nargs}")
            elif proc.formals_type == 'dotted':
                if nargs < len(proc.formals_fixed):
                    raise SchemeError(f"wrong number of arguments: expected at least {len(proc.formals_fixed)}, got {nargs}")
        elif isinstance(proc, Builtin):
            if nargs < proc.min_args:
                raise SchemeError(f"{proc.name}: too few arguments")
            if proc.max_args is not None and nargs > proc.max_args:
                raise SchemeError(f"{proc.name}: too many arguments")
        else:
            raise SchemeError("not a procedure")

    def eval_expr(self, expr, env):
        """Evaluate in non-tail position."""
        while True:
            if isinstance(expr, int):
                return expr
            if isinstance(expr, (Bool, Unspecified, Nil)):
                return expr
            if isinstance(expr, str):
                return expr
            if isinstance(expr, Symbol):
                return _lookup(expr, env)
            if isinstance(expr, Closure):
                return expr
            if isinstance(expr, Builtin):
                return expr
            if not isinstance(expr, Pair):
                return expr
            # It's a list
            head = expr.car
            if isinstance(head, Symbol):
                name = head.name
                if name == 'quote':
                    cdr = expr.cdr
                    if not _is_pair(cdr):
                        raise SchemeError("malformed quote")
                    return cdr.car
                elif name == 'if':
                    forms = _list_to_py(expr.cdr)
                    if len(forms) < 2:
                        raise SchemeError("malformed if")
                    test_val = self.eval_expr(forms[0], env)
                    if _truthy(test_val):
                        expr = forms[1]
                        continue  # tail: but we're in eval_expr... just loop
                    else:
                        if len(forms) > 2:
                            expr = forms[2]
                            continue
                        else:
                            return UNSPECIFIED
                elif name == 'begin':
                    forms = _list_to_py(expr.cdr)
                    if not forms:
                        raise SchemeError("empty begin")
                    for f in forms[:-1]:
                        self.eval_expr(f, env)
                    expr = forms[-1]
                    continue
                elif name == 'define':
                    self._eval_define_in_body(expr.cdr, env)
                    return UNSPECIFIED
                elif name == 'set!':
                    forms = _list_to_py(expr.cdr)
                    if len(forms) != 2 or not isinstance(forms[0], Symbol):
                        raise SchemeError("malformed set!")
                    val = self.eval_expr(forms[1], env)
                    _set_binding(forms[0], val, env)
                    return UNSPECIFIED
                elif name == 'lambda':
                    return self._eval_lambda(expr.cdr, env)
                elif name == 'cond':
                    return self._eval_cond(expr.cdr, env)
                elif name == 'and':
                    args = _list_to_py(expr.cdr)
                    if not args:
                        return TRUE
                    for a in args[:-1]:
                        v = self.eval_expr(a, env)
                        if not _truthy(v):
                            return FALSE
                    expr = args[-1]
                    continue
                elif name == 'or':
                    args = _list_to_py(expr.cdr)
                    if not args:
                        return FALSE
                    for a in args[:-1]:
                        v = self.eval_expr(a, env)
                        if _truthy(v):
                            return v
                    expr = args[-1]
                    continue
                elif name == 'let':
                    return self._eval_let(expr.cdr, env, 'let')
                elif name == 'let*':
                    return self._eval_let(expr.cdr, env, 'let*')
                elif name == 'letrec':
                    return self._eval_let(expr.cdr, env, 'letrec')
                elif name == 'apply':
                    return self._eval_apply_non_tail(expr.cdr, env)
            # General application
            proc = self.eval_expr(expr.car, env)
            args = []
            cur = expr.cdr
            while isinstance(cur, Pair):
                args.append(self.eval_expr(cur.car, env))
                cur = cur.cdr
            self._validate_call(proc, len(args), args)
            return self._call_proc(proc, args)

    def eval_tail(self, expr, env):
        """Evaluate in tail position. Loops for tail calls."""
        while True:
            if isinstance(expr, int):
                return expr
            if isinstance(expr, (Bool, Unspecified, Nil)):
                return expr
            if isinstance(expr, str):
                return expr
            if isinstance(expr, Symbol):
                return _lookup(expr, env)
            if isinstance(expr, Closure):
                return expr
            if isinstance(expr, Builtin):
                return expr
            if not isinstance(expr, Pair):
                return expr
            head = expr.car
            if isinstance(head, Symbol):
                name = head.name
                if name == 'quote':
                    cdr = expr.cdr
                    if not _is_pair(cdr):
                        raise SchemeError("malformed quote")
                    return cdr.car
                elif name == 'if':
                    forms = _list_to_py(expr.cdr)
                    if len(forms) < 2:
                        raise SchemeError("malformed if")
                    test_val = self.eval_expr(forms[0], env)
                    if _truthy(test_val):
                        expr = forms[1]
                        continue
                    else:
                        if len(forms) > 2:
                            expr = forms[2]
                            continue
                        else:
                            return UNSPECIFIED
                elif name == 'begin':
                    forms = _list_to_py(expr.cdr)
                    if not forms:
                        raise SchemeError("empty begin")
                    for f in forms[:-1]:
                        self.eval_expr(f, env)
                    expr = forms[-1]
                    continue
                elif name == 'define':
                    self._eval_define_in_body(expr.cdr, env)
                    return UNSPECIFIED
                elif name == 'set!':
                    forms = _list_to_py(expr.cdr)
                    if len(forms) != 2 or not isinstance(forms[0], Symbol):
                        raise SchemeError("malformed set!")
                    val = self.eval_expr(forms[1], env)
                    _set_binding(forms[0], val, env)
                    return UNSPECIFIED
                elif name == 'lambda':
                    return self._eval_lambda(expr.cdr, env)
                elif name == 'cond':
                    return self._eval_cond(expr.cdr, env)
                elif name == 'and':
                    args = _list_to_py(expr.cdr)
                    if not args:
                        return TRUE
                    for a in args[:-1]:
                        v = self.eval_expr(a, env)
                        if not _truthy(v):
                            return FALSE
                    expr = args[-1]
                    continue
                elif name == 'or':
                    args = _list_to_py(expr.cdr)
                    if not args:
                        return FALSE
                    for a in args[:-1]:
                        v = self.eval_expr(a, env)
                        if _truthy(v):
                            return v
                    expr = args[-1]
                    continue
                elif name == 'let':
                    res = self._eval_let(expr.cdr, env, 'let')
                    if isinstance(res, _TailCall):
                        expr = res.expr
                        env = res.env
                        continue
                    return res
                elif name == 'let*':
                    res = self._eval_let(expr.cdr, env, 'let*')
                    if isinstance(res, _TailCall):
                        expr = res.expr
                        env = res.env
                        continue
                    return res
                elif name == 'letrec':
                    res = self._eval_let(expr.cdr, env, 'letrec')
                    if isinstance(res, _TailCall):
                        expr = res.expr
                        env = res.env
                        continue
                    return res
                elif name == 'apply':
                    res = self._eval_apply_tail(expr.cdr, env)
                    if isinstance(res, _TailCall):
                        expr = res.expr
                        env = res.env
                        continue
                    return res
            # General application (tail position)
            proc = self.eval_expr(expr.car, env)
            args = []
            cur = expr.cdr
            while isinstance(cur, Pair):
                args.append(self.eval_expr(cur.car, env))
                cur = cur.cdr
            self._validate_call(proc, len(args), args)
            if isinstance(proc, Closure):
                new_env = self._make_call_env(proc, args)
                body = proc.body
                # Handle internal definitions
                new_env, real_body = self._process_body(body, new_env)
                for f in real_body[:-1]:
                    self.eval_expr(f, new_env)
                expr = real_body[-1]
                env = new_env
                continue
            elif isinstance(proc, Builtin):
                return proc.func(args)
            else:
                raise SchemeError("not a procedure")

    def _call_proc(self, proc, args):
        if isinstance(proc, Closure):
            new_env = self._make_call_env(proc, args)
            body = proc.body
            new_env, real_body = self._process_body(body, new_env)
            for f in real_body[:-1]:
                self.eval_expr(f, new_env)
            return self.eval_tail(real_body[-1], new_env)
        elif isinstance(proc, Builtin):
            return proc.func(args)
        else:
            raise SchemeError("not a procedure")

    def _eval_lambda(self, cdr, env):
        if not _is_pair(cdr):
            raise SchemeError("malformed lambda")
        formals = cdr.car
        body = cdr.cdr
        body_forms = _list_to_py(body)
        if not body_forms:
            raise SchemeError("empty lambda body")
        return self._make_closure(formals, body_forms, env)

    def _eval_define_in_body(self, cdr, env):
        """Handle define when encountered during body evaluation (non-internal)."""
        if not _is_pair(cdr):
            raise SchemeError("malformed define")
        target = cdr.car
        rest = cdr.cdr
        if isinstance(target, Symbol):
            if not _is_pair(rest):
                raise SchemeError("malformed define")
            val = self.eval_expr(rest.car, env)
            # If the variable is already bound in this frame, update it
            if target in env.vars:
                env.vars[target] = val
            else:
                self.globals.vars[target] = val
        elif _is_pair(target):
            name = target.car
            if not isinstance(name, Symbol):
                raise SchemeError("malformed define")
            formals = target.cdr
            if not _is_pair(rest):
                raise SchemeError("malformed define")
            body = _list_to_py(rest)
            if not body:
                raise SchemeError("malformed define")
            closure = self._make_closure(formals, body, env)
            if name in env.vars:
                env.vars[name] = closure
            else:
                self.globals.vars[name] = closure
        else:
            raise SchemeError("malformed define")

    def _process_body(self, body, env):
        """Process internal definitions. Returns (env, real_body)."""
        # Check if there are any internal defines
        defines = []
        for form in body:
            if isinstance(form, Pair) and isinstance(form.car, Symbol) and form.car.name == 'define':
                defines.append(form)
        if not defines:
            return env, body
        # Collect all defined names
        new_names = set()
        for form in defines:
            cdr = form.cdr
            if _is_pair(cdr):
                target = cdr.car
                if isinstance(target, Symbol):
                    new_names.add(target)
                elif isinstance(target, Pair):
                    if isinstance(target.car, Symbol):
                        new_names.add(target.car)
        if not new_names:
            return env, body
        # Create a new frame with these names UNINITIALIZED
        new_vars = {name: UNINITIALIZED for name in new_names}
        # Also check if any are already in this frame (duplicates) - just override
        new_frame = Frame(new_vars, env)
        # Rewrite define forms to be handled during evaluation
        real_body = []
        for form in body:
            if isinstance(form, Pair) and isinstance(form.car, Symbol) and form.car.name == 'define':
                cdr = form.cdr
                if _is_pair(cdr):
                    target = cdr.car
                    rest = cdr.cdr
                    if isinstance(target, Symbol):
                        if _is_pair(rest):
                            # (define name expr) → (set! name expr) but into new_frame
                            real_body.append(('set_internal', target, rest.car))
                        else:
                            raise SchemeError("malformed define")
                    elif isinstance(target, Pair):
                        name = target.car
                        formals = target.cdr
                        if not _is_pair(rest):
                            raise SchemeError("malformed define")
                        body_forms = _list_to_py(rest)
                        if not body_forms:
                            raise SchemeError("malformed define")
                        # Create lambda form
                        real_body.append(('def_internal', name, formals, body_forms))
                    else:
                        raise SchemeError("malformed define")
                else:
                    raise SchemeError("malformed define")
            else:
                real_body.append(form)
        return new_frame, real_body

    def _eval_body_forms(self, forms, env):
        """Evaluate body forms. Last form is in tail position. Returns value or _TailCall."""
        for form in forms[:-1]:
            self._eval_body_form(form, env)
        # Last form in tail position
        return self._eval_body_form_tail(forms[-1], env)

    def _eval_body_form(self, form, env):
        """Evaluate a non-last body form (which might be an internal define marker)."""
        if isinstance(form, tuple):
            if form[0] == 'set_internal':
                name = form[1]
                expr = form[2]
                val = self.eval_expr(expr, env)
                env.vars[name] = val
            elif form[0] == 'def_internal':
                name = form[1]
                formals = form[2]
                body = form[3]
                closure = self._make_closure(formals, body, env)
                env.vars[name] = closure
            return
        self.eval_expr(form, env)

    def _eval_body_form_tail(self, form, env):
        """Evaluate last body form in tail position."""
        if isinstance(form, tuple):
            if form[0] == 'set_internal':
                name = form[1]
                expr = form[2]
                val = self.eval_expr(expr, env)
                env.vars[name] = val
                return UNSPECIFIED
            elif form[0] == 'def_internal':
                name = form[1]
                formals = form[2]
                body = form[3]
                closure = self._make_closure(formals, body, env)
                env.vars[name] = closure
                return UNSPECIFIED
        return _TailCall(form, env)

    def _eval_let(self, cdr, env, kind):
        if not _is_pair(cdr):
            raise SchemeError("malformed let")
        bindings_spec = cdr.car
        body = cdr.cdr
        body_forms = _list_to_py(body)
        if not body_forms:
            raise SchemeError("empty let body")

        # Check for named let
        if isinstance(bindings_spec, Symbol):
            return self._eval_named_let(cdr, env)

        # Parse bindings
        bindings = []
        cur = bindings_spec
        while isinstance(cur, Pair):
            b = cur.car
            if not _is_pair(b) or not isinstance(b.car, Symbol):
                raise SchemeError("malformed let binding")
            var = b.car
            rest_b = b.cdr
            if not _is_pair(rest_b):
                raise SchemeError("malformed let binding: missing init")
            init = rest_b.car
            if _is_pair(rest_b.cdr):
                raise SchemeError("malformed let binding: extra expressions")
            bindings.append((var, init))
            cur = cur.cdr
        if cur is not NIL:
            raise SchemeError("malformed let bindings")

        if kind == 'let':
            # All inits in outer scope
            vals = []
            for var, init in bindings:
                vals.append(self.eval_expr(init, env))
            new_vars = {var: val for (var, init), val in zip(bindings, vals)}
            new_frame = Frame(new_vars, env)
        elif kind == 'let*':
            new_frame = Frame({}, env)
            for var, init in bindings:
                val = self.eval_expr(init, new_frame)
                new_frame.vars[var] = val
        elif kind == 'letrec':
            new_vars = {var: UNINITIALIZED for var, init in bindings}
            new_frame = Frame(new_vars, env)
            for var, init in bindings:
                val = self.eval_expr(init, new_frame)
                new_frame.vars[var] = val

        # Process internal definitions
        proc_env, real_body = self._process_body(body_forms, new_frame)
        result = self._eval_body_forms(real_body, proc_env)
        return result

    def _eval_named_let(self, cdr, env):
        # cdr.car is the name, but wait - let me re-check the structure
        # Actually for named let, the structure after 'let' is: name bindings body
        # But _eval_let receives cdr which is the whole thing after 'let'
        # Let me redo: for named let, cdr is (name ((v init)...) body...)
        name = None
        # Actually I passed cdr to _eval_named_let but it was already past the name check
        # Let me fix: in _eval_let, if bindings_spec is a Symbol, it's the name
        # cdr.car = name, cdr.cdr.car = bindings, cdr.cdr.cdr = body
        # Wait no, cdr is (name bindings body...) as a list
        # Actually in _eval_let: cdr = the cdr of the let form = (name ((v init)...) body...)
        # if bindings_spec (= cdr.car) is a Symbol, it's the name
        # Then we need cdr.cdr.car for bindings and cdr.cdr.cdr for body
        pass  # handled differently below

    def _eval_apply_non_tail(self, cdr, env):
        forms = _list_to_py(cdr)
        if len(forms) < 2:
            raise SchemeError("apply: needs at least 2 arguments")
        proc = self.eval_expr(forms[0], env)
        rest_args = [self.eval_expr(f, env) for f in forms[1:-1]]
        lst = self.eval_expr(forms[-1], env)
        if not _is_proper_list(lst):
            raise SchemeError("apply: last argument must be a proper list")
        final_args = rest_args + _list_to_py(lst)
        if isinstance(proc, Closure):
            self._validate_call(proc, len(final_args), final_args)
            new_env = self._make_call_env(proc, final_args)
            body = proc.body
            new_env, real_body = self._process_body(body, new_env)
            for f in real_body[:-1]:
                self.eval_expr(f, new_env)
            return self.eval_tail(real_body[-1], new_env)
        elif isinstance(proc, Builtin):
            self._validate_call(proc, len(final_args), final_args)
            return proc.func(final_args)
        else:
            raise SchemeError("apply: first argument is not a procedure")

    def _eval_apply_tail(self, cdr, env):
        forms = _list_to_py(cdr)
        if len(forms) < 2:
            raise SchemeError("apply: needs at least 2 arguments")
        proc = self.eval_expr(forms[0], env)
        rest_args = [self.eval_expr(f, env) for f in forms[1:-1]]
        lst = self.eval_expr(forms[-1], env)
        if not _is_proper_list(lst):
            raise SchemeError("apply: last argument must be a proper list")
        final_args = rest_args + _list_to_py(lst)
        if isinstance(proc, Closure):
            self._validate_call(proc, len(final_args), final_args)
            new_env = self._make_call_env(proc, final_args)
            body = proc.body
            new_env, real_body = self._process_body(body, new_env)
            for f in real_body[:-1]:
                self.eval_expr(f, new_env)
            return _TailCall(real_body[-1], new_env)
        elif isinstance(proc, Builtin):
            self._validate_call(proc, len(final_args), final_args)
            return proc.func(final_args)
        else:
            raise SchemeError("apply: first argument is not a procedure")

    def _eval_cond(self, cdr, env):
        clauses = _list_to_py(cdr)
        for clause in clauses:
            if not isinstance(clause, Pair):
                raise SchemeError("malformed cond clause")
            parts = _list_to_py(clause)
            if not parts:
                raise SchemeError("empty cond clause")
            test = parts[0]
            exprs = parts[1:]
            if isinstance(test, Symbol) and test.name == 'else':
                # else clause - always true
                if not exprs:
                    return TRUE
                for e in exprs[:-1]:
                    self.eval_expr(e, env)
                return self.eval_tail(exprs[-1], env)
            else:
                test_val = self.eval_expr(test, env)
                if _truthy(test_val):
                    if not exprs:
                        return test_val
                    for e in exprs[:-1]:
                        self.eval_expr(e, env)
                    return self.eval_tail(exprs[-1], env)
        return UNSPECIFIED

    # --- Builtins ---

    def _setup_builtins(self):
        g = self.globals.vars

        def make_builtin(name, func, min_args, max_args=None):
            g[Symbol(name)] = Builtin(name, func, min_args, max_args)

        # Arithmetic
        def _check_int(x):
            if isinstance(x, bool):
                raise SchemeError("expected integer")
            if not isinstance(x, int):
                raise SchemeError("expected integer")
            return x

        def _fn_add(args):
            result = 0
            for a in args:
                _check_int(a)
                result += a
            return result

        def _fn_sub(args):
            if not args:
                raise SchemeError("- needs at least 1 argument")
            _check_int(args[0])
            if len(args) == 1:
                return -args[0]
            result = args[0]
            for a in args[1:]:
                _check_int(a)
                result -= a
            return result

        def _fn_mul(args):
            result = 1
            for a in args:
                _check_int(a)
                result *= a
            return result

        def _fn_quotient(args):
            if len(args) != 2:
                raise SchemeError("quotient needs 2 arguments")
            a, b = _check_int(args[0]), _check_int(args[1])
            if b == 0:
                raise SchemeError("division by zero")
            return _quotient(a, b)

        def _fn_remainder(args):
            if len(args) != 2:
                raise SchemeError("remainder needs 2 arguments")
            a, b = _check_int(args[0]), _check_int(args[1])
            if b == 0:
                raise SchemeError("division by zero")
            return _remainder(a, b)

        def _fn_modulo(args):
            if len(args) != 2:
                raise SchemeError("modulo needs 2 arguments")
            a, b = _check_int(args[0]), _check_int(args[1])
            if b == 0:
                raise SchemeError("division by zero")
            return _modulo(a, b)

        def _quotient(a, b):
            # Truncate toward zero
            q = abs(a) // abs(b)
            if (a < 0) != (b < 0):
                q = -q
            return q

        def _remainder(a, b):
            return a - _quotient(a, b) * b

        def _modulo(a, b):
            r = _remainder(a, b)
            if r == 0:
                return 0
            if (r < 0) != (b < 0):
                r += b
            return r

        def _fn_num_to_str(args):
            if len(args) == 1:
                n = _check_int(args[0])
                return _int_to_string(n, 10)
            elif len(args) == 2:
                n = _check_int(args[0])
                r = _check_int(args[1])
                if r not in (2, 8, 10, 16):
                    raise SchemeError("invalid radix")
                return _int_to_string(n, r)
            else:
                raise SchemeError("number->string: wrong number of args")

        def _fn_eq(args):
            if not args:
                raise SchemeError("= needs at least 1 argument")
            for a in args:
                _check_int(a)
            for i in range(1, len(args)):
                if args[i] != args[i-1]:
                    return FALSE
            return TRUE

        def _fn_lt(args):
            if not args:
                raise SchemeError("< needs at least 1 argument")
            for a in args:
                _check_int(a)
            for i in range(1, len(args)):
                if not (args[i-1] < args[i]):
                    return FALSE
            return TRUE

        def _fn_gt(args):
            if not args:
                raise SchemeError("> needs at least 1 argument")
            for a in args:
                _check_int(a)
            for i in range(1, len(args)):
                if not (args[i-1] > args[i]):
                    return FALSE
            return TRUE

        def _fn_le(args):
            if not args:
                raise SchemeError("<= needs at least 1 argument")
            for a in args:
                _check_int(a)
            for i in range(1, len(args)):
                if not (args[i-1] <= args[i]):
                    return FALSE
            return TRUE

        def _fn_ge(args):
            if not args:
                raise SchemeError(">= needs at least 1 argument")
            for a in args:
                _check_int(a)
            for i in range(1, len(args)):
                if not (args[i-1] >= args[i]):
                    return FALSE
            return TRUE

        make_builtin('+', _fn_add, 0)
        make_builtin('-', _fn_sub, 1)
        make_builtin('*', _fn_mul, 0)
        make_builtin('quotient', _fn_quotient, 2, 2)
        make_builtin('remainder', _fn_remainder, 2, 2)
        make_builtin('modulo', _fn_modulo, 2, 2)
        make_builtin('=', _fn_eq, 1)
        make_builtin('<', _fn_lt, 1)
        make_builtin('>', _fn_gt, 1)
        make_builtin('<=', _fn_le, 1)
        make_builtin('>=', _fn_ge, 1)
        make_builtin('number->string', _fn_num_to_str, 1, 2)

        # List operations
        def _fn_cons(args):
            if len(args) != 2:
                raise SchemeError("cons needs 2 arguments")
            return Pair(args[0], args[1])

        def _fn_car(args):
            if len(args) != 1:
                raise SchemeError("car needs 1 argument")
            p = args[0]
            if not isinstance(p, Pair):
                raise SchemeError("car: not a pair")
            return p.car

        def _fn_cdr(args):
            if len(args) != 1:
                raise SchemeError("cdr needs 1 argument")
            p = args[0]
            if not isinstance(p, Pair):
                raise SchemeError("cdr: not a pair")
            return p.cdr

        def _fn_list(args):
            return _py_to_list(args)

        def _fn_null(args):
            return TRUE if args[0] is NIL else FALSE

        def _fn_pair(args):
            return TRUE if isinstance(args[0], Pair) else FALSE

        def _fn_listp(args):
            return TRUE if _is_proper_list(args[0]) else FALSE

        def _fn_length(args):
            x = args[0]
            count = 0
            while isinstance(x, Pair):
                count += 1
                x = x.cdr
            if x is not NIL:
                raise SchemeError("length: not a proper list")
            return count

        def _fn_append(args):
            if not args:
                return NIL
            result_list = []
            for a in args[:-1]:
                if not _is_proper_list(a):
                    raise SchemeError("append: not a proper list")
                result_list.extend(_list_to_py(a))
            last = args[-1]
            result = last
            for item in reversed(result_list):
                result = Pair(item, result)
            return result

        def _fn_reverse(args):
            x = args[0]
            items = []
            while isinstance(x, Pair):
                items.append(x.car)
                x = x.cdr
            if x is not NIL:
                raise SchemeError("reverse: not a proper list")
            return _py_to_list(items)

        def _fn_apply_builtin(args):
            # apply as a callable builtin (when not in special form position)
            # This handles cases like passing apply to something
            # But normally apply is handled as a special form in the evaluator
            if len(args) < 2:
                raise SchemeError("apply needs at least 2 arguments")
            proc = args[0]
            rest = list(args[1:-1])
            lst = args[-1]
            if not _is_proper_list(lst):
                raise SchemeError("apply: last argument must be a proper list")
            final_args = rest + _list_to_py(lst)
            if isinstance(proc, Closure):
                self._validate_call(proc, len(final_args), final_args)
                return self._call_proc(proc, final_args)
            elif isinstance(proc, Builtin):
                self._validate_call(proc, len(final_args), final_args)
                return proc.func(final_args)
            else:
                raise SchemeError("apply: not a procedure")

        make_builtin('cons', _fn_cons, 2, 2)
        make_builtin('car', _fn_car, 1, 1)
        make_builtin('cdr', _fn_cdr, 1, 1)
        make_builtin('list', _fn_list, 0)
        make_builtin('null?', _fn_null, 1, 1)
        make_builtin('pair?', _fn_pair, 1, 1)
        make_builtin('list?', _fn_listp, 1, 1)
        make_builtin('length', _fn_length, 1, 1)
        make_builtin('append', _fn_append, 0)
        make_builtin('reverse', _fn_reverse, 1, 1)
        make_builtin('apply', _fn_apply_builtin, 2)

        # Equality and predicates
        def _scheme_eq(a, b):
            if isinstance(a, Symbol):
                return a is b
            if isinstance(a, Bool):
                return a is b
            if isinstance(a, int) and isinstance(b, int):
                return a == b
            if a is NIL:
                return b is NIL
            if isinstance(a, bool) and isinstance(b, bool):
                return a is b
            return a is b

        def _fn_eqq(args):
            return TRUE if _scheme_eq(args[0], args[1]) else FALSE

        def _scheme_equal(a, b):
            # iterative
            stack = [(a, b)]
            while stack:
                x, y = stack.pop()
                if isinstance(x, Pair) and isinstance(y, Pair):
                    stack.append((x.cdr, y.cdr))
                    stack.append((x.car, y.car))
                elif isinstance(x, str) and isinstance(y, str):
                    if x != y:
                        return False
                else:
                    if not _scheme_eq(x, y):
                        return False
            return True

        def _fn_equal(args):
            return TRUE if _scheme_equal(args[0], args[1]) else FALSE

        def _fn_not(args):
            return TRUE if args[0] is FALSE else FALSE

        def _fn_number(args):
            x = args[0]
            if isinstance(x, bool):
                return FALSE
            return TRUE if isinstance(x, int) else FALSE

        def _fn_symbol(args):
            return TRUE if isinstance(args[0], Symbol) else FALSE

        def _fn_string(args):
            return TRUE if isinstance(args[0], str) else FALSE

        def _fn_procedure(args):
            return TRUE if isinstance(args[0], (Closure, Builtin)) else FALSE

        def _fn_string_append(args):
            result = []
            for a in args:
                if not isinstance(a, str):
                    raise SchemeError("string-append: not a string")
                result.append(a)
            return ''.join(result)

        make_builtin('eq?', _fn_eqq, 2, 2)
        make_builtin('equal?', _fn_equal, 2, 2)
        make_builtin('not', _fn_not, 1, 1)
        make_builtin('number?', _fn_number, 1, 1)
        make_builtin('symbol?', _fn_symbol, 1, 1)
        make_builtin('string?', _fn_string, 1, 1)
        make_builtin('procedure?', _fn_procedure, 1, 1)
        make_builtin('string-append', _fn_string_append, 0)

        # Output and errors
        def _fn_display(args):
            self._display(self._display_val(args[0]))
            return UNSPECIFIED

        def _fn_newline(args):
            self._display('\n')
            return UNSPECIFIED

        def _fn_error(args):
            if not args:
                raise SchemeError("error called with no arguments")
            msg = args[0]
            if isinstance(msg, str):
                parts = [msg]
            else:
                parts = [self._write_val(msg)]
            for irritant in args[1:]:
                parts.append(' ')
                parts.append(self._write_val(irritant))
            raise SchemeError(''.join(parts))

        make_builtin('display', _fn_display, 1, 1)
        make_builtin('newline', _fn_newline, 0, 0)
        make_builtin('error', _fn_error, 1)


class _TailCall:
    __slots__ = ('expr', 'env')
    def __init__(self, expr, env):
        self.expr = expr
        self.env = env


# Named let implementation (fix the stub)
def _eval_named_let(self, cdr, env):
    # cdr = (name ((v init)...) body...)
    name = cdr.car  # Symbol
    rest = cdr.cdr
    if not _is_pair(rest):
        raise SchemeError("malformed named let")
    bindings_spec = rest.car
    body_cdr = rest.cdr
    body_forms = _list_to_py(body_cdr)
    if not body_forms:
        raise SchemeError("empty let body")

    # Parse bindings
    bindings = []
    cur = bindings_spec
    while isinstance(cur, Pair):
        b = cur.car
        if not _is_pair(b) or not isinstance(b.car, Symbol):
            raise SchemeError("malformed let binding")
        var = b.car
        rest_b = b.cdr
        if not _is_pair(rest_b):
            raise SchemeError("malformed let binding: missing init")
        init = rest_b.car
        bindings.append((var, init))
        cur = cur.cdr

    # Evaluate inits in outer scope
    init_vals = []
    for var, init in bindings:
        init_vals.append(self.eval_expr(init, env))

    # Create a recursive procedure
    params = [var for var, init in bindings]
    # Create frame for letrec-like binding
    new_vars = {name: UNINITIALIZED}
    outer_frame = Frame(new_vars, env)

    # Create closure
    closure = Closure('fixed', params, None, None, body_forms, outer_frame)
    outer_frame.vars[name] = closure

    # Call it with init values - tail position
    new_env = Frame({p: v for p, v in zip(params, init_vals)}, outer_frame)
    # Handle internal definitions in the body
    proc_env, real_body = self._process_body(body_forms, new_env)
    result = self._eval_body_forms(real_body, proc_env)
    return result

# Monkey-patch the method
Interp._eval_named_let = _eval_named_let


# ===== Main API =====

def run(source: str) -> str:
    interp = Interp()
    # Read phase
    try:
        forms = _read_source(source)
    except ReaderError as e:
        err = SchemeError(str(e))
        err.output = ''
        raise err
    except SchemeError as e:
        e.output = ''
        raise
    except Exception as e:
        err = SchemeError(str(e))
        err.output = ''
        raise err

    # Eval phase
    try:
        for form in forms:
            interp.eval_top(form)
    except SchemeError as e:
        e.output = ''.join(interp.output)
        raise
    except RecursionError:
        err = SchemeError("maximum recursion depth exceeded")
        err.output = ''.join(interp.output)
        raise err
    except Exception as e:
        err = SchemeError(str(e))
        err.output = ''.join(interp.output)
        raise err

    return ''.join(interp.output)
