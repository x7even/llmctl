import sys
import re

try:
    sys.set_int_max_str_digits(0)
except (AttributeError, ValueError):
    pass

sys.setrecursionlimit(100000)


class SchemeError(Exception):
    def __init__(self, msg, output=''):
        super().__init__(msg)
        self.output = output


# ─── Data Types ───────────────────────────────────────────────────────────────

class Sym:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name

class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr

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

EMPTY_LIST = object()
UNSPECIFIED = object()
_UNINITIALIZED = object()

def is_scheme_int(x):
    return isinstance(x, int) and not isinstance(x, bool)

def is_scheme_bool(x):
    return isinstance(x, bool)

def is_str(x):
    return isinstance(x, str)

def is_sym(x):
    return isinstance(x, Sym)

def is_pair(x):
    return isinstance(x, Pair)

def is_empty_list(x):
    return x is EMPTY_LIST

def is_unspecified(x):
    return x is UNSPECIFIED

def is_proc(x):
    return isinstance(x, (Closure, Builtin))

def is_proper_list(x):
    p = x
    while is_pair(p):
        p = p.cdr
    return is_empty_list(p)

def is_true(x):
    return x is not False

def iter_list(lst):
    while is_pair(lst):
        yield lst.car
        lst = lst.cdr

def list_length(lst):
    n = 0
    p = lst
    while is_pair(p):
        n += 1
        p = p.cdr
    return n

def tuple_to_list(args):
    result = EMPTY_LIST
    for a in reversed(args):
        result = Pair(a, result)
    return result

def list_to_pair(elements):
    result = EMPTY_LIST
    for e in reversed(elements):
        result = Pair(e, result)
    return result

def int_to_base(n, base):
    if n == 0:
        return "0"
    negative = n < 0
    n = abs(n)
    digits = []
    while n > 0:
        n, r = divmod(n, base)
        if r < 10:
            digits.append(chr(48 + r))
        else:
            digits.append(chr(97 + r - 10))
    if negative:
        digits.append('-')
    return ''.join(reversed(digits))


# ─── Reader ───────────────────────────────────────────────────────────────────

class Reader:
    def __init__(self, source):
        self.src = source
        self.pos = 0
        self.n = len(source)

    def skip_ws(self):
        while self.pos < self.n:
            c = self.src[self.pos]
            if c in ' \t\n\r':
                self.pos += 1
            elif c == ';':
                while self.pos < self.n and self.src[self.pos] != '\n':
                    self.pos += 1
            else:
                break

    def read(self):
        self.skip_ws()
        if self.pos >= self.n:
            return None
        c = self.src[self.pos]
        if c == '(':
            return self.read_list()
        elif c == '"':
            return self.read_string()
        elif c == "'":
            self.pos += 1
            datum = self.read()
            if datum is None:
                raise SchemeError("syntax error: ' not followed by a datum")
            return Pair(Sym('quote'), Pair(datum, EMPTY_LIST))
        else:
            return self.read_token()

    def read_list(self):
        self.pos += 1  # skip (
        elements = []
        while True:
            self.skip_ws()
            if self.pos >= self.n:
                raise SchemeError("syntax error: unbalanced parenthesis")
            c = self.src[self.pos]
            if c == ')':
                self.pos += 1
                return list_to_pair(elements)
            # Check for dot
            if c == '.':
                if self.pos + 1 < self.n and self.src[self.pos + 1] in ' \t\n\r)':
                    # It's a dot
                    self.pos += 1
                    self.skip_ws()
                    if len(elements) < 1:
                        raise SchemeError("syntax error: dot must be preceded by at least one element")
                    if self.pos >= self.n or self.src[self.pos] == ')':
                        raise SchemeError("syntax error: expected datum after dot")
                    tail = self.read()
                    self.skip_ws()
                    if self.pos >= self.n or self.src[self.pos] != ')':
                        raise SchemeError("syntax error: expected ) after dotted list")
                    self.pos += 1
                    result = tail
                    for e in reversed(elements):
                        result = Pair(e, result)
                    return result
            datum = self.read()
            elements.append(datum)

    def read_string(self):
        self.pos += 1  # skip opening "
        chars = []
        while True:
            if self.pos >= self.n:
                raise SchemeError("syntax error: unterminated string")
            c = self.src[self.pos]
            if c == '"':
                self.pos += 1
                return ''.join(chars)
            elif c == '\\':
                self.pos += 1
                if self.pos >= self.n:
                    raise SchemeError("syntax error: unterminated string")
                ec = self.src[self.pos]
                if ec == '"':
                    chars.append('"')
                elif ec == '\\':
                    chars.append('\\')
                elif ec == 'n':
                    chars.append('\n')
                else:
                    raise SchemeError(f"syntax error: invalid escape \\{ec}")
                self.pos += 1
            else:
                chars.append(c)
                self.pos += 1

    def read_token(self):
        start = self.pos
        while self.pos < self.n:
            c = self.src[self.pos]
            if c in ' \t\n\r()"\'':
                break
            self.pos += 1
        token = self.src[start:self.pos]
        return self.parse_token(token)

    @staticmethod
    def parse_token(token):
        if token == '#t':
            return True
        if token == '#f':
            return False
        if token.startswith('#'):
            raise SchemeError(f"syntax error: invalid token #{token[1:]}")
        if re.fullmatch(r'[+-]?[0-9]+', token):
            return int(token)
        return Sym(token)


def read_all(source):
    r = Reader(source)
    forms = []
    while True:
        form = r.read()
        if form is None:
            break
        forms.append(form)
    return forms


# ─── Environment ──────────────────────────────────────────────────────────────

class Env:
    __slots__ = ('vars', 'parent')
    def __init__(self, vars, parent=None):
        self.vars = vars
        self.parent = parent


def lookup(name, env):
    e = env
    while e is not None:
        if name in e.vars:
            val = e.vars[name]
            if val is _UNINITIALIZED:
                raise SchemeError(f"uninitialized variable: {name.name}")
            return val
        e = e.parent
    raise SchemeError(f"unbound variable: {name.name}")


def set_var(name, value, env):
    e = env
    while e is not None:
        if name in e.vars:
            e.vars[name] = value
            return
        e = e.parent
    raise SchemeError(f"unbound variable: {name.name}")


# ─── Text Representation ──────────────────────────────────────────────────────

def display_repr(x):
    if is_scheme_int(x):
        return int_to_base(x, 10)
    elif x is True:
        return "#t"
    elif x is False:
        return "#f"
    elif is_str(x):
        return x
    elif is_sym(x):
        return x.name
    elif is_empty_list(x):
        return "()"
    elif is_proc(x):
        return "#<procedure>"
    elif is_unspecified(x):
        return ""
    elif is_pair(x):
        parts = ["("]
        first = True
        p = x
        while is_pair(p):
            if not first:
                parts.append(" ")
            parts.append(display_repr(p.car))
            p = p.cdr
            first = False
        if not is_empty_list(p):
            parts.append(" . ")
            parts.append(display_repr(p))
        parts.append(")")
        return ''.join(parts)
    else:
        return "?"


def write_repr(x):
    if is_scheme_int(x):
        return int_to_base(x, 10)
    elif x is True:
        return "#t"
    elif x is False:
        return "#f"
    elif is_str(x):
        escaped = x.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        return f'"{escaped}"'
    elif is_sym(x):
        return x.name
    elif is_empty_list(x):
        return "()"
    elif is_proc(x):
        return "#<procedure>"
    elif is_unspecified(x):
        return ""
    elif is_pair(x):
        parts = ["("]
        first = True
        p = x
        while is_pair(p):
            if not first:
                parts.append(" ")
            parts.append(write_repr(p.car))
            p = p.cdr
            first = False
        if not is_empty_list(p):
            parts.append(" . ")
            parts.append(write_repr(p))
        parts.append(")")
        return ''.join(parts)
    else:
        return "?"


# ─── Evaluator ────────────────────────────────────────────────────────────────

class Continue:
    __slots__ = ('form', 'env')
    def __init__(self, form, env):
        self.form = form
        self.env = env


SPECIAL_FORMS = frozenset(['quote', 'if', 'define', 'set!', 'begin', 'cond',
                           'and', 'or', 'let', 'let*', 'letrec'])


def is_special_form(head):
    return is_sym(head) and head.name in SPECIAL_FORMS


def make_env(formals, args, parent_env):
    if is_sym(formals):
        # Collect all into a list
        lst = tuple_to_list(args)
        return Env({formals: lst}, parent_env)
    elif is_pair(formals):
        if is_proper_list(formals):
            # Fixed arity
            names = list(iter_list(formals))
            for nm in names:
                if not is_sym(nm):
                    raise SchemeError("lambda: formals must be symbols")
            if len(args) != len(names):
                raise SchemeError(f"arity mismatch: expected {len(names)}, got {len(args)}")
            return Env(dict(zip(names, args)), parent_env)
        else:
            # Dotted list
            proper_names = []
            p = formals
            while is_pair(p) and not is_empty_list(p.cdr):
                if not is_sym(p.car):
                    raise SchemeError("lambda: formals must be symbols")
                proper_names.append(p.car)
                p = p.cdr
            # p is now the rest name (a symbol)
            if not is_sym(p):
                raise SchemeError("lambda: rest must be a symbol")
            rest_name = p
            if len(args) < len(proper_names):
                raise SchemeError(f"arity mismatch: expected at least {len(proper_names)}, got {len(args)}")
            env_vars = {nm: a for nm, a in zip(proper_names, args[:len(proper_names)])}
            env_vars[rest_name] = tuple_to_list(args[len(proper_names):])
            return Env(env_vars, parent_env)
    else:
        raise SchemeError("lambda: invalid formals")


def call_proc(op, args):
    if isinstance(op, Closure):
        new_env = make_env(op.formals, args, op.env)
        return Continue(op.body, new_env)
    elif isinstance(op, Builtin):
        return op.func(args)
    else:
        raise SchemeError(f"attempt to apply non-procedure: {display_repr(op)}")


def is_define_form(form):
    return (is_pair(form) and is_sym(form.car) and form.car.name == 'define')


def parse_define(form):
    """Parse a define form. Returns (name, expr_or_lambda_formals, body_or_None)."""
    second = form.cdr.car
    if is_pair(second) and is_sym(second.car):
        name = second.car
        formals = second.cdr
        body_forms = list(iter_list(form.cdr.cdr))
        if not body_forms:
            raise SchemeError("define: empty body")
        return (name, formals, body_forms)
    else:
        name = second
        if not is_sym(name):
            raise SchemeError("define: name must be a symbol")
        expr = form.cdr.cdr.car
        return (name, expr, None)


def setup_internal_defs(forms, env):
    """Set up letrec* environment for internal definitions in a body."""
    names = []
    for f in forms:
        if is_define_form(f):
            name, _, _ = parse_define(f)
            names.append(name)
    if names:
        return Env({nm: _UNINITIALIZED for nm in names}, env)
    return env


def eval_body_tail(forms, env):
    """Evaluate a body in tail position. Returns a value or Continue."""
    env = setup_internal_defs(forms, env)
    for f in forms[:-1]:
        if is_define_form(f):
            name, second, body = parse_define(f)
            if body is not None:
                val = Closure(second, body, env)
            else:
                val = eval_expr(second, env)
            env.vars[name] = val
        else:
            eval_expr(f, env)
    last = forms[-1]
    if is_define_form(last):
        name, second, body = parse_define(last)
        if body is not None:
            val = Closure(second, body, env)
        else:
            val = eval_expr(second, env)
        env.vars[name] = val
        return UNSPECIFIED
    return Continue(last, env)


def eval(form, env):
    """Main tail-call loop. form is a single expression or a body (Python list)."""
    while True:
        if isinstance(form, list):
            # Body
            if not form:
                raise SchemeError("empty body")
            result = eval_body_tail(form, env)
            if isinstance(result, Continue):
                form = result.form
                env = result.env
                continue
            return result

        # Single expression in tail position
        if is_pair(form):
            head = form.car
            if is_special_form(head):
                result = eval_special_tail(head, form, env)
                if isinstance(result, Continue):
                    form = result.form
                    env = result.env
                    continue
                return result
            else:
                # Application
                op = eval_expr(form.car, env)
                args = tuple(eval_expr(p, env) for p in iter_list(form.cdr))
                # Special case: apply in tail position
                if isinstance(op, Builtin) and op.name == 'apply':
                    if len(args) < 2:
                        raise SchemeError("apply: requires at least 2 arguments")
                    f = args[0]
                    lst = args[-1]
                    if not is_proper_list(lst):
                        raise SchemeError("apply: last argument must be a proper list")
                    extra = args[1:-1]
                    combined = extra + tuple(iter_list(lst))
                    result = call_proc(f, combined)
                    if isinstance(result, Continue):
                        form = result.form
                        env = result.env
                        continue
                    return result
                else:
                    result = call_proc(op, args)
                    if isinstance(result, Continue):
                        form = result.form
                        env = result.env
                        continue
                    return result
        elif is_sym(form):
            return lookup(form, env)
        else:
            return form


def eval_expr(form, env):
    """Evaluate form in non-tail position. Returns value."""
    if is_pair(form):
        head = form.car
        if is_special_form(head):
            return eval_special(head, form, env)
        else:
            op = eval_expr(form.car, env)
            args = tuple(eval_expr(p, env) for p in iter_list(form.cdr))
            if isinstance(op, Builtin) and op.name == 'apply':
                if len(args) < 2:
                    raise SchemeError("apply: requires at least 2 arguments")
                f = args[0]
                lst = args[-1]
                if not is_proper_list(lst):
                    raise SchemeError("apply: last argument must be a proper list")
                extra = args[1:-1]
                combined = extra + tuple(iter_list(lst))
                result = call_proc(f, combined)
                if isinstance(result, Continue):
                    return eval(result.form, result.env)
                return result
            else:
                result = call_proc(op, args)
                if isinstance(result, Continue):
                    return eval(result.form, result.env)
                return result
    elif is_sym(form):
        return lookup(form, env)
    else:
        return form


# ─── Special Forms ────────────────────────────────────────────────────────────

def eval_special_tail(head, form, env):
    name = head.name
    if name == 'quote':
        return form.cdr.car
    elif name == 'if':
        return eval_if_tail(form, env)
    elif name == 'define':
        return eval_define_tail(form, env)
    elif name == 'set!':
        return eval_set_tail(form, env)
    elif name == 'begin':
        return eval_begin_tail(form, env)
    elif name == 'cond':
        return eval_cond_tail(form, env)
    elif name == 'and':
        return eval_and_tail(form, env)
    elif name == 'or':
        return eval_or_tail(form, env)
    elif name == 'let':
        return eval_let_tail(form, env)
    elif name == 'let*':
        return eval_letstar_tail(form, env)
    elif name == 'letrec':
        return eval_letrec_tail(form, env)
    else:
        raise SchemeError(f"unknown special form: {name}")


def eval_special(head, form, env):
    name = head.name
    if name == 'quote':
        return form.cdr.car
    elif name == 'if':
        return eval_if(form, env)
    elif name == 'define':
        return eval_define(form, env)
    elif name == 'set!':
        return eval_set(form, env)
    elif name == 'begin':
        return eval_begin(form, env)
    elif name == 'cond':
        return eval_cond(form, env)
    elif name == 'and':
        return eval_and(form, env)
    elif name == 'or':
        return eval_or(form, env)
    elif name == 'let':
        return eval_let(form, env)
    elif name == 'let*':
        return eval_letstar(form, env)
    elif name == 'letrec':
        return eval_letrec(form, env)
    else:
        raise SchemeError(f"unknown special form: {name}")


def eval_if_tail(form, env):
    parts = list(iter_list(form.cdr))
    if len(parts) < 2:
        raise SchemeError("if: requires test and then expression")
    test = eval_expr(parts[0], env)
    if is_true(test):
        return Continue(parts[1], env)
    else:
        if len(parts) >= 3:
            return Continue(parts[2], env)
        return UNSPECIFIED


def eval_if(form, env):
    parts = list(iter_list(form.cdr))
    if len(parts) < 2:
        raise SchemeError("if: requires test and then expression")
    test = eval_expr(parts[0], env)
    if is_true(test):
        return eval_expr(parts[1], env)
    else:
        if len(parts) >= 3:
            return eval_expr(parts[2], env)
        return UNSPECIFIED


def eval_define_tail(form, env):
    name, second, body = parse_define(form)
    if body is not None:
        val = Closure(second, body, env)
    else:
        val = eval_expr(second, env)
    env.vars[name] = val
    return UNSPECIFIED


def eval_define(form, env):
    name, second, body = parse_define(form)
    if body is not None:
        val = Closure(second, body, env)
    else:
        val = eval_expr(second, env)
    env.vars[name] = val
    return UNSPECIFIED


def eval_set_tail(form, env):
    parts = list(iter_list(form.cdr))
    if len(parts) != 2 or not is_sym(parts[0]):
        raise SchemeError("set!: requires a symbol and an expression")
    val = eval_expr(parts[1], env)
    set_var(parts[0], val, env)
    return UNSPECIFIED


def eval_set(form, env):
    parts = list(iter_list(form.cdr))
    if len(parts) != 2 or not is_sym(parts[0]):
        raise SchemeError("set!: requires a symbol and an expression")
    val = eval_expr(parts[1], env)
    set_var(parts[0], val, env)
    return UNSPECIFIED


def eval_begin_tail(form, env):
    exprs = list(iter_list(form.cdr))
    if not exprs:
        raise SchemeError("begin: requires at least one expression")
    for e in exprs[:-1]:
        eval_expr(e, env)
    return Continue(exprs[-1], env)


def eval_begin(form, env):
    exprs = list(iter_list(form.cdr))
    if not exprs:
        raise SchemeError("begin: requires at least one expression")
    for e in exprs[:-1]:
        eval_expr(e, env)
    return eval_expr(exprs[-1], env)


def eval_cond_tail(form, env):
    clauses = list(iter_list(form.cdr))
    for i, clause in enumerate(clauses):
        if not is_pair(clause):
            raise SchemeError("cond: clause must be a list")
        test = clause.car
        if is_sym(test) and test.name == 'else':
            if i != len(clauses) - 1:
                raise SchemeError("cond: else must be the last clause")
            exprs = list(iter_list(clause.cdr))
            if not exprs:
                raise SchemeError("cond: else clause requires expressions")
            for e in exprs[:-1]:
                eval_expr(e, env)
            return Continue(exprs[-1], env)
        else:
            val = eval_expr(test, env)
            if is_true(val):
                exprs = list(iter_list(clause.cdr))
                if not exprs:
                    return val
                for e in exprs[:-1]:
                    eval_expr(e, env)
                return Continue(exprs[-1], env)
    return UNSPECIFIED


def eval_cond(form, env):
    clauses = list(iter_list(form.cdr))
    for i, clause in enumerate(clauses):
        if not is_pair(clause):
            raise SchemeError("cond: clause must be a list")
        test = clause.car
        if is_sym(test) and test.name == 'else':
            if i != len(clauses) - 1:
                raise SchemeError("cond: else must be the last clause")
            exprs = list(iter_list(clause.cdr))
            if not exprs:
                raise SchemeError("cond: else clause requires expressions")
            for e in exprs[:-1]:
                eval_expr(e, env)
            return eval_expr(exprs[-1], env)
        else:
            val = eval_expr(test, env)
            if is_true(val):
                exprs = list(iter_list(clause.cdr))
                if not exprs:
                    return val
                for e in exprs[:-1]:
                    eval_expr(e, env)
                return eval_expr(exprs[-1], env)
    return UNSPECIFIED


def eval_and_tail(form, env):
    exprs = list(iter_list(form.cdr))
    for e in exprs[:-1]:
        val = eval_expr(e, env)
        if val is False:
            return False
    if not exprs:
        return True
    return Continue(exprs[-1], env)


def eval_and(form, env):
    exprs = list(iter_list(form.cdr))
    result = True
    for e in exprs:
        result = eval_expr(e, env)
        if result is False:
            return False
    return result


def eval_or_tail(form, env):
    exprs = list(iter_list(form.cdr))
    for e in exprs[:-1]:
        val = eval_expr(e, env)
        if is_true(val):
            return val
    if not exprs:
        return False
    return Continue(exprs[-1], env)


def eval_or(form, env):
    exprs = list(iter_list(form.cdr))
    for e in exprs:
        val = eval_expr(e, env)
        if is_true(val):
            return val
    return False


def eval_let_tail(form, env):
    # (let ((v init) ...) body...) or (let name ((v init) ...) body...)
    second = form.cdr.car
    if is_sym(second):
        # Named let
        name = second
        bindings = list(iter_list(form.cdr.cdr.car))
        body = list(iter_list(form.cdr.cdr.cdr))
        if not body:
            raise SchemeError("let: empty body")
        v_names = []
        values = []
        for b in bindings:
            if not is_pair(b) or not is_pair(b.cdr) or not is_sym(b.car):
                raise SchemeError("let: invalid binding")
            v_names.append(b.car)
            values.append(eval_expr(b.cdr.car, env))
        new_env = Env({name: _UNINITIALIZED}, env)
        for v in v_names:
            new_env.vars[v] = _UNINITIALIZED
        closure = Closure(tuple_to_list(v_names), body, new_env)
        new_env.vars[name] = closure
        result = call_proc(closure, tuple(values))
        return result
    else:
        # Regular let
        bindings = list(iter_list(second))
        body = list(iter_list(form.cdr.cdr))
        if not body:
            raise SchemeError("let: empty body")
        names = []
        values = []
        for b in bindings:
            if not is_pair(b) or not is_pair(b.cdr) or not is_sym(b.car):
                raise SchemeError("let: invalid binding")
            names.append(b.car)
            values.append(eval_expr(b.cdr.car, env))
        new_env = Env(dict(zip(names, values)), env)
        return Continue(body, new_env)


def eval_let(form, env):
    second = form.cdr.car
    if is_sym(second):
        # Named let
        name = second
        bindings = list(iter_list(form.cdr.cdr.car))
        body = list(iter_list(form.cdr.cdr.cdr))
        if not body:
            raise SchemeError("let: empty body")
        v_names = []
        values = []
        for b in bindings:
            if not is_pair(b) or not is_pair(b.cdr) or not is_sym(b.car):
                raise SchemeError("let: invalid binding")
            v_names.append(b.car)
            values.append(eval_expr(b.cdr.car, env))
        new_env = Env({name: _UNINITIALIZED}, env)
        for v in v_names:
            new_env.vars[v] = _UNINITIALIZED
        closure = Closure(tuple_to_list(v_names), body, new_env)
        new_env.vars[name] = closure
        result = call_proc(closure, tuple(values))
        if isinstance(result, Continue):
            return eval(result.form, result.env)
        return result
    else:
        bindings = list(iter_list(second))
        body = list(iter_list(form.cdr.cdr))
        if not body:
            raise SchemeError("let: empty body")
        names = []
        values = []
        for b in bindings:
            if not is_pair(b) or not is_pair(b.cdr) or not is_sym(b.car):
                raise SchemeError("let: invalid binding")
            names.append(b.car)
            values.append(eval_expr(b.cdr.car, env))
        new_env = Env(dict(zip(names, values)), env)
        return eval(body, new_env)


def eval_letstar_tail(form, env):
    bindings = list(iter_list(form.cdr.car))
    body = list(iter_list(form.cdr.cdr))
    if not body:
        raise SchemeError("let*: empty body")
    new_env = Env({}, env)
    for b in bindings:
        if not is_pair(b) or not is_pair(b.cdr) or not is_sym(b.car):
            raise SchemeError("let*: invalid binding")
        val = eval_expr(b.cdr.car, new_env)
        new_env.vars[b.car] = val
    return Continue(body, new_env)


def eval_letstar(form, env):
    bindings = list(iter_list(form.cdr.car))
    body = list(iter_list(form.cdr.cdr))
    if not body:
        raise SchemeError("let*: empty body")
    new_env = Env({}, env)
    for b in bindings:
        if not is_pair(b) or not is_pair(b.cdr) or not is_sym(b.car):
            raise SchemeError("let*: invalid binding")
        val = eval_expr(b.cdr.car, new_env)
        new_env.vars[b.car] = val
    return eval(body, new_env)


def eval_letrec_tail(form, env):
    bindings = list(iter_list(form.cdr.car))
    body = list(iter_list(form.cdr.cdr))
    if not body:
        raise SchemeError("letrec: empty body")
    names = []
    for b in bindings:
        if not is_pair(b) or not is_pair(b.cdr) or not is_sym(b.car):
            raise SchemeError("letrec: invalid binding")
        names.append(b.car)
    new_env = Env({nm: _UNINITIALIZED for nm in names}, env)
    for b in bindings:
        val = eval_expr(b.cdr.car, new_env)
        new_env.vars[b.car] = val
    return Continue(body, new_env)


def eval_letrec(form, env):
    bindings = list(iter_list(form.cdr.car))
    body = list(iter_list(form.cdr.cdr))
    if not body:
        raise SchemeError("letrec: empty body")
    names = []
    for b in bindings:
        if not is_pair(b) or not is_pair(b.cdr) or not is_sym(b.car):
            raise SchemeError("letrec: invalid binding")
        names.append(b.car)
    new_env = Env({nm: _UNINITIALIZED for nm in names}, env)
    for b in bindings:
        val = eval_expr(b.cdr.car, new_env)
        new_env.vars[b.car] = val
    return eval(body, new_env)


# ─── Builtins ─────────────────────────────────────────────────────────────────

def make_global_env(output):
    g = {}

    def builtin_add(args):
        for a in args:
            if not is_scheme_int(a):
                raise SchemeError("+: all arguments must be integers")
        return sum(args)

    def builtin_mul(args):
        for a in args:
            if not is_scheme_int(a):
                raise SchemeError("*: all arguments must be integers")
        r = 1
        for a in args:
            r *= a
        return r

    def builtin_sub(args):
        for a in args:
            if not is_scheme_int(a):
                raise SchemeError("-: all arguments must be integers")
        if len(args) == 1:
            return -args[0]
        r = args[0]
        for a in args[1:]:
            r -= a
        return r

    def builtin_quotient(args):
        if len(args) != 2:
            raise SchemeError("quotient: requires exactly 2 arguments")
        a, b = args
        if not is_scheme_int(a) or not is_scheme_int(b):
            raise SchemeError("quotient: arguments must be integers")
        if b == 0:
            raise SchemeError("quotient: division by zero")
        q = abs(a) // abs(b)
        if (a < 0) != (b < 0):
            q = -q
        return q

    def builtin_remainder(args):
        if len(args) != 2:
            raise SchemeError("remainder: requires exactly 2 arguments")
        a, b = args
        if not is_scheme_int(a) or not is_scheme_int(b):
            raise SchemeError("remainder: arguments must be integers")
        if b == 0:
            raise SchemeError("remainder: division by zero")
        r = abs(a) % abs(b)
        if a < 0:
            r = -r
        return r

    def builtin_modulo(args):
        if len(args) != 2:
            raise SchemeError("modulo: requires exactly 2 arguments")
        a, b = args
        if not is_scheme_int(a) or not is_scheme_int(b):
            raise SchemeError("modulo: arguments must be integers")
        if b == 0:
            raise SchemeError("modulo: division by zero")
        r = abs(a) % abs(b)
        if b < 0:
            r = -r
        return r

    def make_cmp(op_func):
        def cmp(args):
            if len(args) < 1:
                raise SchemeError("comparison: requires at least 1 argument")
            for a in args:
                if not is_scheme_int(a):
                    raise SchemeError("comparison: all arguments must be integers")
            for i in range(len(args) - 1):
                if not op_func(args[i], args[i + 1]):
                    return False
            return True
        return cmp

    def builtin_number_to_string(args):
        if len(args) not in (1, 2):
            raise SchemeError("number->string: requires 1 or 2 arguments")
        n = args[0]
        if not is_scheme_int(n):
            raise SchemeError("number->string: first argument must be an integer")
        if len(args) == 1:
            return int_to_base(n, 10)
        radix = args[1]
        if not is_scheme_int(radix) or radix not in (2, 8, 10, 16):
            raise SchemeError("number->string: radix must be 2, 8, 10, or 16")
        return int_to_base(n, radix)

    def builtin_cons(args):
        if len(args) != 2:
            raise SchemeError("cons: requires exactly 2 arguments")
        return Pair(args[0], args[1])

    def builtin_car(args):
        if len(args) != 1:
            raise SchemeError("car: requires exactly 1 argument")
        if not is_pair(args[0]):
            raise SchemeError("car: argument must be a pair")
        return args[0].car

    def builtin_cdr(args):
        if len(args) != 1:
            raise SchemeError("cdr: requires exactly 1 argument")
        if not is_pair(args[0]):
            raise SchemeError("cdr: argument must be a pair")
        return args[0].cdr

    def builtin_list(args):
        return tuple_to_list(args)

    def builtin_null_p(args):
        if len(args) != 1:
            raise SchemeError("null?: requires exactly 1 argument")
        return is_empty_list(args[0])

    def builtin_pair_p(args):
        if len(args) != 1:
            raise SchemeError("pair?: requires exactly 1 argument")
        return is_pair(args[0])

    def builtin_list_p(args):
        if len(args) != 1:
            raise SchemeError("list?: requires exactly 1 argument")
        return is_proper_list(args[0])

    def builtin_length(args):
        if len(args) != 1:
            raise SchemeError("length: requires exactly 1 argument")
        if not is_proper_list(args[0]):
            raise SchemeError("length: argument must be a proper list")
        return list_length(args[0])

    def builtin_append(args):
        if len(args) == 0:
            return EMPTY_LIST
        if len(args) == 1:
            return args[0]
        # All but last must be proper lists
        for a in args[:-1]:
            if not is_proper_list(a):
                raise SchemeError("append: all but last argument must be proper lists")
        last = args[-1]
        # Build result by appending
        result = last
        for a in reversed(args[:-1]):
            # Prepend elements of a to result
            elems = list(iter_list(a))
            for e in reversed(elems):
                result = Pair(e, result)
        return result

    def builtin_reverse(args):
        if len(args) != 1:
            raise SchemeError("reverse: requires exactly 1 argument")
        if not is_proper_list(args[0]):
            raise SchemeError("reverse: argument must be a proper list")
        result = EMPTY_LIST
        p = args[0]
        while is_pair(p):
            result = Pair(p.car, result)
            p = p.cdr
        return result

    def builtin_apply(args):
        if len(args) < 2:
            raise SchemeError("apply: requires at least 2 arguments")
        f = args[0]
        lst = args[-1]
        if not is_proper_list(lst):
            raise SchemeError("apply: last argument must be a proper list")
        extra = args[1:-1]
        combined = extra + tuple(iter_list(lst))
        result = call_proc(f, combined)
        if isinstance(result, Continue):
            return eval(result.form, result.env)
        return result

    def builtin_eq(args):
        if len(args) != 2:
            raise SchemeError("eq?: requires exactly 2 arguments")
        a, b = args
        if is_scheme_int(a) and is_scheme_int(b):
            return a == b
        if is_scheme_bool(a) and is_scheme_bool(b):
            return a == b
        if is_sym(a) and is_sym(b):
            return a.name == b.name
        if is_empty_list(a) and is_empty_list(b):
            return True
        return a is b

    def builtin_equal(args):
        if len(args) != 2:
            raise SchemeError("equal?: requires exactly 2 arguments")
        return _scheme_equal(args[0], args[1])

    def _scheme_equal(a, b):
        if is_scheme_int(a) and is_scheme_int(b):
            return a == b
        if is_scheme_bool(a) and is_scheme_bool(b):
            return a == b
        if is_scheme_int(a) and is_scheme_bool(b):
            return False
        if is_scheme_bool(a) and is_scheme_int(b):
            return False
        if is_str(a) and is_str(b):
            return a == b
        if is_sym(a) and is_sym(b):
            return a.name == b.name
        if is_empty_list(a) and is_empty_list(b):
            return True
        if is_pair(a) and is_pair(b):
            # Iterative for flat lists, recursive for nested
            pa, pb = a, b
            while is_pair(pa) and is_pair(pb):
                if not _scheme_equal(pa.car, pb.car):
                    return False
                pa = pa.cdr
                pb = pb.cdr
            if is_empty_list(pa) and is_empty_list(pb):
                return True
            if not is_pair(pa) and not is_pair(pb):
                return _scheme_equal(pa, pb)
            return False
        if is_proc(a) and is_proc(b):
            return a is b
        if is_unspecified(a) and is_unspecified(b):
            return True
        return False

    def builtin_not(args):
        if len(args) != 1:
            raise SchemeError("not: requires exactly 1 argument")
        return args[0] is False

    def builtin_number_p(args):
        if len(args) != 1:
            raise SchemeError("number?: requires exactly 1 argument")
        return is_scheme_int(args[0])

    def builtin_symbol_p(args):
        if len(args) != 1:
            raise SchemeError("symbol?: requires exactly 1 argument")
        return is_sym(args[0])

    def builtin_string_p(args):
        if len(args) != 1:
            raise SchemeError("string?: requires exactly 1 argument")
        return is_str(args[0])

    def builtin_procedure_p(args):
        if len(args) != 1:
            raise SchemeError("procedure?: requires exactly 1 argument")
        return is_proc(args[0])

    def builtin_string_append(args):
        for a in args:
            if not is_str(a):
                raise SchemeError("string-append: all arguments must be strings")
        return ''.join(args)

    def builtin_display(args):
        if len(args) != 1:
            raise SchemeError("display: requires exactly 1 argument")
        output.append(display_repr(args[0]))
        return UNSPECIFIED

    def builtin_newline(args):
        if len(args) != 0:
            raise SchemeError("newline: requires 0 arguments")
        output.append("\n")
        return UNSPECIFIED

    def builtin_error(args):
        if len(args) < 1:
            raise SchemeError("error: requires at least 1 argument")
        msg = args[0]
        if not is_str(msg):
            raise SchemeError("error: first argument must be a string")
        parts = [msg]
        for irritant in args[1:]:
            parts.append(' ')
            parts.append(write_repr(irritant))
        raise SchemeError(''.join(parts))

    g[Sym('+')] = Builtin('+', builtin_add)
    g[Sym('*')] = Builtin('*', builtin_mul)
    g[Sym('-')] = Builtin('-', builtin_sub)
    g[Sym('quotient')] = Builtin('quotient', builtin_quotient)
    g[Sym('remainder')] = Builtin('remainder', builtin_remainder)
    g[Sym('modulo')] = Builtin('modulo', builtin_modulo)
    g[Sym('=')] = Builtin('=', make_cmp(lambda a, b: a == b))
    g[Sym('<')] = Builtin('<', make_cmp(lambda a, b: a < b))
    g[Sym('>')] = Builtin('>', make_cmp(lambda a, b: a > b))
    g[Sym('<=')] = Builtin('<=', make_cmp(lambda a, b: a <= b))
    g[Sym('>=')] = Builtin('>=', make_cmp(lambda a, b: a >= b))
    g[Sym('number->string')] = Builtin('number->string', builtin_number_to_string)
    g[Sym('cons')] = Builtin('cons', builtin_cons)
    g[Sym('car')] = Builtin('car', builtin_car)
    g[Sym('cdr')] = Builtin('cdr', builtin_cdr)
    g[Sym('list')] = Builtin('list', builtin_list)
    g[Sym('null?')] = Builtin('null?', builtin_null_p)
    g[Sym('pair?')] = Builtin('pair?', builtin_pair_p)
    g[Sym('list?')] = Builtin('list?', builtin_list_p)
    g[Sym('length')] = Builtin('length', builtin_length)
    g[Sym('append')] = Builtin('append', builtin_append)
    g[Sym('reverse')] = Builtin('reverse', builtin_reverse)
    g[Sym('apply')] = Builtin('apply', builtin_apply)
    g[Sym('eq?')] = Builtin('eq?', builtin_eq)
    g[Sym('equal?')] = Builtin('equal?', builtin_equal)
    g[Sym('not')] = Builtin('not', builtin_not)
    g[Sym('number?')] = Builtin('number?', builtin_number_p)
    g[Sym('symbol?')] = Builtin('symbol?', builtin_symbol_p)
    g[Sym('string?')] = Builtin('string?', builtin_string_p)
    g[Sym('procedure?')] = Builtin('procedure?', builtin_procedure_p)
    g[Sym('string-append')] = Builtin('string-append', builtin_string_append)
    g[Sym('display')] = Builtin('display', builtin_display)
    g[Sym('newline')] = Builtin('newline', builtin_newline)
    g[Sym('error')] = Builtin('error', builtin_error)

    return Env(g)


# ─── Public API ───────────────────────────────────────────────────────────────

def run(source):
    output = []
    try:
        forms = read_all(source)
    except SchemeError:
        raise
    except Exception as e:
        raise SchemeError(str(e))

    global_env = make_global_env(output)

    try:
        for form in forms:
            eval(form, global_env)
    except SchemeError as e:
        e.output = ''.join(output)
        raise
    except RecursionError:
        raise SchemeError("stack overflow", ''.join(output))
    except Exception as e:
        raise SchemeError(str(e), ''.join(output))

    return ''.join(output)