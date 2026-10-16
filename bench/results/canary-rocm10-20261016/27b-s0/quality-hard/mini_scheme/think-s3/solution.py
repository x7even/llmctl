import sys

try:
    sys.set_int_max_str_digits(0)
except (AttributeError, ValueError):
    pass

sys.setrecursionlimit(200000)


class SchemeError(Exception):
    def __init__(self, msg, output=''):
        super().__init__(msg)
        self.output = output


# ─── Data types ───────────────────────────────────────────────────────────────

class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr

class Symbol:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name

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

UNSPECIFIED = object()
UNINITIALIZED = object()

# ─── Output buffer ────────────────────────────────────────────────────────────

_output = []

# ─── Reader ───────────────────────────────────────────────────────────────────

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
            chars = []
            while i < n:
                if source[i] == '\\' and i + 1 < n:
                    nxt = source[i + 1]
                    if nxt == '"':
                        chars.append('"')
                        i += 2
                    elif nxt == '\\':
                        chars.append('\\')
                        i += 2
                    elif nxt == 'n':
                        chars.append('\n')
                        i += 2
                    else:
                        raise SchemeError("invalid escape sequence")
                elif source[i] == '"':
                    i += 1
                    break
                else:
                    chars.append(source[i])
                    i += 1
            else:
                raise SchemeError("unterminated string")
            tokens.append(('STR', ''.join(chars)))
        else:
            start = i
            while i < n and source[i] not in ' \t\n\r()"\'':
                i += 1
            tokens.append(source[start:i])
    tokens.append('EOF')
    return tokens


def _is_int_token(tok):
    if not tok:
        return False
    i = 0
    if tok[0] in '+-':
        i = 1
    if i >= len(tok):
        return False
    return all(c in '0123456789' for c in tok[i:])


def _read_atom(tok):
    if tok == '.':
        return '.'
    if tok == '#t':
        return True
    if tok == '#f':
        return False
    if tok.startswith('#'):
        raise SchemeError(f"invalid token: {tok}")
    if _is_int_token(tok):
        return int(tok)
    return Symbol(tok)


def _read_form(tokens, i):
    tok = tokens[i]
    if tok == 'EOF':
        raise SchemeError("unexpected end of input")
    if tok == '(':
        return _read_list(tokens, i + 1)
    if tok == ')':
        raise SchemeError("unexpected )")
    if tok == "'":
        i += 1
        if i >= len(tokens) or tokens[i] in ('EOF', ')'):
            raise SchemeError("' not followed by a datum")
        datum, i = _read_form(tokens, i)
        return (Pair(Symbol('quote'), Pair(datum, ())), i)
    if isinstance(tok, tuple) and tok[0] == 'STR':
        return (tok[1], i + 1)
    return (_read_atom(tok), i + 1)


def _read_list(tokens, i):
    elements = []
    while True:
        tok = tokens[i]
        if tok == 'EOF':
            raise SchemeError("unbalanced (")
        if tok == ')':
            if not elements:
                return ((), i + 1)
            result = ()
            for el in reversed(elements):
                result = Pair(el, result)
            return (result, i + 1)
        if tok == '(':
            form, i = _read_list(tokens, i + 1)
            elements.append(form)
        elif tok == "'":
            form, i = _read_form(tokens, i)
            elements.append(form)
        elif tok == '.':
            if not elements:
                raise SchemeError("dot must be preceded by at least one element")
            i += 1
            if i >= len(tokens) or tokens[i] in ('EOF', ')'):
                raise SchemeError("dot must be followed by a datum")
            dot_val, i = _read_form(tokens, i)
            if i >= len(tokens) or tokens[i] != ')':
                raise SchemeError("expected ) after dotted tail")
            result = dot_val
            for el in reversed(elements):
                result = Pair(el, result)
            return (result, i + 1)
        else:
            elements.append(_read_atom(tok))
            i += 1


def _read_all(source):
    tokens = _tokenize(source)
    forms = []
    i = 0
    while tokens[i] != 'EOF':
        form, i = _read_form(tokens, i)
        forms.append(form)
    return forms

# ─── Environment ──────────────────────────────────────────────────────────────

class Env:
    __slots__ = ('frame', 'parent')
    def __init__(self, frame, parent=None):
        self.frame = frame
        self.parent = parent

    def lookup(self, name):
        e = self
        while e:
            if name in e.frame:
                return e.frame[name]
            e = e.parent
        raise SchemeError(f"unbound variable: {name}")

    def set(self, name, value):
        e = self
        while e:
            if name in e.frame:
                e.frame[name] = value
                return
            e = e.parent
        raise SchemeError(f"unbound variable: {name}")

    def define(self, name, value):
        self.frame[name] = value

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _is_proper_list(x):
    if x == ():
        return True
    if not isinstance(x, Pair):
        return False
    cur = x
    while isinstance(cur, Pair):
        cur = cur.cdr
    return cur == ()


def _pair_to_list(p):
    if p == ():
        return []
    if not isinstance(p, Pair):
        raise SchemeError("expected a list")
    result = []
    cur = p
    while isinstance(cur, Pair):
        result.append(cur.car)
        cur = cur.cdr
    if cur != ():
        raise SchemeError("expected a proper list")
    return result


def _list_to_pair(lst):
    result = ()
    for item in reversed(lst):
        result = Pair(item, result)
    return result


def _is_procedure(x):
    return isinstance(x, (Closure, Builtin))


def _is_self_evaluating(x):
    return isinstance(x, (int, str)) or x is True or x is False


def _check_uninit(val, name):
    if val is UNINITIALIZED:
        raise SchemeError(f"uninitialized variable: {name}")
    return val


def _is_define_form(form):
    if not isinstance(form, Pair):
        return False
    if form.car is None:
        return False
    if not isinstance(form.car, Symbol):
        return False
    return form.car.name == 'define'


def _get_define_name(form):
    rest = form.cdr
    if not isinstance(rest, Pair):
        raise SchemeError("malformed define")
    first = rest.car
    if isinstance(first, Symbol):
        return first.name
    elif isinstance(first, Pair):
        if not isinstance(first.car, Symbol):
            raise SchemeError("malformed define")
        return first.car.name
    else:
        raise SchemeError("malformed define")


def _parse_define(form):
    rest = form.cdr
    if not isinstance(rest, Pair):
        raise SchemeError("malformed define")
    first = rest.car
    if isinstance(first, Symbol):
        name = first.name
        expr = rest.cdr
        if not isinstance(expr, Pair):
            raise SchemeError("malformed define")
        return (name, expr.car, expr.cdr)
    elif isinstance(first, Pair):
        if not isinstance(first.car, Symbol):
            raise SchemeError("malformed define")
        name = first.car.name
        formals = _parse_formals(first.cdr)
        body = _pair_to_list(rest.cdr)
        if not body:
            raise SchemeError("empty body")
        return (name, formals, body)
    else:
        raise SchemeError("malformed define")


def _parse_formals(formals):
    if isinstance(formals, Symbol):
        return formals.name
    if formals == ():
        return []
    if isinstance(formals, Pair):
        if _is_proper_list(formals):
            syms = []
            cur = formals
            while cur != ():
                if not isinstance(cur.car, Symbol):
                    raise SchemeError("formal parameter must be a symbol")
                syms.append(cur.car.name)
                cur = cur.cdr
            return syms
        else:
            fixed = []
            cur = formals
            while isinstance(cur.cdr, Pair):
                if not isinstance(cur.car, Symbol):
                    raise SchemeError("formal parameter must be a symbol")
                fixed.append(cur.car.name)
                cur = cur.cdr
            if not isinstance(cur.car, Symbol):
                raise SchemeError("formal parameter must be a symbol")
            fixed.append(cur.car.name)
            rest_sym = cur.cdr
            if not isinstance(rest_sym, Symbol):
                raise SchemeError("rest parameter must be a symbol")
            return (fixed, rest_sym.name)
    raise SchemeError("invalid formals")


def _bind_closure_args(closure, arg_vals):
    formals = closure.formals
    parent = closure.env
    if isinstance(formals, list):
        if len(formals) != len(arg_vals):
            raise SchemeError("wrong number of arguments")
        frame = {}
        for nm, v in zip(formals, arg_vals):
            frame[nm] = v
        return Env(frame, parent)
    elif isinstance(formals, tuple):
        fixed, rest_name = formals
        if len(arg_vals) < len(fixed):
            raise SchemeError("wrong number of arguments")
        frame = {}
        for nm, v in zip(fixed, arg_vals[:len(fixed)]):
            frame[nm] = v
        frame[rest_name] = _list_to_pair(arg_vals[len(fixed):])
        return Env(frame, parent)
    elif isinstance(formals, str):
        frame = {formals: _list_to_pair(arg_vals)}
        return Env(frame, parent)
    raise SchemeError("invalid formals")


def _prepare_body(body, env):
    internal_names = []
    for form in body:
        if _is_define_form(form):
            nm = _get_define_name(form)
            internal_names.append(nm)
    if internal_names:
        env = Env({nm: UNINITIALIZED for nm in internal_names}, env)
    last_idx = len(body) - 1
    for i in range(last_idx):
        form = body[i]
        if _is_define_form(form):
            name, expr_or_formals, rest = _parse_define(form)
            if isinstance(expr_or_formals, Symbol) or isinstance(expr_or_formals, int) or isinstance(expr_or_formals, str) or expr_or_formals is True or expr_or_formals is False or isinstance(expr_or_formals, Pair) or expr_or_formals == ():
                val = _eval(expr_or_formals, env)
                env.frame[name] = val
            else:
                raise SchemeError("malformed define")
        else:
            _eval(form, env)
    return (body[last_idx], env)


# ─── Display / Write ──────────────────────────────────────────────────────────

def _repr_value(val, write_mode=False):
    if isinstance(val, bool):
        return '#t' if val else '#f'
    if isinstance(val, int):
        return str(val)
    if isinstance(val, str):
        if write_mode:
            s = val.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
            return f'"{s}"'
        return val
    if isinstance(val, Symbol):
        return val.name
    if val == ():
        return '()'
    if isinstance(val, Pair):
        return _repr_pair(val, write_mode)
    if isinstance(val, (Closure, Builtin)):
        return '#<procedure>'
    if val is UNSPECIFIED:
        return ''
    return '#<unknown>'


def _repr_pair(p, write_mode=False):
    parts = []
    cur = p
    while isinstance(cur, Pair):
        parts.append(_repr_value(cur.car, write_mode))
        cur = cur.cdr
    if cur == ():
        return '(' + ' '.join(parts) + ')'
    else:
        return '(' + ' '.join(parts) + ' . ' + _repr_value(cur, write_mode) + ')'


# ─── Evaluator ────────────────────────────────────────────────────────────────

def _eval(expr, env):
    if _is_self_evaluating(expr):
        return expr
    if isinstance(expr, Symbol):
        val = env.lookup(expr.name)
        return _check_uninit(val, expr.name)
    if expr == ():
        raise SchemeError("cannot apply ()")
    if not isinstance(expr, Pair):
        raise SchemeError("invalid expression")
    if not _is_proper_list(expr):
        raise SchemeError("invalid application (dotted form)")

    head = expr.car
    arg_exprs = _pair_to_list(expr.cdr)

    if isinstance(head, Symbol) and head.name in _SPECIAL_FORMS:
        return _eval_special(head.name, arg_exprs, env)

    op = _eval(head, env)
    arg_vals = [_eval(a, env) for a in arg_exprs]
    return _apply(op, arg_vals)


def _eval_tail(expr, env):
    while True:
        if _is_self_evaluating(expr):
            return expr
        if isinstance(expr, Symbol):
            val = env.lookup(expr.name)
            return _check_uninit(val, expr.name)
        if expr == ():
            raise SchemeError("cannot apply ()")
        if not isinstance(expr, Pair):
            raise SchemeError("invalid expression")
        if not _is_proper_list(expr):
            raise SchemeError("invalid application (dotted form)")

        head = expr.car
        arg_exprs = _pair_to_list(expr.cdr)

        if isinstance(head, Symbol) and head.name in _SPECIAL_FORMS:
            result = _eval_special_tail(head.name, arg_exprs, env)
            if isinstance(result, tuple) and len(result) == 2 and result[0] is _TAIL:
                expr, env = result[1], result[2]
                continue
            else:
                return result

        # apply special case
        if isinstance(head, Symbol) and head.name == 'apply':
            if len(arg_exprs) < 2:
                raise SchemeError("apply: expected at least 2 arguments")
            f_val = _eval(arg_exprs[0], env)
            other_vals = [_eval(a, env) for a in arg_exprs[1:-1]]
            lst_val = _eval(arg_exprs[-1], env)
            if not _is_procedure(f_val):
                raise SchemeError("apply: first argument not a procedure")
            if not _is_proper_list(lst_val):
                raise SchemeError("apply: last argument not a proper list")
            all_args = other_vals + _pair_to_list(lst_val)
            if isinstance(f_val, Closure):
                new_env = _bind_closure_args(f_val, all_args)
                expr, env = _prepare_body(f_val.body, new_env)
                continue
            elif isinstance(f_val, Builtin):
                return f_val.func(all_args)
            raise SchemeError("not a procedure")

        op = _eval(head, env)
        arg_vals = [_eval(a, env) for a in arg_exprs]

        if not _is_procedure(op):
            raise SchemeError("not a procedure")

        if isinstance(op, Closure):
            new_env = _bind_closure_args(op, arg_vals)
            expr, env = _prepare_body(op.body, new_env)
        elif isinstance(op, Builtin):
            return op.func(arg_vals)
        else:
            raise SchemeError("not a procedure")


_TAIL = object()


def _apply(op, arg_vals):
    if not _is_procedure(op):
        raise SchemeError("not a procedure")
    if isinstance(op, Closure):
        new_env = _bind_closure_args(op, arg_vals)
        last_expr, new_env = _prepare_body(op.body, new_env)
        return _eval_tail(last_expr, new_env)
    elif isinstance(op, Builtin):
        return op.func(arg_vals)
    raise SchemeError("not a procedure")


# ─── Special forms (non-tail) ─────────────────────────────────────────────────

def _eval_special(name, args, env):
    if name == 'quote':
        if len(args) != 1:
            raise SchemeError("quote: expected 1 argument")
        return args[0]
    if name == 'if':
        if len(args) not in (2, 3):
            raise SchemeError("if: expected 2 or 3 arguments")
        test = _eval(args[0], env)
        if test is not False:
            return _eval(args[1], env)
        elif len(args) == 3:
            return _eval(args[2], env)
        else:
            return UNSPECIFIED
    if name == 'define':
        return _eval_define(args, env)
    if name == 'set!':
        if len(args) != 2:
            raise SchemeError("set!: expected 2 arguments")
        if not isinstance(args[0], Symbol):
            raise SchemeError("set!: first argument must be a symbol")
        val = _eval(args[1], env)
        env.set(args[0].name, val)
        return UNSPECIFIED
    if name == 'begin':
        if not args:
            raise SchemeError("begin: expected at least 1 form")
        for a in args[:-1]:
            _eval(a, env)
        return _eval(args[-1], env)
    if name == 'cond':
        return _eval_cond(args, env)
    if name == 'and':
        for a in args:
            val = _eval(a, env)
            if val is False:
                return False
        return True if not args else val
    if name == 'or':
        for a in args:
            val = _eval(a, env)
            if val is not False:
                return val
        return False
    if name == 'lambda':
        if len(args) != 2:
            raise SchemeError("lambda: expected 2 arguments")
        formals = _parse_formals(args[0])
        body = args[1]
        if not isinstance(body, list):
            raise SchemeError("lambda: body must be a list of forms")
        if not body:
            raise SchemeError("lambda: empty body")
        return Closure(formals, body, env)
    if name == 'let':
        return _eval_let(args, env)
    if name == 'let*':
        return _eval_letstar(args, env)
    if name == 'letrec':
        return _eval_letrec(args, env)
    raise SchemeError(f"unknown special form: {name}")


def _eval_define(args, env):
    if not args:
        raise SchemeError("define: expected at least 1 argument")
    first = args[0]
    if isinstance(first, Symbol):
        if len(args) != 2:
            raise SchemeError("define: expected (define name expr)")
        name = first.name
        val = _eval(args[1], env)
        env.define(name, val)
        return UNSPECIFIED
    elif isinstance(first, Pair):
        if not isinstance(first.car, Symbol):
            raise SchemeError("define: malformed")
        name = first.car.name
        formals = _parse_formals(first.cdr)
        body = args[1]
        if not isinstance(body, list) or not body:
            raise SchemeError("define: empty body")
        closure = Closure(formals, body, env)
        env.define(name, closure)
        return UNSPECIFIED
    else:
        raise SchemeError("define: malformed")


def _eval_cond(args, env):
    for i, clause in enumerate(args):
        if not isinstance(clause, list) or not clause:
            raise SchemeError("cond: malformed clause")
        test = clause[0]
        if isinstance(test, Symbol) and test.name == 'else':
            if i != len(args) - 1:
                raise SchemeError("cond: else must be last clause")
            exprs = clause[1:]
            if not exprs:
                return UNSPECIFIED
            for e in exprs[:-1]:
                _eval(e, env)
            return _eval(exprs[-1], env)
        else:
            val = _eval(test, env)
            if val is not False:
                exprs = clause[1:]
                if not exprs:
                    return val
                for e in exprs[:-1]:
                    _eval(e, env)
                return _eval(exprs[-1], env)
    return UNSPECIFIED


def _eval_let(args, env):
    # Named let: (let name ((v init) ...) body...)
    if isinstance(args[0], Symbol):
        name = args[0].name
        bindings = args[1]
        body = args[2]
        if not isinstance(bindings, list):
            raise SchemeError("let: malformed bindings")
        # Parse bindings
        names = []
        inits = []
        for b in bindings:
            if not isinstance(b, list) or len(b) != 2:
                raise SchemeError("let: malformed binding")
            if not isinstance(b[0], Symbol):
                raise SchemeError("let: binding name must be a symbol")
            names.append(b[0].name)
            inits.append(b[1])
        # Evaluate inits in outer scope
        init_vals = [_eval(init, env) for init in inits]
        # Create the named procedure
        formals = names
        proc = Closure(formals, body, None)  # env will be set
        # The closure's env should see the let variables
        # Create env with the variables, then set the closure's env
        let_env = Env({}, env)
        let_env.frame[name] = proc
        proc.env = let_env
        # Bind the variables and call
        for nm, v in zip(names, init_vals):
            let_env.frame[nm] = v
        last_expr, let_env = _prepare_body(body, let_env)
        return _eval_tail(last_expr, let_env)
    else:
        bindings = args[0]
        body = args[1]
        if not isinstance(bindings, list):
            raise SchemeError("let: malformed bindings")
        names = []
        inits = []
        for b in bindings:
            if not isinstance(b, list) or len(b) != 2:
                raise SchemeError("let: malformed binding")
            if not isinstance(b[0], Symbol):
                raise SchemeError("let: binding name must be a symbol")
            names.append(b[0].name)
            inits.append(b[1])
        init_vals = [_eval(init, env) for init in inits]
        frame = {}
        for nm, v in zip(names, init_vals):
            frame[nm] = v
        let_env = Env(frame, env)
        last_expr, let_env = _prepare_body(body, let_env)
        return _eval_tail(last_expr, let_env)


def _eval_letstar(args, env):
    bindings = args[0]
    body = args[1]
    if not isinstance(bindings, list):
        raise SchemeError("let*: malformed bindings")
    let_env = env
    for b in bindings:
        if not isinstance(b, list) or len(b) != 2:
            raise SchemeError("let*: malformed binding")
        if not isinstance(b[0], Symbol):
            raise SchemeError("let*: binding name must be a symbol")
        val = _eval(b[1], let_env)
        let_env = Env({b[0].name: val}, let_env)
    last_expr, let_env = _prepare_body(body, let_env)
    return _eval_tail(last_expr, let_env)


def _eval_letrec(args, env):
    bindings = args[0]
    body = args[1]
    if not isinstance(bindings, list):
        raise SchemeError("letrec: malformed bindings")
    names = []
    inits = []
    for b in bindings:
        if not isinstance(b, list) or len(b) != 2:
            raise SchemeError("letrec: malformed binding")
        if not isinstance(b[0], Symbol):
            raise SchemeError("letrec: binding name must be a symbol")
        names.append(b[0].name)
        inits.append(b[1])
    let_env = Env({nm: UNINITIALIZED for nm in names}, env)
    for nm, init in zip(names, inits):
        val = _eval(init, let_env)
        let_env.frame[nm] = val
    last_expr, let_env = _prepare_body(body, let_env)
    return _eval_tail(last_expr, let_env)


# ─── Special forms (tail) ─────────────────────────────────────────────────────

def _eval_special_tail(name, args, env):
    if name == 'quote':
        if len(args) != 1:
            raise SchemeError("quote: expected 1 argument")
        return args[0]
    if name == 'if':
        if len(args) not in (2, 3):
            raise SchemeError("if: expected 2 or 3 arguments")
        test = _eval(args[0], env)
        if test is not False:
            return (_TAIL, args[1], env)
        elif len(args) == 3:
            return (_TAIL, args[2], env)
        else:
            return UNSPECIFIED
    if name == 'define':
        return _eval_define(args, env)
    if name == 'set!':
        if len(args) != 2:
            raise SchemeError("set!: expected 2 arguments")
        if not isinstance(args[0], Symbol):
            raise SchemeError("set!: first argument must be a symbol")
        val = _eval(args[1], env)
        env.set(args[0].name, val)
        return UNSPECIFIED
    if name == 'begin':
        if not args:
            raise SchemeError("begin: expected at least 1 form")
        for a in args[:-1]:
            _eval(a, env)
        return (_TAIL, args[-1], env)
    if name == 'cond':
        return _eval_cond_tail(args, env)
    if name == 'and':
        if not args:
            return True
        for a in args[:-1]:
            val = _eval(a, env)
            if val is False:
                return False
        return (_TAIL, args[-1], env)
    if name == 'or':
        if not args:
            return False
        for a in args[:-1]:
            val = _eval(a, env)
            if val is not False:
                return val
        return (_TAIL, args[-1], env)
    if name == 'lambda':
        if len(args) != 2:
            raise SchemeError("lambda: expected 2 arguments")
        formals = _parse_formals(args[0])
        body = args[1]
        if not isinstance(body, list) or not body:
            raise SchemeError("lambda: empty body")
        return Closure(formals, body, env)
    if name == 'let':
        return _eval_let_tail(args, env)
    if name == 'let*':
        return _eval_letstar_tail(args, env)
    if name == 'letrec':
        return _eval_letrec_tail(args, env)
    raise SchemeError(f"unknown special form: {name}")


def _eval_cond_tail(args, env):
    for i, clause in enumerate(args):
        if not isinstance(clause, list) or not clause:
            raise SchemeError("cond: malformed clause")
        test = clause[0]
        if isinstance(test, Symbol) and test.name == 'else':
            if i != len(args) - 1:
                raise SchemeError("cond: else must be last clause")
            exprs = clause[1:]
            if not exprs:
                return UNSPECIFIED
            for e in exprs[:-1]:
                _eval(e, env)
            return (_TAIL, exprs[-1], env)
        else:
            val = _eval(test, env)
            if val is not False:
                exprs = clause[1:]
                if not exprs:
                    return val
                for e in exprs[:-1]:
                    _eval(e, env)
                return (_TAIL, exprs[-1], env)
    return UNSPECIFIED


def _eval_let_tail(args, env):
    if isinstance(args[0], Symbol):
        name = args[0].name
        bindings = args[1]
        body = args[2]
        if not isinstance(bindings, list):
            raise SchemeError("let: malformed bindings")
        names = []
        inits = []
        for b in bindings:
            if not isinstance(b, list) or len(b) != 2:
                raise SchemeError("let: malformed binding")
            if not isinstance(b[0], Symbol):
                raise SchemeError("let: binding name must be a symbol")
            names.append(b[0].name)
            inits.append(b[1])
        init_vals = [_eval(init, env) for init in inits]
        formals = names
        proc = Closure(formals, body, None)
        let_env = Env({}, env)
        let_env.frame[name] = proc
        proc.env = let_env
        for nm, v in zip(names, init_vals):
            let_env.frame[nm] = v
        last_expr, let_env = _prepare_body(body, let_env)
        return (_TAIL, last_expr, let_env)
    else:
        bindings = args[0]
        body = args[1]
        if not isinstance(bindings, list):
            raise SchemeError("let: malformed bindings")
        names = []
        inits = []
        for b in bindings:
            if not isinstance(b, list) or len(b) != 2:
                raise SchemeError("let: malformed binding")
            if not isinstance(b[0], Symbol):
                raise SchemeError("let: binding name must be a symbol")
            names.append(b[0].name)
            inits.append(b[1])
        init_vals = [_eval(init, env) for init in inits]
        frame = {}
        for nm, v in zip(names, init_vals):
            frame[nm] = v
        let_env = Env(frame, env)
        last_expr, let_env = _prepare_body(body, let_env)
        return (_TAIL, last_expr, let_env)


def _eval_letstar_tail(args, env):
    bindings = args[0]
    body = args[1]
    if not isinstance(bindings, list):
        raise SchemeError("let*: malformed bindings")
    let_env = env
    for b in bindings:
        if not isinstance(b, list) or len(b) != 2:
            raise SchemeError("let*: malformed binding")
        if not isinstance(b[0], Symbol):
            raise SchemeError("let*: binding name must be a symbol")
        val = _eval(b[1], let_env)
        let_env = Env({b[0].name: val}, let_env)
    last_expr, let_env = _prepare_body(body, let_env)
    return (_TAIL, last_expr, let_env)


def _eval_letrec_tail(args, env):
    bindings = args[0]
    body = args[1]
    if not isinstance(bindings, list):
        raise SchemeError("letrec: malformed bindings")
    names = []
    inits = []
    for b in bindings:
        if not isinstance(b, list) or len(b) != 2:
            raise SchemeError("letrec: malformed binding")
        if not isinstance(b[0], Symbol):
            raise SchemeError("letrec: binding name must be a symbol")
        names.append(b[0].name)
        inits.append(b[1])
    let_env = Env({nm: UNINITIALIZED for nm in names}, env)
    for nm, init in zip(names, inits):
        val = _eval(init, let_env)
        let_env.frame[nm] = val
    last_expr, let_env = _prepare_body(body, let_env)
    return (_TAIL, last_expr, let_env)


# ─── Builtins ─────────────────────────────────────────────────────────────────

def _builtin_plus(args):
    for a in args:
        if isinstance(a, bool) or not isinstance(a, int):
            raise SchemeError("+: all arguments must be integers")
    return sum(args)


def _builtin_mul(args):
    for a in args:
        if isinstance(a, bool) or not isinstance(a, int):
            raise SchemeError("*: all arguments must be integers")
    r = 1
    for a in args:
        r *= a
    return r


def _builtin_sub(args):
    for a in args:
        if isinstance(a, bool) or not isinstance(a, int):
            raise SchemeError("-: all arguments must be integers")
    if len(args) == 1:
        return -args[0]
    r = args[0]
    for a in args[1:]:
        r -= a
    return r


def _builtin_quotient(args):
    if len(args) != 2:
        raise SchemeError("quotient: expected 2 arguments")
    a, b = args
    if isinstance(a, bool) or isinstance(b, bool) or not isinstance(a, int) or not isinstance(b, int):
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
    if isinstance(a, bool) or isinstance(b, bool) or not isinstance(a, int) or not isinstance(b, int):
        raise SchemeError("remainder: arguments must be integers")
    if b == 0:
        raise SchemeError("remainder: division by zero")
    return a - _builtin_quotient([a, b]) * b


def _builtin_modulo(args):
    if len(args) != 2:
        raise SchemeError("modulo: expected 2 arguments")
    a, b = args
    if isinstance(a, bool) or isinstance(b, bool) or not isinstance(a, int) or not isinstance(b, int):
        raise SchemeError("modulo: arguments must be integers")
    if b == 0:
        raise SchemeError("modulo: division by zero")
    return a % b


def _builtin_compare(args, op_name):
    for a in args:
        if isinstance(a, bool) or not isinstance(a, int):
            raise SchemeError(f"{op_name}: all arguments must be integers")
    for i in range(len(args) - 1):
        if op_name == '=':
            if args[i] != args[i + 1]:
                return False
        elif op_name == '<':
            if not (args[i] < args[i + 1]):
                return False
        elif op_name == '>':
            if not (args[i] > args[i + 1]):
                return False
        elif op_name == '<=':
            if not (args[i] <= args[i + 1]):
                return False
        elif op_name == '>=':
            if not (args[i] >= args[i + 1]):
                return False
    return True


def _builtin_number_to_string(args):
    if len(args) not in (1, 2):
        raise SchemeError("number->string: expected 1 or 2 arguments")
    n = args[0]
    if isinstance(n, bool) or not isinstance(n, int):
        raise SchemeError("number->string: argument must be an integer")
    radix = 10
    if len(args) == 2:
        radix = args[1]
        if isinstance(radix, bool) or not isinstance(radix, int):
            raise SchemeError("number->string: radix must be an integer")
        if radix not in (2, 8, 10, 16):
            raise SchemeError("number->string: invalid radix")
    return _num_to_str(n, radix)


def _num_to_str(n, radix):
    if n < 0:
        return '-' + _num_to_str(-n, radix)
    if n == 0:
        return '0'
    digits = '0123456789abcdef'
    result = []
    while n > 0:
        result.append(digits[n % radix])
        n //= radix
    return ''.join(reversed(result))


def _builtin_cons(args):
    if len(args) != 2:
        raise SchemeError("cons: expected 2 arguments")
    return Pair(args[0], args[1])


def _builtin_car(args):
    if len(args) != 1:
        raise SchemeError("car: expected 1 argument")
    if not isinstance(args[0], Pair):
        raise SchemeError("car: argument must be a pair")
    return args[0].car


def _builtin_cdr(args):
    if len(args) != 1:
        raise SchemeError("cdr: expected 1 argument")
    if not isinstance(args[0], Pair):
        raise SchemeError("cdr: argument must be a pair")
    return args[0].cdr


def _builtin_list(args):
    return _list_to_pair(args)


def _builtin_null_p(args):
    if len(args) != 1:
        raise SchemeError("null?: expected 1 argument")
    return args[0] == ()


def _builtin_pair_p(args):
    if len(args) != 1:
        raise SchemeError("pair?: expected 1 argument")
    return isinstance(args[0], Pair)


def _builtin_list_p(args):
    if len(args) != 1:
        raise SchemeError("list?: expected 1 argument")
    return _is_proper_list(args[0])


def _builtin_length(args):
    if len(args) != 1:
        raise SchemeError("length: expected 1 argument")
    l = args[0]
    if not _is_proper_list(l):
        raise SchemeError("length: argument must be a proper list")
    count = 0
    cur = l
    while cur != ():
        count += 1
        cur = cur.cdr
    return count


def _builtin_append(args):
    if not args:
        return ()
    for l in args[:-1]:
        if not _is_proper_list(l):
            raise SchemeError("append: argument must be a proper list")
    last = args[-1]
    if len(args) == 1:
        return last
    result_head = None
    result_tail = None
    for l in args[:-1]:
        cur = l
        while cur != ():
            p = Pair(cur.car, ())
            if result_head is None:
                result_head = p
            else:
                result_tail.cdr = p
            result_tail = p
            cur = cur.cdr
    if result_head is None:
        return last
    result_tail.cdr = last
    return result_head


def _builtin_reverse(args):
    if len(args) != 1:
        raise SchemeError("reverse: expected 1 argument")
    l = args[0]
    if not _is_proper_list(l):
        raise SchemeError("reverse: argument must be a proper list")
    result = ()
    cur = l
    while cur != ():
        result = Pair(cur.car, result)
        cur = cur.cdr
    return result


def _builtin_eq(args):
    if len(args) != 2:
        raise SchemeError("eq?: expected 2 arguments")
    a, b = args
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, int) and isinstance(b, int):
        return a == b
    if isinstance(a, Symbol) and isinstance(b, Symbol):
        return a.name == b.name
    if a == () and b == ():
        return True
    return a is b


def _builtin_equal(args):
    if len(args) != 2:
        raise SchemeError("equal?: expected 2 arguments")
    return _equal(args[0], args[1])


def _equal(a, b):
    stack = [(a, b)]
    while stack:
        a, b = stack.pop()
        if isinstance(a, bool) or isinstance(b, bool):
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
        elif a == () and b == ():
            pass
        elif isinstance(a, Pair) and isinstance(b, Pair):
            stack.append((a.cdr, b.cdr))
            stack.append((a.car, b.car))
        elif isinstance(a, (Closure, Builtin)) and isinstance(b, (Closure, Builtin)):
            if a is not b:
                return False
        elif a is UNSPECIFIED and b is UNSPECIFIED:
            pass
        else:
            return False
    return True


def _builtin_not(args):
    if len(args) != 1:
        raise SchemeError("not: expected 1 argument")
    return args[0] is False


def _builtin_number_p(args):
    if len(args) != 1:
        raise SchemeError("number?: expected 1 argument")
    return isinstance(args[0], int) and not isinstance(args[0], bool)


def _builtin_symbol_p(args):
    if len(args) != 1:
        raise SchemeError("symbol?: expected 1 argument")
    return isinstance(args[0], Symbol)


def _builtin_string_p(args):
    if len(args) != 1:
        raise SchemeError("string?: expected 1 argument")
    return isinstance(args[0], str)


def _builtin_procedure_p(args):
    if len(args) != 1:
        raise SchemeError("procedure?: expected 1 argument")
    return _is_procedure(args[0])


def _builtin_string_append(args):
    for a in args:
        if not isinstance(a, str):
            raise SchemeError("string-append: all arguments must be strings")
    return ''.join(args)


def _builtin_display(args):
    if len(args) != 1:
        raise SchemeError("display: expected 1 argument")
    _output.append(_repr_value(args[0], write_mode=False))
    return UNSPECIFIED


def _builtin_newline(args):
    if len(args) != 0:
        raise SchemeError("newline: expected 0 arguments")
    _output.append('\n')
    return UNSPECIFIED


def _builtin_error(args):
    if len(args) < 1:
        raise SchemeError("error: expected at least 1 argument")
    msg = args[0]
    if not isinstance(msg, str):
        raise SchemeError("error: first argument must be a string")
    full = msg
    for irr in args[1:]:
        full += ' ' + _repr_value(irr, write_mode=True)
    raise SchemeError(full)


# ─── Global environment ───────────────────────────────────────────────────────

def _make_global_env():
    frame = {}
    frame['+'] = Builtin('+', _builtin_plus)
    frame['*'] = Builtin('*', _builtin_mul)
    frame['-'] = Builtin('-', _builtin_sub)
    frame['quotient'] = Builtin('quotient', _builtin_quotient)
    frame['remainder'] = Builtin('remainder', _builtin_remainder)
    frame['modulo'] = Builtin('modulo', _builtin_modulo)
    frame['='] = Builtin('=', lambda a: _builtin_compare(a, '='))
    frame['<'] = Builtin('<', lambda a: _builtin_compare(a, '<'))
    frame['>'] = Builtin('>', lambda a: _builtin_compare(a, '>'))
    frame['<='] = Builtin('<=', lambda a: _builtin_compare(a, '<='))
    frame['>='] = Builtin('>=', lambda a: _builtin_compare(a, '>='))
    frame['number->string'] = Builtin('number->string', _builtin_number_to_string)
    frame['cons'] = Builtin('cons', _builtin_cons)
    frame['car'] = Builtin('car', _builtin_car)
    frame['cdr'] = Builtin('cdr', _builtin_cdr)
    frame['list'] = Builtin('list', _builtin_list)
    frame['null?'] = Builtin('null?', _builtin_null_p)
    frame['pair?'] = Builtin('pair?', _builtin_pair_p)
    frame['list?'] = Builtin('list?', _builtin_list_p)
    frame['length'] = Builtin('length', _builtin_length)
    frame['append'] = Builtin('append', _builtin_append)
    frame['reverse'] = Builtin('reverse', _builtin_reverse)
    frame['apply'] = Builtin('apply', lambda a: (_ for _ in ()).throw(SchemeError("apply should be handled by evaluator")))
    frame['eq?'] = Builtin('eq?', _builtin_eq)
    frame['equal?'] = Builtin('equal?', _builtin_equal)
    frame['not'] = Builtin('not', _builtin_not)
    frame['number?'] = Builtin('number?', _builtin_number_p)
    frame['symbol?'] = Builtin('symbol?', _builtin_symbol_p)
    frame['string?'] = Builtin('string?', _builtin_string_p)
    frame['procedure?'] = Builtin('procedure?', _builtin_procedure_p)
    frame['string-append'] = Builtin('string-append', _builtin_string_append)
    frame['display'] = Builtin('display', _builtin_display)
    frame['newline'] = Builtin('newline', _builtin_newline)
    frame['error'] = Builtin('error', _builtin_error)
    return Env(frame)


_SPECIAL_FORMS = {
    'quote', 'if', 'define', 'set!', 'begin', 'cond',
    'and', 'or', 'lambda', 'let', 'let*', 'letrec'
}

# ─── Public API ───────────────────────────────────────────────────────────────

def run(source):
    global _output
    _output = []
    try:
        forms = _read_all(source)
        env = _make_global_env()
        for form in forms:
            _eval(form, env)
    except SchemeError as e:
        e.output = ''.join(_output)
        raise
    except RecursionError:
        raise SchemeError("maximum recursion depth exceeded", ''.join(_output))
    except Exception as e:
        raise SchemeError(str(e), ''.join(_output))
    return ''.join(_output)