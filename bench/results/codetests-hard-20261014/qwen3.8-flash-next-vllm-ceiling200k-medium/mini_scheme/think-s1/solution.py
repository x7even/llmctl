import sys
import threading
import re

try:
    sys.set_int_max_str_digits(0)
except (AttributeError, ValueError):
    pass


class SchemeError(Exception):
    def __init__(self, msg='', output=''):
        super().__init__(msg)
        self.output = output


# ─── Data types ───────────────────────────────────────────────────────────────

class Symbol:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name
    def __repr__(self):
        return self.name

_symbol_table = {}
def make_symbol(name):
    if name not in _symbol_table:
        _symbol_table[name] = Symbol(name)
    return _symbol_table[name]

class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr

class _EmptyList:
    def __repr__(self):
        return '()'
EMPTY_LIST = _EmptyList()

class _Bool:
    __slots__ = ('val',)
    def __init__(self, val):
        self.val = val
    def __repr__(self):
        return '#t' if self.val else '#f'
TRUE = _Bool(True)
FALSE = _Bool(False)

class _Unspecified:
    def __repr__(self):
        return '#<unspecified>'
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
    __slots__ = ('func', 'name')
    def __init__(self, func, name=''):
        self.func = func
        self.name = name


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
                    raise SchemeError(f"uninitialized variable: {name}")
                return val
            env = env.parent
        raise SchemeError(f"unbound variable: {name}")

    def set(self, name, value):
        env = self
        while env is not None:
            if name in env.bindings:
                env.bindings[name] = value
                return
            env = env.parent
        raise SchemeError(f"unbound variable: {name}")

    def define(self, name, value):
        self.bindings[name] = value


# ─── Reader ───────────────────────────────────────────────────────────────────

_INT_RE = re.compile(r'^[+-]?[0-9]+$')

class Reader:
    def __init__(self, source):
        self.src = source
        self.pos = 0
        self.length = len(source)

    def skip_ws(self):
        while self.pos < self.length:
            ch = self.src[self.pos]
            if ch in ' \t\n\r':
                self.pos += 1
            elif ch == ';':
                while self.pos < self.length and self.src[self.pos] != '\n':
                    self.pos += 1
            else:
                break

    def read_datum(self):
        self.skip_ws()
        if self.pos >= self.length:
            raise SchemeError("unexpected end of input")
        ch = self.src[self.pos]
        if ch == '(':
            return self.read_list()
        elif ch == ')':
            raise SchemeError("unexpected )")
        elif ch == "'":
            self.pos += 1
            datum = self.read_datum()
            return Pair(make_symbol('quote'), Pair(datum, EMPTY_LIST))
        elif ch == '"':
            return self.read_string()
        else:
            return self.read_atom()

    def read_list(self):
        self.pos += 1  # skip (
        elements = []
        while True:
            self.skip_ws()
            if self.pos >= self.length:
                raise SchemeError("unbalanced (")
            if self.src[self.pos] == ')':
                self.pos += 1
                result = EMPTY_LIST
                for e in reversed(elements):
                    result = Pair(e, result)
                return result
            datum = self.read_datum()
            if isinstance(datum, Symbol) and datum.name == '.':
                if len(elements) == 0:
                    raise SchemeError("dot without preceding element")
                dot_val = self.read_datum()
                self.skip_ws()
                if self.pos >= self.length or self.src[self.pos] != ')':
                    raise SchemeError("expected ) after dot datum")
                self.pos += 1
                result = dot_val
                for e in reversed(elements):
                    result = Pair(e, result)
                return result
            elements.append(datum)

    def read_string(self):
        self.pos += 1  # skip "
        chars = []
        while self.pos < self.length:
            ch = self.src[self.pos]
            if ch == '"':
                self.pos += 1
                return ''.join(chars)
            elif ch == '\\':
                self.pos += 1
                if self.pos >= self.length:
                    raise SchemeError("unterminated string")
                esc = self.src[self.pos]
                if esc == '"':
                    chars.append('"')
                elif esc == '\\':
                    chars.append('\\')
                elif esc == 'n':
                    chars.append('\n')
                else:
                    raise SchemeError(f"invalid escape: \\{esc}")
                self.pos += 1
            else:
                chars.append(ch)
                self.pos += 1
        raise SchemeError("unterminated string")

    def read_atom(self):
        start = self.pos
        while self.pos < self.length and self.src[self.pos] not in ' \t\n\r()";\'':
            self.pos += 1
        token = self.src[start:self.pos]
        if not token:
            raise SchemeError("unexpected character")
        if token[0] == '#':
            if token == '#t':
                return TRUE
            if token == '#f':
                return FALSE
            raise SchemeError(f"invalid syntax: {token}")
        if _INT_RE.match(token):
            return int(token)
        return make_symbol(token)

    def has_more(self):
        self.skip_ws()
        return self.pos < self.length


def read_all(source):
    reader = Reader(source)
    forms = []
    while reader.has_more():
        forms.append(reader.read_datum())
    return forms


# ─── Helpers ──────────────────────────────────────────────────────────────────

def to_proper_list(x):
    result = []
    cur = x
    while isinstance(cur, Pair):
        result.append(cur.car)
        cur = cur.cdr
    if isinstance(cur, _EmptyList):
        return result
    return None

def to_pair_list(lst):
    result = EMPTY_LIST
    for item in reversed(lst):
        result = Pair(item, result)
    return result

def is_proper_list(x):
    while isinstance(x, Pair):
        x = x.cdr
    return isinstance(x, _EmptyList)

def is_true(x):
    return x is not FALSE

def parse_binding(binding):
    if not isinstance(binding, Pair):
        raise SchemeError("malformed binding")
    var = binding.car
    if not isinstance(var, Symbol):
        raise SchemeError("malformed binding: variable must be a symbol")
    rest = binding.cdr
    if not isinstance(rest, Pair) or not isinstance(rest.cdr, _EmptyList):
        raise SchemeError("malformed binding: must have exactly one init expression")
    return var, rest.car


# ─── Display / Write ─────────────────────────────────────────────────────────

def display_value(x, output):
    if isinstance(x, int):
        output.append(str(x))
    elif x is TRUE:
        output.append('#t')
    elif x is FALSE:
        output.append('#f')
    elif isinstance(x, str):
        output.append(x)
    elif isinstance(x, Symbol):
        output.append(x.name)
    elif isinstance(x, _EmptyList):
        output.append('()')
    elif isinstance(x, _Unspecified):
        pass
    elif isinstance(x, (Closure, Builtin)):
        output.append('#<procedure>')
    elif isinstance(x, Pair):
        output.append('(')
        display_value(x.car, output)
        cur = x.cdr
        while isinstance(cur, Pair):
            output.append(' ')
            display_value(cur.car, output)
            cur = cur.cdr
        if not isinstance(cur, _EmptyList):
            output.append(' . ')
            display_value(cur, output)
        output.append(')')
    else:
        output.append(str(x))

def write_value(x, output):
    if isinstance(x, str):
        output.append('"')
        for ch in x:
            if ch == '"':
                output.append('\\"')
            elif ch == '\\':
                output.append('\\\\')
            elif ch == '\n':
                output.append('\\n')
            else:
                output.append(ch)
        output.append('"')
    elif isinstance(x, Pair):
        output.append('(')
        write_value(x.car, output)
        cur = x.cdr
        while isinstance(cur, Pair):
            output.append(' ')
            write_value(cur.car, output)
            cur = cur.cdr
        if not isinstance(cur, _EmptyList):
            output.append(' . ')
            write_value(cur, output)
        output.append(')')
    else:
        display_value(x, output)


# ─── Evaluator ────────────────────────────────────────────────────────────────

def setup_body(body, base_env):
    internal_defs = []
    for form in body:
        if isinstance(form, Pair) and isinstance(form.car, Symbol) and form.car.name == 'define':
            name = _extract_define_name(form)
            if name is not None:
                internal_defs.append(name)
    if internal_defs:
        frame = {name: UNINITIALIZED for name in internal_defs}
        return Env(frame, base_env)
    return base_env

def _extract_define_name(form):
    target = form.cdr.car if isinstance(form.cdr, Pair) else None
    if isinstance(target, Symbol):
        return target.name
    if isinstance(target, Pair) and isinstance(target.car, Symbol):
        return target.car.name
    return None

def make_call_env(closure, args):
    formals = closure.formals
    if isinstance(formals, Symbol):
        frame = {formals.name: to_pair_list(args)}
    elif isinstance(formals, _EmptyList):
        if len(args) != 0:
            raise SchemeError("wrong number of arguments")
        frame = {}
    elif isinstance(formals, Pair):
        frame = {}
        cur = formals
        i = 0
        while isinstance(cur, Pair):
            if i >= len(args):
                raise SchemeError("too few arguments")
            if not isinstance(cur.car, Symbol):
                raise SchemeError("malformed formals")
            frame[cur.car.name] = args[i]
            cur = cur.cdr
            i += 1
        if isinstance(cur, Symbol):
            frame[cur.name] = to_pair_list(args[i:])
        elif isinstance(cur, _EmptyList):
            if i != len(args):
                raise SchemeError("wrong number of arguments")
        else:
            raise SchemeError("malformed formals")
    else:
        raise SchemeError("malformed formals")
    return Env(frame, closure.env)

def validate_formals(formals):
    if isinstance(formals, Symbol):
        return
    if isinstance(formals, _EmptyList):
        return
    if isinstance(formals, Pair):
        cur = formals
        while isinstance(cur, Pair):
            if not isinstance(cur.car, Symbol):
                raise SchemeError("malformed lambda: non-symbol in formals")
            cur = cur.cdr
        if isinstance(cur, Symbol) or isinstance(cur, _EmptyList):
            return
    raise SchemeError("malformed lambda: invalid formals")


def eval_expr(expr, env, output):
    while True:
        if isinstance(expr, int):
            return expr
        if expr is TRUE or expr is FALSE:
            return expr
        if isinstance(expr, str):
            return expr
        if isinstance(expr, Symbol):
            return env.lookup(expr.name)
        if isinstance(expr, _EmptyList):
            raise SchemeError("cannot evaluate ()")
        if isinstance(expr, (Closure, Builtin, _Unspecified, _Uninitialized)):
            return expr
        if not isinstance(expr, Pair):
            raise SchemeError("cannot evaluate expression")

        head = expr.car
        if isinstance(head, Symbol):
            name = head.name

            # ── quote ──
            if name == 'quote':
                rest = expr.cdr
                if not isinstance(rest, Pair) or not isinstance(rest.cdr, _EmptyList):
                    raise SchemeError("malformed quote")
                return rest.car

            # ── if ──
            elif name == 'if':
                parts = to_proper_list(expr.cdr)
                if parts is None or len(parts) < 2 or len(parts) > 3:
                    raise SchemeError("malformed if")
                test_val = eval_expr(parts[0], env, output)
                if is_true(test_val):
                    expr = parts[1]
                    continue
                elif len(parts) == 3:
                    expr = parts[2]
                    continue
                else:
                    return UNSPECIFIED

            # ── define ──
            elif name == 'define':
                rest = expr.cdr
                if not isinstance(rest, Pair):
                    raise SchemeError("malformed define")
                target = rest.car
                if isinstance(target, Symbol):
                    body = to_proper_list(rest.cdr)
                    if body is None or len(body) != 1:
                        raise SchemeError("malformed define")
                    val = eval_expr(body[0], env, output)
                    env.define(target.name, val)
                elif isinstance(target, Pair):
                    if not isinstance(target.car, Symbol):
                        raise SchemeError("malformed define")
                    formals = target.cdr
                    body = to_proper_list(rest.cdr)
                    if body is None or len(body) == 0:
                        raise SchemeError("malformed define")
                    validate_formals(formals)
                    lam_expr = Pair(make_symbol('lambda'), Pair(formals, to_pair_list(body)))
                    closure = eval_expr(lam_expr, env, output)
                    env.define(target.car.name, closure)
                else:
                    raise SchemeError("malformed define")
                return UNSPECIFIED

            # ── set! ──
            elif name == 'set!':
                parts = to_proper_list(expr.cdr)
                if parts is None or len(parts) != 2:
                    raise SchemeError("malformed set!")
                target, val_expr = parts
                if not isinstance(target, Symbol):
                    raise SchemeError("malformed set!")
                val = eval_expr(val_expr, env, output)
                env.set(target.name, val)
                return UNSPECIFIED

            # ── begin ──
            elif name == 'begin':
                parts = to_proper_list(expr.cdr)
                if parts is None or len(parts) == 0:
                    raise SchemeError("malformed begin")
                for form in parts[:-1]:
                    eval_expr(form, env, output)
                expr = parts[-1]
                continue

            # ── cond ──
            elif name == 'cond':
                clauses = to_proper_list(expr.cdr)
                if clauses is None:
                    raise SchemeError("malformed cond")
                matched = False
                for i, clause in enumerate(clauses):
                    if not isinstance(clause, Pair):
                        raise SchemeError("malformed cond clause")
                    test = clause.car
                    body = to_proper_list(clause.cdr)
                    if body is None:
                        raise SchemeError("malformed cond clause")
                    if isinstance(test, Symbol) and test.name == 'else':
                        if i != len(clauses) - 1:
                            raise SchemeError("else not last in cond")
                        if len(body) == 0:
                            return UNSPECIFIED
                        for form in body[:-1]:
                            eval_expr(form, env, output)
                        expr = body[-1]
                        matched = True
                        break
                    else:
                        test_val = eval_expr(test, env, output)
                        if is_true(test_val):
                            if len(body) == 0:
                                return test_val
                            for form in body[:-1]:
                                eval_expr(form, env, output)
                            expr = body[-1]
                            matched = True
                            break
                if not matched:
                    return UNSPECIFIED
                continue

            # ── and ──
            elif name == 'and':
                parts = to_proper_list(expr.cdr)
                if parts is None:
                    raise SchemeError("malformed and")
                if len(parts) == 0:
                    return TRUE
                for form in parts[:-1]:
                    val = eval_expr(form, env, output)
                    if not is_true(val):
                        return FALSE
                expr = parts[-1]
                continue

            # ── or ──
            elif name == 'or':
                parts = to_proper_list(expr.cdr)
                if parts is None:
                    raise SchemeError("malformed or")
                if len(parts) == 0:
                    return FALSE
                for form in parts[:-1]:
                    val = eval_expr(form, env, output)
                    if is_true(val):
                        return val
                expr = parts[-1]
                continue

            # ── lambda ──
            elif name == 'lambda':
                rest = expr.cdr
                if not isinstance(rest, Pair):
                    raise SchemeError("malformed lambda")
                formals = rest.car
                body = to_proper_list(rest.cdr)
                if body is None or len(body) == 0:
                    raise SchemeError("malformed lambda")
                validate_formals(formals)
                return Closure(formals, body, env)

            # ── let / named let ──
            elif name == 'let':
                rest = expr.cdr
                if not isinstance(rest, Pair):
                    raise SchemeError("malformed let")
                if isinstance(rest.car, Symbol):
                    # Named let
                    let_name = rest.car
                    bindings_expr = rest.cdr
                    if not isinstance(bindings_expr, Pair):
                        raise SchemeError("malformed named let")
                    bindings_list = to_proper_list(bindings_expr.car)
                    body = to_proper_list(bindings_expr.cdr)
                    if bindings_list is None or body is None or len(body) == 0:
                        raise SchemeError("malformed named let")
                    formals_syms = []
                    inits = []
                    for b in bindings_list:
                        v, init = parse_binding(b)
                        formals_syms.append(v)
                        inits.append(init)
                    formals = to_pair_list(formals_syms)
                    lam = Closure(formals, body, env)
                    frame = {let_name.name: lam}
                    let_env = Env(frame, env)
                    lam.env = let_env
                    args = [eval_expr(init, env, output) for init in inits]
                    new_env = make_call_env(lam, args)
                    body_env = setup_body(body, new_env)
                    for form in body[:-1]:
                        eval_expr(form, body_env, output)
                    expr = body[-1]
                    env = body_env
                    continue
                else:
                    # Regular let
                    bindings_expr = rest.car
                    body = to_proper_list(rest.cdr)
                    if body is None or len(body) == 0:
                        raise SchemeError("malformed let")
                    bindings_list = to_proper_list(bindings_expr)
                    if bindings_list is None:
                        raise SchemeError("malformed let")
                    names = []
                    values = []
                    for b in bindings_list:
                        v, init = parse_binding(b)
                        names.append(v.name)
                        values.append(eval_expr(init, env, output))
                    frame = dict(zip(names, values))
                    new_env = Env(frame, env)
                    body_env = setup_body(body, new_env)
                    for form in body[:-1]:
                        eval_expr(form, body_env, output)
                    expr = body[-1]
                    env = body_env
                    continue

            # ── let* ──
            elif name == 'let*':
                rest = expr.cdr
                if not isinstance(rest, Pair):
                    raise SchemeError("malformed let*")
                bindings_expr = rest.car
                body = to_proper_list(rest.cdr)
                if body is None or len(body) == 0:
                    raise SchemeError("malformed let*")
                bindings_list = to_proper_list(bindings_expr)
                if bindings_list is None:
                    raise SchemeError("malformed let*")
                cur_env = env
                for b in bindings_list:
                    v, init = parse_binding(b)
                    val = eval_expr(init, cur_env, output)
                    cur_env = Env({v.name: val}, cur_env)
                body_env = setup_body(body, cur_env)
                for form in body[:-1]:
                    eval_expr(form, body_env, output)
                expr = body[-1]
                env = body_env
                continue

            # ── letrec ──
            elif name == 'letrec':
                rest = expr.cdr
                if not isinstance(rest, Pair):
                    raise SchemeError("malformed letrec")
                bindings_expr = rest.car
                body = to_proper_list(rest.cdr)
                if body is None or len(body) == 0:
                    raise SchemeError("malformed letrec")
                bindings_list = to_proper_list(bindings_expr)
                if bindings_list is None:
                    raise SchemeError("malformed letrec")
                frame = {}
                for b in bindings_list:
                    v, _ = parse_binding(b)
                    frame[v.name] = UNINITIALIZED
                new_env = Env(frame, env)
                for b in bindings_list:
                    v, init = parse_binding(b)
                    val = eval_expr(init, new_env, output)
                    new_env.bindings[v.name] = val
                body_env = setup_body(body, new_env)
                for form in body[:-1]:
                    eval_expr(form, body_env, output)
                expr = body[-1]
                env = body_env
                continue

            # ── apply (tail-call optimization) ──
            elif name == 'apply':
                parts = to_proper_list(expr.cdr)
                if parts is None or len(parts) < 2:
                    raise SchemeError("malformed apply")
                f = eval_expr(parts[0], env, output)
                extra = [eval_expr(p, env, output) for p in parts[1:-1]]
                last = eval_expr(parts[-1], env, output)
                if not is_proper_list(last):
                    raise SchemeError("apply: last argument must be a proper list")
                args = extra + to_proper_list(last)
                if isinstance(f, Closure):
                    new_env = make_call_env(f, args)
                    body = f.body
                    body_env = setup_body(body, new_env)
                    for form in body[:-1]:
                        eval_expr(form, body_env, output)
                    expr = body[-1]
                    env = body_env
                    continue
                elif isinstance(f, Builtin):
                    return f.func(args, output)
                else:
                    raise SchemeError("apply: not a procedure")

        # ── Application (non-special form) ──
        # Check for dotted form
        if not is_proper_list(expr.cdr):
            raise SchemeError("dotted form used as application")

        op = eval_expr(head, env, output)
        operands = to_proper_list(expr.cdr)
        args = []
        for operand in operands:
            args.append(eval_expr(operand, env, output))

        if isinstance(op, Closure):
            new_env = make_call_env(op, args)
            body = op.body
            body_env = setup_body(body, new_env)
            for form in body[:-1]:
                eval_expr(form, body_env, output)
            expr = body[-1]
            env = body_env
            continue
        elif isinstance(op, Builtin):
            return op.func(args, output)
        else:
            raise SchemeError("not a procedure")


# ─── Builtins ─────────────────────────────────────────────────────────────────

def _check_int(x, fname):
    if not isinstance(x, int):
        raise SchemeError(f"{fname}: expected integer, got {type(x).__name__}")

def _builtin_add(args, output):
    for a in args:
        _check_int(a, '+')
    return sum(args)

def _builtin_mul(args, output):
    for a in args:
        _check_int(a, '*')
    r = 1
    for a in args:
        r *= a
    return r

def _builtin_sub(args, output):
    for a in args:
        _check_int(a, '-')
    if len(args) == 1:
        return -args[0]
    r = args[0]
    for a in args[1:]:
        r -= a
    return r

def _quotient(a, b):
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        q = -q
    return q

def _builtin_quotient(args, output):
    if len(args) != 2:
        raise SchemeError("quotient: expects 2 arguments")
    _check_int(args[0], 'quotient')
    _check_int(args[1], 'quotient')
    if args[1] == 0:
        raise SchemeError("quotient: division by zero")
    return _quotient(args[0], args[1])

def _builtin_remainder(args, output):
    if len(args) != 2:
        raise SchemeError("remainder: expects 2 arguments")
    _check_int(args[0], 'remainder')
    _check_int(args[1], 'remainder')
    if args[1] == 0:
        raise SchemeError("remainder: division by zero")
    return args[0] - _quotient(args[0], args[1]) * args[1]

def _builtin_modulo(args, output):
    if len(args) != 2:
        raise SchemeError("modulo: expects 2 arguments")
    _check_int(args[0], 'modulo')
    _check_int(args[1], 'modulo')
    if args[1] == 0:
        raise SchemeError("modulo: division by zero")
    return args[0] % args[1]

def _builtin_eq(args, output):
    if len(args) < 1:
        raise SchemeError("=: expects at least 1 argument")
    for a in args:
        _check_int(a, '=')
    for i in range(len(args) - 1):
        if args[i] != args[i+1]:
            return FALSE
    return TRUE

def _builtin_lt(args, output):
    if len(args) < 1:
        raise SchemeError("<: expects at least 1 argument")
    for a in args:
        _check_int(a, '<')
    for i in range(len(args) - 1):
        if not (args[i] < args[i+1]):
            return FALSE
    return TRUE

def _builtin_gt(args, output):
    if len(args) < 1:
        raise SchemeError(">: expects at least 1 argument")
    for a in args:
        _check_int(a, '>')
    for i in range(len(args) - 1):
        if not (args[i] > args[i+1]):
            return FALSE
    return TRUE

def _builtin_le(args, output):
    if len(args) < 1:
        raise SchemeError("<=: expects at least 1 argument")
    for a in args:
        _check_int(a, '<=')
    for i in range(len(args) - 1):
        if not (args[i] <= args[i+1]):
            return FALSE
    return TRUE

def _builtin_ge(args, output):
    if len(args) < 1:
        raise SchemeError(">=: expects at least 1 argument")
    for a in args:
        _check_int(a, '>=')
    for i in range(len(args) - 1):
        if not (args[i] >= args[i+1]):
            return FALSE
    return TRUE

def _builtin_number_to_string(args, output):
    if len(args) < 1 or len(args) > 2:
        raise SchemeError("number->string: expects 1 or 2 arguments")
    _check_int(args[0], 'number->string')
    radix = 10
    if len(args) == 2:
        _check_int(args[1], 'number->string')
        radix = args[1]
        if radix not in (2, 8, 10, 16):
            raise SchemeError(f"number->string: invalid radix {radix}")
    n = args[0]
    if n == 0:
        return "0"
    neg = n < 0
    n = abs(n)
    if radix == 10:
        s = str(n)
    elif radix == 2:
        s = bin(n)[2:]
    elif radix == 8:
        s = oct(n)[2:]
    else:
        s = hex(n)[2:]
    if neg:
        s = '-' + s
    return s

def _builtin_cons(args, output):
    if len(args) != 2:
        raise SchemeError("cons: expects 2 arguments")
    return Pair(args[0], args[1])

def _builtin_car(args, output):
    if len(args) != 1:
        raise SchemeError("car: expects 1 argument")
    if not isinstance(args[0], Pair):
        raise SchemeError("car: not a pair")
    return args[0].car

def _builtin_cdr(args, output):
    if len(args) != 1:
        raise SchemeError("cdr: expects 1 argument")
    if not isinstance(args[0], Pair):
        raise SchemeError("cdr: not a pair")
    return args[0].cdr

def _builtin_list(args, output):
    return to_pair_list(args)

def _builtin_null_p(args, output):
    if len(args) != 1:
        raise SchemeError("null?: expects 1 argument")
    return TRUE if isinstance(args[0], _EmptyList) else FALSE

def _builtin_pair_p(args, output):
    if len(args) != 1:
        raise SchemeError("pair?: expects 1 argument")
    return TRUE if isinstance(args[0], Pair) else FALSE

def _builtin_list_p(args, output):
    if len(args) != 1:
        raise SchemeError("list?: expects 1 argument")
    return TRUE if is_proper_list(args[0]) else FALSE

def _builtin_length(args, output):
    if len(args) != 1:
        raise SchemeError("length: expects 1 argument")
    n = 0
    cur = args[0]
    while isinstance(cur, Pair):
        n += 1
        cur = cur.cdr
    if not isinstance(cur, _EmptyList):
        raise SchemeError("length: not a proper list")
    return n

def _builtin_append(args, output):
    items = []
    for a in args[:-1]:
        cur = a
        while isinstance(cur, Pair):
            items.append(cur.car)
            cur = cur.cdr
        if not isinstance(cur, _EmptyList):
            raise SchemeError("append: not a proper list")
    last = args[-1] if args else EMPTY_LIST
    result = last
    for item in reversed(items):
        result = Pair(item, result)
    return result

def _builtin_reverse(args, output):
    if len(args) != 1:
        raise SchemeError("reverse: expects 1 argument")
    items = []
    cur = args[0]
    while isinstance(cur, Pair):
        items.append(cur.car)
        cur = cur.cdr
    if not isinstance(cur, _EmptyList):
        raise SchemeError("reverse: not a proper list")
    result = EMPTY_LIST
    for item in items:
        result = Pair(item, result)
    return result

def _builtin_apply(args, output):
    if len(args) < 2:
        raise SchemeError("apply: expects at least 2 arguments")
    f = args[0]
    extra = args[1:-1]
    last = args[-1]
    if not is_proper_list(last):
        raise SchemeError("apply: last argument must be a proper list")
    call_args = extra + to_proper_list(last)
    if isinstance(f, Closure):
        new_env = make_call_env(f, call_args)
        body = f.body
        body_env = setup_body(body, new_env)
        for form in body[:-1]:
            eval_expr(form, body_env, output)
        return eval_expr(body[-1], body_env, output)
    elif isinstance(f, Builtin):
        return f.func(call_args, output)
    else:
        raise SchemeError("apply: not a procedure")

def _scheme_equal(a, b):
    while True:
        if a is b:
            return True
        if isinstance(a, int) and isinstance(b, int):
            return a == b
        if isinstance(a, str) and isinstance(b, str):
            return a == b
        if isinstance(a, Pair) and isinstance(b, Pair):
            if not _scheme_equal(a.car, b.car):
                return False
            a = a.cdr
            b = b.cdr
            continue
        return False

def _builtin_eq_p(args, output):
    if len(args) != 2:
        raise SchemeError("eq?: expects 2 arguments")
    a, b = args
    if a is b:
        return TRUE
    if isinstance(a, int) and isinstance(b, int):
        return TRUE if a == b else FALSE
    return FALSE

def _builtin_equal_p(args, output):
    if len(args) != 2:
        raise SchemeError("equal?: expects 2 arguments")
    return TRUE if _scheme_equal(args[0], args[1]) else FALSE

def _builtin_not(args, output):
    if len(args) != 1:
        raise SchemeError("not: expects 1 argument")
    return TRUE if args[0] is FALSE else FALSE

def _builtin_number_p(args, output):
    if len(args) != 1:
        raise SchemeError("number?: expects 1 argument")
    return TRUE if isinstance(args[0], int) else FALSE

def _builtin_symbol_p(args, output):
    if len(args) != 1:
        raise SchemeError("symbol?: expects 1 argument")
    return TRUE if isinstance(args[0], Symbol) else FALSE

def _builtin_string_p(args, output):
    if len(args) != 1:
        raise SchemeError("string?: expects 1 argument")
    return TRUE if isinstance(args[0], str) else FALSE

def _builtin_procedure_p(args, output):
    if len(args) != 1:
        raise SchemeError("procedure?: expects 1 argument")
    return TRUE if isinstance(args[0], (Closure, Builtin)) else FALSE

def _builtin_string_append(args, output):
    for a in args:
        if not isinstance(a, str):
            raise SchemeError("string-append: expected string")
    return ''.join(args)

def _builtin_display(args, output):
    if len(args) != 1:
        raise SchemeError("display: expects 1 argument")
    display_value(args[0], output)
    return UNSPECIFIED

def _builtin_newline(args, output):
    if len(args) != 0:
        raise SchemeError("newline: expects 0 arguments")
    output.append('\n')
    return UNSPECIFIED

def _builtin_error(args, output):
    if len(args) < 1:
        raise SchemeError("error: expects at least 1 argument")
    msg = args[0]
    if not isinstance(msg, str):
        raise SchemeError(str(msg))
    parts = [msg]
    for irritant in args[1:]:
        parts.append(' ')
        buf = []
        write_value(irritant, buf)
        parts.append(''.join(buf))
    raise SchemeError(''.join(parts))


# ─── Global Environment ───────────────────────────────────────────────────────

def make_global_env(output):
    env = Env()
    builtins = [
        ('+', _builtin_add),
        ('*', _builtin_mul),
        ('-', _builtin_sub),
        ('quotient', _builtin_quotient),
        ('remainder', _builtin_remainder),
        ('modulo', _builtin_modulo),
        ('=', _builtin_eq),
        ('<', _builtin_lt),
        ('>', _builtin_gt),
        ('<=', _builtin_le),
        ('>=', _builtin_ge),
        ('number->string', _builtin_number_to_string),
        ('cons', _builtin_cons),
        ('car', _builtin_car),
        ('cdr', _builtin_cdr),
        ('list', _builtin_list),
        ('null?', _builtin_null_p),
        ('pair?', _builtin_pair_p),
        ('list?', _builtin_list_p),
        ('length', _builtin_length),
        ('append', _builtin_append),
        ('reverse', _builtin_reverse),
        ('apply', _builtin_apply),
        ('eq?', _builtin_eq_p),
        ('equal?', _builtin_equal_p),
        ('not', _builtin_not),
        ('number?', _builtin_number_p),
        ('symbol?', _builtin_symbol_p),
        ('string?', _builtin_string_p),
        ('procedure?', _builtin_procedure_p),
        ('string-append', _builtin_string_append),
        ('display', _builtin_display),
        ('newline', _builtin_newline),
        ('error', _builtin_error),
    ]
    for name, func in builtins:
        env.define(name, Builtin(func, name))
    return env


# ─── Public API ───────────────────────────────────────────────────────────────

def run(source):
    result = [None]
    exc = [None]

    def _run():
        output = []
        try:
            forms = read_all(source)
            env = make_global_env(output)
            for form in forms:
                eval_expr(form, env, output)
            result[0] = ''.join(output)
        except SchemeError as e:
            e.output = ''.join(output)
            exc[0] = e
        except RecursionError:
            err = SchemeError("stack overflow")
            err.output = ''.join(output)
            exc[0] = err
        except Exception as e:
            err = SchemeError(str(e))
            err.output = ''.join(output)
            exc[0] = err

    old_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(200000)
    try:
        threading.stack_size(64 * 1024 * 1024)
    except Exception:
        pass
    t = threading.Thread(target=_run)
    t.start()
    t.join()
    sys.setrecursionlimit(old_limit)

    if exc[0] is not None:
        raise exc[0]
    return result[0]
