import sys
import re
import threading

try:
    sys.set_int_max_str_digits(0)
except (AttributeError, ValueError):
    pass


class SchemeError(Exception):
    def __init__(self, msg, output=''):
        super().__init__(msg)
        self.output = output


class SchemeSymbol:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name
    def __repr__(self):
        return f"Sym({self.name})"


class SchemePair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr


class Closure:
    __slots__ = ('params', 'body', 'env')
    def __init__(self, params, body, env):
        self.params = params
        self.body = body
        self.env = env


class Builtin:
    __slots__ = ('func',)
    def __init__(self, func):
        self.func = func


UNSPECIFIED = object()
UNINITIALIZED = object()


class Env:
    __slots__ = ('bindings', 'parent')
    def __init__(self, bindings=None, parent=None):
        self.bindings = bindings if bindings is not None else {}
        self.parent = parent

    def lookup(self, name):
        e = self
        while e is not None:
            if name in e.bindings:
                v = e.bindings[name]
                if v is UNINITIALIZED:
                    raise SchemeError(f"unbound variable: {name}")
                return v
            e = e.parent
        raise SchemeError(f"unbound variable: {name}")

    def set(self, name, value):
        e = self
        while e is not None:
            if name in e.bindings:
                e.bindings[name] = value
                return
            e = e.parent
        raise SchemeError(f"unbound variable: {name}")


# ─── Reader ───────────────────────────────────────────────────────────────────

def _read_all(source):
    pos = 0
    n = len(source)
    forms = []

    def skip_ws():
        nonlocal pos
        while pos < n:
            c = source[pos]
            if c in ' \t\n\r':
                pos += 1
            elif c == ';':
                while pos < n and source[pos] != '\n':
                    pos += 1
            else:
                break

    def read_datum():
        nonlocal pos
        skip_ws()
        if pos >= n:
            raise SchemeError("unexpected end of input")
        c = source[pos]
        if c == '(':
            return read_list()
        elif c == ')':
            raise SchemeError("unexpected )")
        elif c == "'":
            pos += 1
            d = read_datum()
            return [SchemeSymbol('quote'), d]
        elif c == '"':
            return read_string()
        else:
            return read_token()

    def read_list():
        nonlocal pos
        pos += 1
        elements = []
        while True:
            skip_ws()
            if pos >= n:
                raise SchemeError("unbalanced (")
            c = source[pos]
            if c == ')':
                pos += 1
                if elements:
                    return elements
                else:
                    return ()
            elif c == '.' and (pos + 1 >= n or source[pos + 1] in ' \t\n\r)'):
                pos += 1
                skip_ws()
                if pos >= n or source[pos] == ')':
                    raise SchemeError("dot must be followed by a datum")
                tail = read_datum()
                skip_ws()
                if pos >= n or source[pos] != ')':
                    raise SchemeError("expected ) after dotted list")
                pos += 1
                if not elements:
                    raise SchemeError("dot must be preceded by at least one element")
                result = tail
                for elem in reversed(elements):
                    result = SchemePair(elem, result)
                return result
            else:
                elements.append(read_datum())

    def read_string():
        nonlocal pos
        pos += 1
        result = []
        while pos < n:
            c = source[pos]
            if c == '"':
                pos += 1
                return ''.join(result)
            elif c == '\\':
                if pos + 1 >= n:
                    raise SchemeError("unterminated string")
                nc = source[pos + 1]
                if nc == '"':
                    result.append('"')
                    pos += 2
                elif nc == '\\':
                    result.append('\\')
                    pos += 2
                elif nc == 'n':
                    result.append('\n')
                    pos += 2
                else:
                    raise SchemeError(f"invalid escape: \\{nc}")
            else:
                result.append(c)
                pos += 1
        raise SchemeError("unterminated string")

    def read_token():
        nonlocal pos
        start = pos
        while pos < n and source[pos] not in ' \t\n\r()";\'':
            pos += 1
        token = source[start:pos]
        if not token:
            raise SchemeError("empty token")
        if re.fullmatch(r'[+-]?[0-9]+', token):
            return int(token)
        if token == '#t':
            return True
        if token == '#f':
            return False
        if token.startswith('#'):
            raise SchemeError(f"invalid token: {token}")
        return SchemeSymbol(token)

    while True:
        skip_ws()
        if pos >= n:
            break
        forms.append(read_datum())
    return forms


# ─── Helper functions ─────────────────────────────────────────────────────────

def _is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)

def _is_bool(x):
    return isinstance(x, bool)

def _is_str(x):
    return isinstance(x, str)

def _is_sym(x):
    return isinstance(x, SchemeSymbol)

def _is_pair(x):
    return isinstance(x, SchemePair)

def _is_proper_list(x):
    return x == () or isinstance(x, list)

def _truthy(x):
    return x is not False

def _int_to_str(n, radix=10):
    if n == 0:
        return '0'
    negative = n < 0
    n = abs(n)
    digits = []
    while n > 0:
        n, r = divmod(n, radix)
        digits.append('0123456789abcdef'[r])
    if negative:
        digits.append('-')
    return ''.join(reversed(digits))


def _display_value(val, out, write=False):
    if _is_bool(val):
        out.append('#t' if val else '#f')
    elif _is_int(val):
        out.append(_int_to_str(val))
    elif _is_str(val):
        if write:
            out.append('"')
            for c in val:
                if c == '"':
                    out.append('\\"')
                elif c == '\\':
                    out.append('\\\\')
                elif c == '\n':
                    out.append('\\n')
                else:
                    out.append(c)
            out.append('"')
        else:
            out.append(val)
    elif _is_sym(val):
        out.append(val.name)
    elif val == ():
        out.append('()')
    elif isinstance(val, (list, SchemePair)):
        _display_list(val, out, write)
    elif isinstance(val, (Closure, Builtin)):
        out.append('#<procedure>')
    elif val is UNSPECIFIED:
        pass
    else:
        out.append(str(val))


def _display_list(val, out, write=False):
    out.append('(')
    printed = False
    while True:
        if val == ():
            break
        if printed:
            out.append(' ')
        if isinstance(val, list):
            _display_value(val[0], out, write)
            val = val[1:] if len(val) > 1 else ()
        elif isinstance(val, SchemePair):
            _display_value(val.car, out, write)
            val = val.cdr
            if val != () and not isinstance(val, list):
                out.append(' . ')
                _display_value(val, out, write)
                break
        else:
            break
        printed = True
    out.append(')')


def _write_value(val, out):
    _display_value(val, out, write=True)


# ─── TCO infrastructure ───────────────────────────────────────────────────────

class TailCall:
    __slots__ = ('form', 'env')
    def __init__(self, form, env):
        self.form = form
        self.env = env


class EvalSeq:
    __slots__ = ('forms', 'env')
    def __init__(self, forms, env):
        self.forms = forms
        self.env = env


# ─── Evaluator ────────────────────────────────────────────────────────────────

def _eval_form(form, env, out):
    """Evaluate a form in non-tail position. Returns a value."""
    if _is_int(form) or _is_bool(form) or _is_str(form):
        return form
    if _is_sym(form):
        return env.lookup(form.name)
    if form == ():
        return ()
    if isinstance(form, SchemePair):
        raise SchemeError("dotted form cannot be applied")
    if not isinstance(form, list):
        return form
    if len(form) == 0:
        raise SchemeError("cannot evaluate empty list")
    head = form[0]
    if _is_sym(head):
        name = head.name
        if name == 'quote':
            return _eval_quote(form, env, out)
        elif name == 'if':
            return _eval_if(form, env, out)
        elif name == 'define':
            return _eval_define(form, env, out)
        elif name == 'set!':
            return _eval_set(form, env, out)
        elif name == 'begin':
            return _eval_begin(form, env, out)
        elif name == 'cond':
            return _eval_cond(form, env, out)
        elif name == 'and':
            return _eval_and(form, env, out)
        elif name == 'or':
            return _eval_or(form, env, out)
        elif name == 'let':
            return _eval_let(form, env, out)
        elif name == 'let*':
            return _eval_letstar(form, env, out)
        elif name == 'letrec':
            return _eval_letrec(form, env, out)
        elif name == 'lambda':
            return _eval_lambda(form, env, out)
    # Application
    return _eval_application(form, env, out)


def _eval_seq(forms, env, out):
    """Evaluate a sequence of forms. Last is in tail position."""
    for f in forms[:-1]:
        _eval_form(f, env, out)
    return _eval_tail(forms[-1], env, out)


def _eval_tail(form, env, out):
    """Evaluate a form in tail position. Returns a value."""
    while True:
        result = _eval_tail_once(form, env, out)
        if isinstance(result, TailCall):
            form, env = result.form, result.env
        elif isinstance(result, EvalSeq):
            forms, env = result.forms, result.env
            for f in forms[:-1]:
                _eval_form(f, env, out)
            form = forms[-1]
        else:
            return result


def _eval_tail_once(form, env, out):
    """One step of tail evaluation. Returns value, TailCall, or EvalSeq."""
    if _is_int(form) or _is_bool(form) or _is_str(form):
        return form
    if _is_sym(form):
        return env.lookup(form.name)
    if form == ():
        return ()
    if isinstance(form, SchemePair):
        raise SchemeError("dotted form cannot be applied")
    if not isinstance(form, list):
        return form
    if len(form) == 0:
        raise SchemeError("cannot evaluate empty list")
    head = form[0]
    if _is_sym(head):
        name = head.name
        if name == 'quote':
            return _eval_quote(form, env, out)
        elif name == 'if':
            return _eval_if_tail(form, env, out)
        elif name == 'define':
            return _eval_define(form, env, out)
        elif name == 'set!':
            return _eval_set(form, env, out)
        elif name == 'begin':
            return _eval_begin_tail(form, env, out)
        elif name == 'cond':
            return _eval_cond_tail(form, env, out)
        elif name == 'and':
            return _eval_and_tail(form, env, out)
        elif name == 'or':
            return _eval_or_tail(form, env, out)
        elif name == 'let':
            return _eval_let_tail(form, env, out)
        elif name == 'let*':
            return _eval_letstar_tail(form, env, out)
        elif name == 'letrec':
            return _eval_letrec_tail(form, env, out)
        elif name == 'lambda':
            return _eval_lambda(form, env, out)
    return _eval_application_tail(form, env, out)


# ─── Special forms (non-tail) ─────────────────────────────────────────────────

def _eval_quote(form, env, out):
    if len(form) != 2:
        raise SchemeError("malformed quote")
    return form[1]


def _eval_if(form, env, out):
    if len(form) not in (3, 4):
        raise SchemeError("malformed if")
    test = _eval_form(form[1], env, out)
    if _truthy(test):
        return _eval_form(form[2], env, out)
    else:
        if len(form) == 4:
            return _eval_form(form[3], env, out)
        else:
            return UNSPECIFIED


def _eval_define(form, env, out):
    if len(form) < 3:
        raise SchemeError("malformed define")
    if len(form) == 3:
        name = form[1]
        if not _is_sym(name):
            raise SchemeError("define: name must be a symbol")
        val = _eval_form(form[2], env, out)
        env.bindings[name.name] = val
    else:
        funcdef = form[1]
        if isinstance(funcdef, list):
            if not funcdef or not _is_sym(funcdef[0]):
                raise SchemeError("malformed define")
            name = funcdef[0]
            formals = funcdef[1:]
        elif isinstance(funcdef, SchemePair):
            if not _is_sym(funcdef.car):
                raise SchemeError("malformed define")
            name = funcdef.car
            formals = funcdef.cdr
        else:
            raise SchemeError("malformed define")
        lambda_form = [SchemeSymbol('lambda'), formals] + form[2:]
        val = _eval_lambda(lambda_form, env, out)
        env.bindings[name.name] = val
    return UNSPECIFIED


def _eval_set(form, env, out):
    if len(form) != 3:
        raise SchemeError("malformed set!")
    name = form[1]
    if not _is_sym(name):
        raise SchemeError("set!: name must be a symbol")
    val = _eval_form(form[2], env, out)
    env.set(name.name, val)
    return UNSPECIFIED


def _eval_begin(form, env, out):
    if len(form) < 2:
        raise SchemeError("malformed begin")
    val = UNSPECIFIED
    for f in form[1:]:
        val = _eval_form(f, env, out)
    return val


def _eval_cond(form, env, out):
    clauses = form[1:]
    for i, clause in enumerate(clauses):
        if not isinstance(clause, list) or len(clause) < 1:
            raise SchemeError("malformed cond clause")
        test = clause[0]
        if _is_sym(test) and test.name == 'else':
            if i != len(clauses) - 1:
                raise SchemeError("else must be last clause")
            exprs = clause[1:]
            if not exprs:
                raise SchemeError("else clause requires expressions")
            val = UNSPECIFIED
            for e in exprs:
                val = _eval_form(e, env, out)
            return val
        else:
            test_val = _eval_form(test, env, out)
            if _truthy(test_val):
                exprs = clause[1:]
                if not exprs:
                    return test_val
                val = UNSPECIFIED
                for e in exprs:
                    val = _eval_form(e, env, out)
                return val
    return UNSPECIFIED


def _eval_and(form, env, out):
    exprs = form[1:]
    if not exprs:
        return True
    val = True
    for e in exprs:
        val = _eval_form(e, env, out)
        if val is False:
            return False
    return val


def _eval_or(form, env, out):
    exprs = form[1:]
    for e in exprs:
        val = _eval_form(e, env, out)
        if val is not False:
            return val
    return False


def _eval_let(form, env, out):
    if len(form) < 3:
        raise SchemeError("malformed let")
    # Check for named let
    if _is_sym(form[1]):
        return _eval_named_let(form, env, out, tail=False)
    bindings = form[1]
    body = form[2:]
    if not isinstance(bindings, list):
        raise SchemeError("malformed let")
    vals = []
    names = []
    for b in bindings:
        if not isinstance(b, list) or len(b) != 2:
            raise SchemeError("malformed let binding")
        if not _is_sym(b[0]):
            raise SchemeError("let: variable must be a symbol")
        names.append(b[0].name)
        vals.append(_eval_form(b[1], env, out))
    new_env = Env(dict(zip(names, vals)), env)
    return _eval_body(body, new_env, out)


def _eval_letstar(form, env, out):
    if len(form) < 3:
        raise SchemeError("malformed let*")
    bindings = form[1]
    body = form[2:]
    if not isinstance(bindings, list):
        raise SchemeError("malformed let*")
    new_env = Env({}, env)
    for b in bindings:
        if not isinstance(b, list) or len(b) != 2:
            raise SchemeError("malformed let* binding")
        if not _is_sym(b[0]):
            raise SchemeError("let*: variable must be a symbol")
        val = _eval_form(b[1], new_env, out)
        new_env.bindings[b[0].name] = val
    return _eval_body(body, new_env, out)


def _eval_letrec(form, env, out):
    if len(form) < 3:
        raise SchemeError("malformed letrec")
    bindings = form[1]
    body = form[2:]
    if not isinstance(bindings, list):
        raise SchemeError("malformed letrec")
    new_env = Env({}, env)
    for b in bindings:
        if not isinstance(b, list) or len(b) != 2:
            raise SchemeError("malformed letrec binding")
        if not _is_sym(b[0]):
            raise SchemeError("letrec: variable must be a symbol")
        new_env.bindings[b[0].name] = UNINITIALIZED
    for b in bindings:
        val = _eval_form(b[1], new_env, out)
        new_env.bindings[b[0].name] = val
    return _eval_body(body, new_env, out)


def _eval_named_let(form, env, out, tail=False):
    if len(form) < 4:
        raise SchemeError("malformed named let")
    name = form[1]
    bindings = form[2]
    body = form[3:]
    if not isinstance(bindings, list):
        raise SchemeError("malformed named let")
    params = []
    args = []
    for b in bindings:
        if not isinstance(b, list) or len(b) != 2:
            raise SchemeError("malformed named let binding")
        if not _is_sym(b[0]):
            raise SchemeError("named let: variable must be a symbol")
        params.append(b[0].name)
        args.append(_eval_form(b[1], env, out))
    closure_env = Env({}, env)
    closure = Closure(params, body, closure_env)
    closure_env.bindings[name.name] = closure
    call_env = Env(dict(zip(params, args)), closure_env)
    if tail:
        return EvalSeq(body, call_env)
    else:
        return _eval_body(body, call_env, out)


def _eval_lambda(form, env, out):
    if len(form) < 3:
        raise SchemeError("malformed lambda")
    formals = form[1]
    body = form[2:]
    if not body:
        raise SchemeError("lambda: empty body")
    if _is_sym(formals):
        pass
    elif isinstance(formals, list):
        for p in formals:
            if not _is_sym(p):
                raise SchemeError("lambda: parameter must be a symbol")
    elif isinstance(formals, SchemePair):
        p = formals
        while isinstance(p, SchemePair):
            if not _is_sym(p.car):
                raise SchemeError("lambda: parameter must be a symbol")
            p = p.cdr
        if not _is_sym(p):
            raise SchemeError("lambda: rest parameter must be a symbol")
    else:
        raise SchemeError("malformed lambda")
    return Closure(formals, body, env)


# ─── Special forms (tail) ─────────────────────────────────────────────────────

def _eval_if_tail(form, env, out):
    if len(form) not in (3, 4):
        raise SchemeError("malformed if")
    test = _eval_form(form[1], env, out)
    if _truthy(test):
        return TailCall(form[2], env)
    else:
        if len(form) == 4:
            return TailCall(form[3], env)
        else:
            return UNSPECIFIED


def _eval_begin_tail(form, env, out):
    if len(form) < 2:
        raise SchemeError("malformed begin")
    for f in form[1:-1]:
        _eval_form(f, env, out)
    return TailCall(form[-1], env)


def _eval_cond_tail(form, env, out):
    clauses = form[1:]
    for i, clause in enumerate(clauses):
        if not isinstance(clause, list) or len(clause) < 1:
            raise SchemeError("malformed cond clause")
        test = clause[0]
        if _is_sym(test) and test.name == 'else':
            if i != len(clauses) - 1:
                raise SchemeError("else must be last clause")
            exprs = clause[1:]
            if not exprs:
                raise SchemeError("else clause requires expressions")
            for e in exprs[:-1]:
                _eval_form(e, env, out)
            return TailCall(exprs[-1], env)
        else:
            test_val = _eval_form(test, env, out)
            if _truthy(test_val):
                exprs = clause[1:]
                if not exprs:
                    return test_val
                for e in exprs[:-1]:
                    _eval_form(e, env, out)
                return TailCall(exprs[-1], env)
    return UNSPECIFIED


def _eval_and_tail(form, env, out):
    exprs = form[1:]
    if not exprs:
        return True
    for e in exprs[:-1]:
        val = _eval_form(e, env, out)
        if val is False:
            return False
    return TailCall(exprs[-1], env)


def _eval_or_tail(form, env, out):
    exprs = form[1:]
    if not exprs:
        return False
    for e in exprs[:-1]:
        val = _eval_form(e, env, out)
        if val is not False:
            return val
    return TailCall(exprs[-1], env)


def _eval_let_tail(form, env, out):
    if len(form) < 3:
        raise SchemeError("malformed let")
    if _is_sym(form[1]):
        return _eval_named_let(form, env, out, tail=True)
    bindings = form[1]
    body = form[2:]
    if not isinstance(bindings, list):
        raise SchemeError("malformed let")
    vals = []
    names = []
    for b in bindings:
        if not isinstance(b, list) or len(b) != 2:
            raise SchemeError("malformed let binding")
        if not _is_sym(b[0]):
            raise SchemeError("let: variable must be a symbol")
        names.append(b[0].name)
        vals.append(_eval_form(b[1], env, out))
    new_env = Env(dict(zip(names, vals)), env)
    return EvalSeq(body, new_env)


def _eval_letstar_tail(form, env, out):
    if len(form) < 3:
        raise SchemeError("malformed let*")
    bindings = form[1]
    body = form[2:]
    if not isinstance(bindings, list):
        raise SchemeError("malformed let*")
    new_env = Env({}, env)
    for b in bindings:
        if not isinstance(b, list) or len(b) != 2:
            raise SchemeError("malformed let* binding")
        if not _is_sym(b[0]):
            raise SchemeError("let*: variable must be a symbol")
        val = _eval_form(b[1], new_env, out)
        new_env.bindings[b[0].name] = val
    return EvalSeq(body, new_env)


def _eval_letrec_tail(form, env, out):
    if len(form) < 3:
        raise SchemeError("malformed letrec")
    bindings = form[1]
    body = form[2:]
    if not isinstance(bindings, list):
        raise SchemeError("malformed letrec")
    new_env = Env({}, env)
    for b in bindings:
        if not isinstance(b, list) or len(b) != 2:
            raise SchemeError("malformed letrec binding")
        if not _is_sym(b[0]):
            raise SchemeError("letrec: variable must be a symbol")
        new_env.bindings[b[0].name] = UNINITIALIZED
    for b in bindings:
        val = _eval_form(b[1], new_env, out)
        new_env.bindings[b[0].name] = val
    return EvalSeq(body, new_env)


# ─── Body evaluation with internal definitions ────────────────────────────────

def _get_define_name(form):
    if len(form) == 3:
        if _is_sym(form[1]):
            return form[1].name
        elif isinstance(form[1], list) and len(form[1]) > 0:
            if _is_sym(form[1][0]):
                return form[1][0].name
        elif isinstance(form[1], SchemePair):
            if _is_sym(form[1].car):
                return form[1].car.name
    return None


def _eval_body(forms, env, out):
    """Evaluate a body, setting up internal definitions."""
    for f in forms:
        if isinstance(f, list) and len(f) >= 2:
            head = f[0]
            if _is_sym(head) and head.name == 'define':
                name = _get_define_name(f)
                if name is not None and name not in env.bindings:
                    env.bindings[name] = UNINITIALIZED
    return _eval_seq(forms, env, out)


# ─── Application ──────────────────────────────────────────────────────────────

def _bind_params(closure, args):
    params = closure.params
    if _is_sym(params):
        return Env({params.name: list(args)}, closure.env)
    elif isinstance(params, list):
        if len(args) != len(params):
            raise SchemeError("wrong number of arguments")
        return Env(dict(zip([p.name for p in params], args)), closure.env)
    elif isinstance(params, SchemePair):
        fixed = []
        p = params
        while isinstance(p, SchemePair):
            fixed.append(p.car)
            p = p.cdr
        rest_name = p
        if not _is_sym(rest_name):
            raise SchemeError("malformed lambda")
        if len(args) < len(fixed):
            raise SchemeError("wrong number of arguments")
        bindings = {fp.name: a for fp, a in zip(fixed, args[:len(fixed)])}
        bindings[rest_name.name] = list(args[len(fixed):])
        return Env(bindings, closure.env)
    else:
        raise SchemeError("malformed lambda")


def _call_procedure(proc, args, out):
    if isinstance(proc, Closure):
        new_env = _bind_params(proc, args)
        return _eval_body(proc.body, new_env, out)
    elif isinstance(proc, Builtin):
        return proc.func(args, out)
    else:
        raise SchemeError("not a procedure")


def _eval_application(form, env, out):
    op = _eval_form(form[0], env, out)
    args = [_eval_form(a, env, out) for a in form[1:]]
    if isinstance(op, Builtin) and op.func is _builtin_apply:
        if len(args) < 2:
            raise SchemeError("apply: wrong number of arguments")
        f = args[0]
        mid = args[1:-1]
        lst = args[-1]
        if not _is_proper_list(lst):
            raise SchemeError("apply: last argument must be a proper list")
        actual_args = mid + list(lst)
        return _call_procedure(f, actual_args, out)
    return _call_procedure(op, args, out)


def _eval_application_tail(form, env, out):
    op = _eval_form(form[0], env, out)
    args = [_eval_form(a, env, out) for a in form[1:]]
    if isinstance(op, Builtin) and op.func is _builtin_apply:
        if len(args) < 2:
            raise SchemeError("apply: wrong number of arguments")
        f = args[0]
        mid = args[1:-1]
        lst = args[-1]
        if not _is_proper_list(lst):
            raise SchemeError("apply: last argument must be a proper list")
        actual_args = mid + list(lst)
        if isinstance(f, Closure):
            new_env = _bind_params(f, actual_args)
            return EvalSeq(f.body, new_env)
        elif isinstance(f, Builtin):
            return f.func(actual_args, out)
        else:
            raise SchemeError("not a procedure")
    if isinstance(op, Closure):
        new_env = _bind_params(op, args)
        return EvalSeq(op.body, new_env)
    elif isinstance(op, Builtin):
        return op.func(args, out)
    else:
        raise SchemeError("not a procedure")


# ─── Builtins ─────────────────────────────────────────────────────────────────

def _builtin_plus(args, out):
    for a in args:
        if not _is_int(a):
            raise SchemeError("+: argument must be an integer")
    return sum(args)


def _builtin_star(args, out):
    for a in args:
        if not _is_int(a):
            raise SchemeError("*: argument must be an integer")
    r = 1
    for a in args:
        r *= a
    return r


def _builtin_minus(args, out):
    for a in args:
        if not _is_int(a):
            raise SchemeError("-: argument must be an integer")
    if len(args) == 1:
        return -args[0]
    r = args[0]
    for a in args[1:]:
        r -= a
    return r


def _builtin_quotient(args, out):
    if len(args) != 2:
        raise SchemeError("quotient: exactly 2 arguments")
    a, b = args
    if not _is_int(a) or not _is_int(b):
        raise SchemeError("quotient: arguments must be integers")
    if b == 0:
        raise SchemeError("quotient: division by zero")
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        q = -q
    return q


def _builtin_remainder(args, out):
    if len(args) != 2:
        raise SchemeError("remainder: exactly 2 arguments")
    a, b = args
    if not _is_int(a) or not _is_int(b):
        raise SchemeError("remainder: arguments must be integers")
    if b == 0:
        raise SchemeError("remainder: division by zero")
    r = abs(a) % abs(b)
    if a < 0:
        r = -r
    return r


def _builtin_modulo(args, out):
    if len(args) != 2:
        raise SchemeError("modulo: exactly 2 arguments")
    a, b = args
    if not _is_int(a) or not _is_int(b):
        raise SchemeError("modulo: arguments must be integers")
    if b == 0:
        raise SchemeError("modulo: division by zero")
    r = abs(a) % abs(b)
    if b < 0:
        r = -r
    return r


def _builtin_cmp(args, out, op):
    for a in args:
        if not _is_int(a):
            raise SchemeError("comparison: argument must be an integer")
    for i in range(len(args) - 1):
        if not op(args[i], args[i + 1]):
            return False
    return True


def _builtin_eq(args, out):
    if len(args) != 2:
        raise SchemeError("eq?: exactly 2 arguments")
    a, b = args
    if _is_bool(a) or _is_bool(b):
        return _is_bool(a) and _is_bool(b) and a == b
    if _is_int(a) and _is_int(b):
        return a == b
    if _is_sym(a) and _is_sym(b):
        return a.name == b.name
    if a == () and b == ():
        return True
    return a is b


def _builtin_equal(a, b):
    while True:
        if _is_bool(a) or _is_bool(b):
            return _is_bool(a) and _is_bool(b) and a == b
        if _is_int(a) and _is_int(b):
            return a == b
        if _is_str(a) and _is_str(b):
            return a == b
        if _is_sym(a) and _is_sym(b):
            return a.name == b.name
        if a is UNSPECIFIED or b is UNSPECIFIED:
            return a is b
        if isinstance(a, (Closure, Builtin)) or isinstance(b, (Closure, Builtin)):
            return a is b
        a_empty = (a == ())
        b_empty = (b == ())
        a_plist = isinstance(a, list)
        b_plist = isinstance(b, list)
        a_pair = isinstance(a, SchemePair)
        b_pair = isinstance(b, SchemePair)
        if a_empty and b_empty:
            return True
        if a_empty or b_empty:
            return False
        if a_plist and b_plist:
            if len(a) != len(b):
                return False
            for x, y in zip(a, b):
                if not _builtin_equal(x, y):
                    return False
            return True
        if a_pair and b_pair:
            if not _builtin_equal(a.car, b.car):
                return False
            a, b = a.cdr, b.cdr
            continue
        return False


def _builtin_equal_fn(args, out):
    if len(args) != 2:
        raise SchemeError("equal?: exactly 2 arguments")
    return _builtin_equal(args[0], args[1])


def _builtin_not(args, out):
    if len(args) != 1:
        raise SchemeError("not: exactly 1 argument")
    return args[0] is False


def _builtin_numberp(args, out):
    if len(args) != 1:
        raise SchemeError("number?: exactly 1 argument")
    return _is_int(args[0])


def _builtin_symbolp(args, out):
    if len(args) != 1:
        raise SchemeError("symbol?: exactly 1 argument")
    return _is_sym(args[0])


def _builtin_stringp(args, out):
    if len(args) != 1:
        raise SchemeError("string?: exactly 1 argument")
    return _is_str(args[0])


def _builtin_procedurep(args, out):
    if len(args) != 1:
        raise SchemeError("procedure?: exactly 1 argument")
    return isinstance(args[0], (Closure, Builtin))


def _builtin_nullp(args, out):
    if len(args) != 1:
        raise SchemeError("null?: exactly 1 argument")
    return args[0] == ()


def _builtin_pairp(args, out):
    if len(args) != 1:
        raise SchemeError("pair?: exactly 1 argument")
    return _is_pair(args[0])


def _builtin_listp(args, out):
    if len(args) != 1:
        raise SchemeError("list?: exactly 1 argument")
    return _is_proper_list(args[0])


def _builtin_cons(args, out):
    if len(args) != 2:
        raise SchemeError("cons: exactly 2 arguments")
    a, b = args
    if b == ():
        return [a]
    elif isinstance(b, list):
        return [a] + b
    else:
        return SchemePair(a, b)


def _builtin_car(args, out):
    if len(args) != 1:
        raise SchemeError("car: exactly 1 argument")
    x = args[0]
    if isinstance(x, list):
        if len(x) == 0:
            raise SchemeError("car: null argument")
        return x[0]
    elif _is_pair(x):
        return x.car
    else:
        raise SchemeError("car: not a pair")


def _builtin_cdr(args, out):
    if len(args) != 1:
        raise SchemeError("cdr: exactly 1 argument")
    x = args[0]
    if isinstance(x, list):
        if len(x) == 0:
            raise SchemeError("cdr: null argument")
        return x[1:] if len(x) > 1 else ()
    elif _is_pair(x):
        return x.cdr
    else:
        raise SchemeError("cdr: not a pair")