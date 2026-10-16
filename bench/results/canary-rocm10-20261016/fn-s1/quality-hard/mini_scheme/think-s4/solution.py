import sys
import threading

if hasattr(sys, 'set_int_max_str_digits'):
    sys.set_int_max_str_digits(0)

try:
    threading.stack_size(256 * 1024 * 1024)
except (ValueError, RuntimeError):
    try:
        threading.stack_size(64 * 1024 * 1024)
    except Exception:
        pass


class SchemeError(Exception):
    def __init__(self, message, output=''):
        super().__init__(message)
        self.output = output


class Symbol:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name
    def __repr__(self):
        return f'Symbol({self.name})'
    def __eq__(self, other):
        return isinstance(other, Symbol) and self.name == other.name
    def __hash__(self):
        return hash(('Symbol', self.name))


class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr


class _Nil:
    def __repr__(self):
        return '()'
    def __bool__(self):
        return True

NIL = _Nil()


class _Unspecified:
    def __repr__(self):
        return '<unspecified>'
    def __bool__(self):
        return True

UNSPECIFIED = _Unspecified()
UNBOUND = object()


class Closure:
    __slots__ = ('formals', 'body', 'env')
    def __init__(self, formals, body, env):
        self.formals = formals
        self.body = body
        self.env = env


class Builtin:
    __slots__ = ('name', 'func', 'min_args', 'max_args')
    def __init__(self, name, func, min_args=None, max_args=None):
        self.name = name
        self.func = func
        self.min_args = min_args
        self.max_args = max_args


class Frame:
    __slots__ = ('bindings',)
    def __init__(self, bindings=None):
        self.bindings = bindings if bindings is not None else {}


class Env:
    __slots__ = ('frame', 'parent')
    def __init__(self, frame, parent=None):
        self.frame = frame
        self.parent = parent

    def lookup(self, sym):
        env = self
        while env is not None:
            if sym in env.frame.bindings:
                val = env.frame.bindings[sym]
                if val is UNBOUND:
                    raise SchemeError(f"uninitialized variable: {sym.name}")
                return val
            env = env.parent
        raise SchemeError(f"unbound variable: {sym.name}")

    def set(self, sym, val):
        env = self
        while env is not None:
            if sym in env.frame.bindings:
                env.frame.bindings[sym] = val
                return
            env = env.parent
        raise SchemeError(f"unbound variable: {sym.name}")

    def define(self, sym, val):
        self.frame.bindings[sym] = val


# --- Reader ---

class Reader:
    def __init__(self, source):
        self.source = source
        self.pos = 0

    def skip_ws(self):
        while self.pos < len(self.source):
            ch = self.source[self.pos]
            if ch in ' \t\n\r':
                self.pos += 1
            elif ch == ';':
                while self.pos < len(self.source) and self.source[self.pos] != '\n':
                    self.pos += 1
            else:
                break

    def read_all(self):
        forms = []
        while True:
            self.skip_ws()
            if self.pos >= len(self.source):
                break
            forms.append(self.read_datum())
        return forms

    def read_datum(self):
        self.skip_ws()
        if self.pos >= len(self.source):
            raise SchemeError("unexpected end of input")
        ch = self.source[self.pos]
        if ch == '(':
            return self.read_list()
        elif ch == ')':
            raise SchemeError("unexpected )")
        elif ch == "'":
            self.pos += 1
            datum = self.read_datum()
            return Pair(Symbol('quote'), Pair(datum, NIL))
        elif ch == '"':
            return self.read_string()
        elif ch == '#':
            return self.read_hash()
        else:
            return self.read_atom()

    def read_list(self):
        self.pos += 1
        items = []
        dotted = False
        dot_value = None
        while True:
            self.skip_ws()
            if self.pos >= len(self.source):
                raise SchemeError("unbalanced (")
            if self.source[self.pos] == ')':
                self.pos += 1
                break
            if not dotted and self.source[self.pos] == '.':
                next_pos = self.pos + 1
                if next_pos >= len(self.source) or self.source[next_pos] in ' \t\n\r()\";\x27':
                    if len(items) == 0:
                        raise SchemeError("dot with no preceding element")
                    dotted = True
                    self.pos = next_pos
                    dot_value = self.read_datum()
                    self.skip_ws()
                    if self.pos >= len(self.source) or self.source[self.pos] != ')':
                        raise SchemeError("expected ) after dotted pair")
                    self.pos += 1
                    break
            items.append(self.read_datum())
        if dotted:
            result = dot_value
            for item in reversed(items):
                result = Pair(item, result)
            return result
        else:
            result = NIL
            for item in reversed(items):
                result = Pair(item, result)
            return result

    def read_string(self):
        self.pos += 1
        chars = []
        while self.pos < len(self.source):
            ch = self.source[self.pos]
            if ch == '"':
                self.pos += 1
                return ''.join(chars)
            elif ch == '\\':
                self.pos += 1
                if self.pos >= len(self.source):
                    raise SchemeError("unterminated string")
                esc = self.source[self.pos]
                if esc == '"':
                    chars.append('"')
                elif esc == '\\':
                    chars.append('\\')
                elif esc == 'n':
                    chars.append('\n')
                else:
                    raise SchemeError(f"invalid escape sequence: \\{esc}")
                self.pos += 1
            else:
                chars.append(ch)
                self.pos += 1
        raise SchemeError("unterminated string")

    def read_hash(self):
        start = self.pos
        while self.pos < len(self.source):
            ch = self.source[self.pos]
            if ch in ' \t\n\r()\";\x27':
                break
            self.pos += 1
        token = self.source[start:self.pos]
        if token == '#t':
            return True
        if token == '#f':
            return False
        raise SchemeError(f"invalid token: {token}")

    def read_atom(self):
        start = self.pos
        while self.pos < len(self.source):
            ch = self.source[self.pos]
            if ch in ' \t\n\r()\";\x27':
                break
            self.pos += 1
        token = self.source[start:self.pos]
        if not token:
            raise SchemeError("unexpected character")
        if self._is_int(token):
            return int(token)
        if token.startswith('#'):
            raise SchemeError(f"invalid token: {token}")
        return Symbol(token)

    @staticmethod
    def _is_int(token):
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


# --- Utilities ---

def is_int(x):
    return type(x) is int

def is_bool(x):
    return type(x) is bool

def is_proper_list(x):
    while isinstance(x, Pair):
        x = x.cdr
    return x is NIL

def list_to_proper(lst):
    result = []
    current = lst
    while isinstance(current, Pair):
        result.append(current.car)
        current = current.cdr
    if current is not NIL:
        raise SchemeError("malformed: expected proper list")
    return result

def args_to_list(args):
    result = NIL
    for a in reversed(args):
        result = Pair(a, result)
    return result


# --- Display / Write ---

def display_value(val):
    if is_bool(val):
        return '#t' if val else '#f'
    if is_int(val):
        return str(val)
    if isinstance(val, str):
        return val
    if isinstance(val, Symbol):
        return val.name
    if val is NIL:
        return '()'
    if isinstance(val, Pair):
        return display_pair(val)
    if isinstance(val, (Closure, Builtin)):
        return '#<procedure>'
    if val is UNSPECIFIED:
        return ''
    return ''

def display_pair(val):
    parts = []
    current = val
    while isinstance(current, Pair):
        parts.append(display_value(current.car))
        current = current.cdr
    if current is NIL:
        return '(' + ' '.join(parts) + ')'
    else:
        return '(' + ' '.join(parts) + ' . ' + display_value(current) + ')'

def write_value(val):
    if isinstance(val, str):
        escaped = val.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        return '"' + escaped + '"'
    if isinstance(val, Pair):
        return write_pair(val)
    return display_value(val)

def write_pair(val):
    parts = []
    current = val
    while isinstance(current, Pair):
        parts.append(write_value(current.car))
        current = current.cdr
    if current is NIL:
        return '(' + ' '.join(parts) + ')'
    else:
        return '(' + ' '.join(parts) + ' . ' + write_value(current) + ')'


# --- Evaluator ---

DONE = 0
TAIL = 1
_current_output = []

def _write(s):
    _current_output.append(s)


def eval_expr(expr, env):
    if is_int(expr) or is_bool(expr) or isinstance(expr, str):
        return (DONE, expr)
    if expr is NIL:
        raise SchemeError("cannot evaluate ()")
    if isinstance(expr, Symbol):
        return (DONE, env.lookup(expr))
    if isinstance(expr, Pair):
        head = expr.car
        if isinstance(head, Symbol):
            name = head.name
            if name == 'quote': return _eval_quote(expr, env)
            if name == 'if': return _eval_if(expr, env)
            if name == 'define': return _eval_define(expr, env)
            if name == 'set!': return _eval_set(expr, env)
            if name == 'begin': return _eval_begin(expr, env)
            if name == 'lambda': return _eval_lambda(expr, env)
            if name == 'cond': return _eval_cond(expr, env)
            if name == 'and': return _eval_and(expr, env)
            if name == 'or': return _eval_or(expr, env)
            if name == 'let': return _eval_let(expr, env)
            if name == 'let*': return _eval_letstar(expr, env)
            if name == 'letrec': return _eval_letrec(expr, env)
            if name == 'apply': return _eval_apply(expr, env)
        return _eval_application(expr, env)
    raise SchemeError("invalid expression")


def eval_val(expr, env):
    result = eval_expr(expr, env)
    while result[0] == TAIL:
        result = apply_proc(result[1], result[2])
    return result[1]


def apply_proc(proc, args):
    while True:
        if isinstance(proc, Closure):
            frame = _make_param_frame(proc.formals, args)
            for name in _scan_internal_defines(proc.body):
                if name not in frame:
                    frame[name] = UNBOUND
            new_env = Env(Frame(frame), proc.env)
            result = _eval_body(proc.body, new_env)
            if result[0] == TAIL:
                proc = result[1]
                args = result[2]
                continue
            return result
        elif isinstance(proc, Builtin):
            return (DONE, proc.func(*args))
        else:
            raise SchemeError("not a procedure")


def _make_param_frame(formals, args):
    frame = {}
    if isinstance(formals, Symbol):
        frame[formals] = args_to_list(args)
    elif isinstance(formals, Pair):
        fixed = []
        current = formals
        while isinstance(current, Pair):
            fixed.append(current.car)
            current = current.cdr
        if current is NIL:
            for sym, val in zip(fixed, args):
                frame[sym] = val
        elif isinstance(current, Symbol):
            for sym, val in zip(fixed, args[:len(fixed)]):
                frame[sym] = val
            frame[current] = args_to_list(args[len(fixed):])
        else:
            raise SchemeError("malformed formals")
    elif formals is NIL:
        pass
    else:
        raise SchemeError("malformed formals")
    return frame


def _check_arity(proc, nargs):
    if isinstance(proc, Builtin):
        if proc.min_args is not None and nargs < proc.min_args:
            raise SchemeError(f"{proc.name}: too few arguments")
        if proc.max_args is not None and nargs > proc.max_args:
            raise SchemeError(f"{proc.name}: too many arguments")
    elif isinstance(proc, Closure):
        formals = proc.formals
        if isinstance(formals, Symbol):
            pass
        elif isinstance(formals, Pair):
            fixed_count = 0
            current = formals
            while isinstance(current, Pair):
                fixed_count += 1
                current = current.cdr
            if current is NIL:
                if nargs != fixed_count:
                    raise SchemeError("wrong number of arguments")
            elif isinstance(current, Symbol):
                if nargs < fixed_count:
                    raise SchemeError("too few arguments")
            else:
                raise SchemeError("malformed formals")
        elif formals is NIL:
            if nargs != 0:
                raise SchemeError("wrong number of arguments")
        else:
            raise SchemeError("malformed formals")


def _eval_body(body, env):
    for i in range(len(body) - 1):
        eval_val(body[i], env)
    return eval_expr(body[-1], env)


def _scan_internal_defines(body):
    names = []
    for form in body:
        if isinstance(form, Pair) and isinstance(form.car, Symbol) and form.car.name == 'define':
            cdr = form.cdr
            if cdr is not NIL:
                target = cdr.car
                if isinstance(target, Symbol):
                    names.append(target)
                elif isinstance(target, Pair) and isinstance(target.car, Symbol):
                    names.append(target.car)
    return names


def _make_body_env(body, env, extra_bindings=None):
    names = _scan_internal_defines(body)
    bindings = {}
    if extra_bindings:
        for k, v in extra_bindings:
            bindings[k] = v
    for name in names:
        if name not in bindings:
            bindings[name] = UNBOUND
    return Env(Frame(bindings), env)


# --- Special Forms ---

def _eval_quote(expr, env):
    cdr = expr.cdr
    if cdr is NIL:
        raise SchemeError("malformed quote")
    datum = cdr.car
    if cdr.cdr is not NIL:
        raise SchemeError("malformed quote")
    return (DONE, datum)


def _eval_if(expr, env):
    cdr = expr.cdr
    if cdr is NIL:
        raise SchemeError("malformed if")
    test_expr = cdr.car
    then_cdr = cdr.cdr
    if then_cdr is NIL:
        raise SchemeError("malformed if")
    then_expr = then_cdr.car
    else_cdr = then_cdr.cdr
    test_val = eval_val(test_expr, env)
    if test_val is not False:
        return eval_expr(then_expr, env)
    else:
        if else_cdr is NIL:
            return (DONE, UNSPECIFIED)
        else_expr = else_cdr.car
        if else_cdr.cdr is not NIL:
            raise SchemeError("malformed if: too many forms")
        return eval_expr(else_expr, env)


def _eval_define(expr, env):
    cdr = expr.cdr
    if cdr is NIL:
        raise SchemeError("malformed define")
    target = cdr.car
    if isinstance(target, Symbol):
        rest = cdr.cdr
        if rest is NIL:
            raise SchemeError("malformed define")
        val = eval_val(rest.car, env)
        if rest.cdr is not NIL:
            raise SchemeError("malformed define")
        env.define(target, val)
        return (DONE, UNSPECIFIED)
    elif isinstance(target, Pair):
        name = target.car
        if not isinstance(name, Symbol):
            raise SchemeError("malformed define")
        formals = target.cdr
        body_cdr = cdr.cdr
        if body_cdr is NIL:
            raise SchemeError("malformed define: empty body")
        body = list_to_proper(body_cdr)
        closure = Closure(formals, body, env)
        env.define(name, closure)
        return (DONE, UNSPECIFIED)
    else:
        raise SchemeError("malformed define")


def _eval_set(expr, env):
    cdr = expr.cdr
    if cdr is NIL:
        raise SchemeError("malformed set!")
    name = cdr.car
    if not isinstance(name, Symbol):
        raise SchemeError("malformed set!")
    rest = cdr.cdr
    if rest is NIL:
        raise SchemeError("malformed set!")
    val = eval_val(rest.car, env)
    if rest.cdr is not NIL:
        raise SchemeError("malformed set!")
    env.set(name, val)
    return (DONE, UNSPECIFIED)


def _eval_begin(expr, env):
    exprs = list_to_proper(expr.cdr)
    if len(exprs) == 0:
        raise SchemeError("malformed begin")
    for i in range(len(exprs) - 1):
        eval_val(exprs[i], env)
    return eval_expr(exprs[-1], env)


def _eval_lambda(expr, env):
    cdr = expr.cdr
    if cdr is NIL:
        raise SchemeError("malformed lambda")
    formals = cdr.car
    body_cdr = cdr.cdr
    if body_cdr is NIL:
        raise SchemeError("malformed lambda: empty body")
    body = list_to_proper(body_cdr)
    return (DONE, Closure(formals, body, env))


def _eval_cond(expr, env):
    clauses = list_to_proper(expr.cdr)
    for i, clause in enumerate(clauses):
        if not isinstance(clause, Pair):
            raise SchemeError("malformed cond clause")
        test = clause.car
        body_cdr = clause.cdr
        if isinstance(test, Symbol) and test.name == 'else':
            if i != len(clauses) - 1:
                raise SchemeError("else not last in cond")
            body = list_to_proper(body_cdr)
            if len(body) == 0:
                raise SchemeError("malformed cond: else with no body")
            return _eval_body(body, env)
        else:
            test_val = eval_val(test, env)
            if test_val is not False:
                body = list_to_proper(body_cdr)
                if len(body) == 0:
                    return (DONE, test_val)
                return _eval_body(body, env)
    return (DONE, UNSPECIFIED)


def _eval_and(expr, env):
    exprs = list_to_proper(expr.cdr)
    if len(exprs) == 0:
        return (DONE, True)
    for i in range(len(exprs) - 1):
        val = eval_val(exprs[i], env)
        if val is False:
            return (DONE, False)
    return eval_expr(exprs[-1], env)


def _eval_or(expr, env):
    exprs = list_to_proper(expr.cdr)
    if len(exprs) == 0:
        return (DONE, False)
    for i in range(len(exprs) - 1):
        val = eval_val(exprs[i], env)
        if val is not False:
            return (DONE, val)
    return eval_expr(exprs[-1], env)


def _parse_bindings(bindings_form):
    result = []
    current = bindings_form
    while isinstance(current, Pair):
        b = current.car
        if not isinstance(b, Pair):
            raise SchemeError("malformed binding")
        v = b.car
        if not isinstance(v, Symbol):
            raise SchemeError("malformed binding: not a symbol")
        init_cdr = b.cdr
        if init_cdr is NIL:
            raise SchemeError("malformed binding: no init")
        init = init_cdr.car
        if init_cdr.cdr is not NIL:
            raise SchemeError("malformed binding: too many inits")
        result.append((v, init))
        current = current.cdr
    if current is not NIL:
        raise SchemeError("malformed bindings")
    return result


def _eval_let(expr, env):
    cdr = expr.cdr
    if cdr is NIL:
        raise SchemeError("malformed let")
    first = cdr.car
    if isinstance(first, Symbol):
        return _eval_named_let(expr, env)
    bindings_form = first
    body_cdr = cdr.cdr
    if body_cdr is NIL:
        raise SchemeError("malformed let: empty body")
    bind_list = _parse_bindings(bindings_form)
    body = list_to_proper(body_cdr)
    vals = []
    for v, init in bind_list:
        vals.append(eval_val(init, env))
    extra = list(zip([v for v, _ in bind_list], vals))
    new_env = _make_body_env(body, env, extra)
    return _eval_body(body, new_env)


def _eval_letstar(expr, env):
    cdr = expr.cdr
    if cdr is NIL:
        raise SchemeError("malformed let*")
    bindings_form = cdr.car
    body_cdr = cdr.cdr
    if body_cdr is NIL:
        raise SchemeError("malformed let*: empty body")
    bind_list = _parse_bindings(bindings_form)
    body = list_to_proper(body_cdr)
    new_env = _make_body_env(body, env, [])
    for v, init in bind_list:
        val = eval_val(init, new_env)
        new_env.define(v, val)
    return _eval_body(body, new_env)


def _eval_letrec(expr, env):
    cdr = expr.cdr
    if cdr is NIL:
        raise SchemeError("malformed letrec")
    bindings_form = cdr.car
    body_cdr = cdr.cdr
    if body_cdr is NIL:
        raise SchemeError("malformed letrec: empty body")
    bind_list = _parse_bindings(bindings_form)
    body = list_to_proper(body_cdr)
    extra = [(v, UNBOUND) for v, _ in bind_list]
    new_env = _make_body_env(body, env, extra)
    for v, init in bind_list:
        val = eval_val(init, new_env)
        new_env.define(v, val)
    return _eval_body(body, new_env)


def _eval_named_let(expr, env):
    cdr = expr.cdr
    name = cdr.car
    bindings_form = cdr.cdr.car
    body_cdr = cdr.cdr.cdr
    if body_cdr is NIL:
        raise SchemeError("malformed named let: empty body")
    bind_list = _parse_bindings(bindings_form)
    body = list_to_proper(body_cdr)
    vals = []
    for v, init in bind_list:
        vals.append(eval_val(init, env))
    formals = args_to_list([v for v, _ in bind_list])
    frame = Frame({name: UNBOUND})
    letrec_env = Env(frame, env)
    closure = Closure(formals, body, letrec_env)
    frame.bindings[name] = closure
    return (TAIL, closure, vals)


def _eval_application(expr, env):
    proc = eval_val(expr.car, env)
    args = []
    current = expr.cdr
    while isinstance(current, Pair):
        args.append(eval_val(current.car, env))
        current = current.cdr
    if current is not NIL:
        raise SchemeError("dotted form in application")
    if not isinstance(proc, (Closure, Builtin)):
        raise SchemeError(f"not a procedure: {display_value(proc)}")
    _check_arity(proc, len(args))
    return (TAIL, proc, args)


def _eval_apply(expr, env):
    cdr = expr.cdr
    if cdr is NIL:
        raise SchemeError("malformed apply")
    args_list = list_to_proper(cdr)
    if len(args_list) < 2:
        raise SchemeError("apply: needs at least 2 arguments")
    f = eval_val(args_list[0], env)
    fixed_args = [eval_val(a, env) for a in args_list[1:-1]]
    lst = eval_val(args_list[-1], env)
    if not is_proper_list(lst):
        raise SchemeError("apply: last argument is not a proper list")
    all_args = fixed_args[:]
    current = lst
    while isinstance(current, Pair):
        all_args.append(current.car)
        current = current.cdr
    if not isinstance(f, (Closure, Builtin)):
        raise SchemeError("apply: not a procedure")
    _check_arity(f, len(all_args))
    return (TAIL, f, all_args)


# --- Builtins ---

def _check_num(x, name):
    if is_bool(x) or not isinstance(x, int):
        raise SchemeError(f"{name}: not a number")

def _bi_add(*args):
    for a in args:
        _check_num(a, '+')
    return sum(args) if args else 0

def _bi_mul(*args):
    for a in args:
        _check_num(a, '*')
    r = 1
    for a in args:
        r *= a
    return r

def _bi_sub(*args):
    for a in args:
        _check_num(a, '-')
    if len(args) == 1:
        return -args[0]
    r = args[0]
    for a in args[1:]:
        r -= a
    return r

def _bi_quotient(a, b):
    _check_num(a, 'quotient')
    _check_num(b, 'quotient')
    if b == 0:
        raise SchemeError("quotient: division by zero")
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        q = -q
    return q

def _bi_remainder(a, b):
    _check_num(a, 'remainder')
    _check_num(b, 'remainder')
    if b == 0:
        raise SchemeError("remainder: division by zero")
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        q = -q
    return a - q * b

def _bi_modulo(a, b):
    _check_num(a, 'modulo')
    _check_num(b, 'modulo')
    if b == 0:
        raise SchemeError("modulo: division by zero")
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        q = -q - 1
    return a - q * b

def _bi_eq(*args):
    for a in args:
        _check_num(a, '=')
    for i in range(len(args) - 1):
        if args[i] != args[i + 1]:
            return False
    return True

def _bi_lt(*args):
    for a in args:
        _check_num(a, '<')
    for i in range(len(args) - 1):
        if not (args[i] < args[i + 1]):
            return False
    return True

def _bi_gt(*args):
    for a in args:
        _check_num(a, '>')
    for i in range(len(args) - 1):
        if not (args[i] > args[i + 1]):
            return False
    return True

def _bi_le(*args):
    for a in args:
        _check_num(a, '<=')
    for i in range(len(args) - 1):
        if not (args[i] <= args[i + 1]):
            return False
    return True

def _bi_ge(*args):
    for a in args:
        _check_num(a, '>=')
    for i in range(len(args) - 1):
        if not (args[i] >= args[i + 1]):
            return False
    return True

def _bi_num2str(n, radix=10):
    _check_num(n, 'number->string')
    if radix not in (2, 8, 10, 16):
        raise SchemeError("number->string: invalid radix")
    negative = n < 0
    n = abs(n)
    if n == 0:
        return '0'
    digits = '0123456789abcdef'
    result = ''
    while n > 0:
        result = digits[n % radix] + result
        n //= radix
    if negative:
        result = '-' + result
    return result

def _bi_cons(a, b):
    return Pair(a, b)

def _bi_car(p):
    if not isinstance(p, Pair):
        raise SchemeError("car: not a pair")
    return p.car

def _bi_cdr(p):
    if not isinstance(p, Pair):
        raise SchemeError("cdr: not a pair")
    return p.cdr

def _bi_list(*args):
    return args_to_list(args)

def _bi_null(x):
    return x is NIL

def _bi_pair(x):
    return isinstance(x, Pair)

def _bi_listq(x):
    return is_proper_list(x)

def _bi_length(l):
    n = 0
    current = l
    while isinstance(current, Pair):
        n += 1
        current = current.cdr
    if current is not NIL:
        raise SchemeError("length: not a proper list")
    return n

def _bi_append(*args):
    if len(args) == 0:
        return NIL
    for i in range(len(args) - 1):
        if not is_proper_list(args[i]):
            raise SchemeError("append: not a proper list")
    last = args[-1]
    result = last
    for i in range(len(args) - 2, -1, -1):
        lst = args[i]
        if lst is NIL:
            continue
        elements = []
        current = lst
        while isinstance(current, Pair):
            elements.append(current.car)
            current = current.cdr
        for elem in reversed(elements):
            result = Pair(elem, result)
    return result

def _bi_reverse(l):
    if not is_proper_list(l):
        raise SchemeError("reverse: not a proper list")
    result = NIL
    current = l
    while isinstance(current, Pair):
        result = Pair(current.car, result)
        current = current.cdr
    return result

def _bi_apply(*args):
    if len(args) < 2:
        raise SchemeError("apply: needs at least 2 arguments")
    f = args[0]
    fixed_args = list(args[1:-1])
    lst = args[-1]
    if not is_proper_list(lst):
        raise SchemeError("apply: last argument is not a proper list")
    all_args = fixed_args[:]
    current = lst
    while isinstance(current, Pair):
        all_args.append(current.car)
        current = current.cdr
    if not isinstance(f, (Closure, Builtin)):
        raise SchemeError("apply: not a procedure")
    _check_arity(f, len(all_args))
    result = apply_proc(f, all_args)
    while result[0] == TAIL:
        result = apply_proc(result[1], result[2])
    return result[1]

def _bi_eqq(a, b):
    if is_bool(a) and is_bool(b):
        return a == b
    if is_bool(a) or is_bool(b):
        return False
    if is_int(a) and is_int(b):
        return a == b
    if is_int(a) or is_int(b):
        return False
    if a is NIL and b is NIL:
        return True
    if isinstance(a, Symbol) and isinstance(b, Symbol):
        return a.name == b.name
    return a is b

def _bi_equal(a, b):
    while True:
        if isinstance(a, Pair) and isinstance(b, Pair):
            if not _bi_equal(a.car, b.car):
                return False
            a = a.cdr
            b = b.cdr
        elif isinstance(a, str) and isinstance(b, str):
            return a == b
        else:
            return _bi_eqq(a, b)

def _bi_not(x):
    return x is False

def _bi_number(x):
    return is_int(x)

def _bi_symbol(x):
    return isinstance(x, Symbol)

def _bi_string(x):
    return isinstance(x, str)

def _bi_procedure(x):
    return isinstance(x, (Closure, Builtin))

def _bi_str_append(*args):
    for a in args:
        if not isinstance(a, str):
            raise SchemeError("string-append: not a string")
    return ''.join(args)

def _bi_display(x):
    _write(display_value(x))
    return UNSPECIFIED

def _bi_newline():
    _write('\n')
    return UNSPECIFIED

def _bi_error(*args):
    if len(args) < 1:
        raise SchemeError("error: needs at least 1 argument")
    msg = args[0]
    if not isinstance(msg, str):
        raise SchemeError("error: first argument must be a string")
    parts = [msg]
    for irritant in args[1:]:
        parts.append(' ')
        parts.append(write_value(irritant))
    raise SchemeError(''.join(parts))


def _make_globals():
    g = {}
    g[Symbol('+')] = Builtin('+', _bi_add, 0, None)
    g[Symbol('*')] = Builtin('*', _bi_mul, 0, None)
    g[Symbol('-')] = Builtin('-', _bi_sub, 1, None)
    g[Symbol('quotient')] = Builtin('quotient', _bi_quotient, 2, 2)
    g[Symbol('remainder')] = Builtin('remainder', _bi_remainder, 2, 2)
    g[Symbol('modulo')] = Builtin('modulo', _bi_modulo, 2, 2)
    g[Symbol('=')] = Builtin('=', _bi_eq, 1, None)
    g[Symbol('<')] = Builtin('<', _bi_lt, 1, None)
    g[Symbol('>')] = Builtin('>', _bi_gt, 1, None)
    g[Symbol('<=')] = Builtin('<=', _bi_le, 1, None)
    g[Symbol('>=')] = Builtin('>=', _bi_ge, 1, None)
    g[Symbol('number->string')] = Builtin('number->string', _bi_num2str, 1, 2)
    g[Symbol('cons')] = Builtin('cons', _bi_cons, 2, 2)
    g[Symbol('car')] = Builtin('car', _bi_car, 1, 1)
    g[Symbol('cdr')] = Builtin('cdr', _bi_cdr, 1, 1)
    g[Symbol('list')] = Builtin('list', _bi_list, 0, None)
    g[Symbol('null?')] = Builtin('null?', _bi_null, 1, 1)
    g[Symbol('pair?')] = Builtin('pair?', _bi_pair, 1, 1)
    g[Symbol('list?')] = Builtin('list?', _bi_listq, 1, 1)
    g[Symbol('length')] = Builtin('length', _bi_length, 1, 1)
    g[Symbol('append')] = Builtin('append', _bi_append, 0, None)
    g[Symbol('reverse')] = Builtin('reverse', _bi_reverse, 1, 1)
    g[Symbol('apply')] = Builtin('apply', _bi_apply, 2, None)
    g[Symbol('eq?')] = Builtin('eq?', _bi_eqq, 2, 2)
    g[Symbol('equal?')] = Builtin('equal?', _bi_equal, 2, 2)
    g[Symbol('not')] = Builtin('not', _bi_not, 1, 1)
    g[Symbol('number?')] = Builtin('number?', _bi_number, 1, 1)
    g[Symbol('symbol?')] = Builtin('symbol?', _bi_symbol, 1, 1)
    g[Symbol('string?')] = Builtin('string?', _bi_string, 1, 1)
    g[Symbol('procedure?')] = Builtin('procedure?', _bi_procedure, 1, 1)
    g[Symbol('string-append')] = Builtin('string-append', _bi_str_append, 0, None)
    g[Symbol('display')] = Builtin('display', _bi_display, 1, 1)
    g[Symbol('newline')] = Builtin('newline', _bi_newline, 0, 0)
    g[Symbol('error')] = Builtin('error', _bi_error, 1, None)
    return g


# --- Main entry point ---

def _run_inner(source):
    global _current_output
    _current_output = []
    reader = Reader(source)
    forms = reader.read_all()
    global_bindings = _make_globals()
    global_env = Env(Frame(global_bindings))
    for form in forms:
        result = eval_expr(form, global_env)
        while result[0] == TAIL:
            result = apply_proc(result[1], result[2])
    return ''.join(_current_output)


def run(source):
    sys.setrecursionlimit(200000)
    result_box = []
    error_box = []

    def target():
        global _current_output
        _current_output = []
        try:
            val = _run_inner(source)
            result_box.append(val)
        except SchemeError as e:
            e.output = ''.join(_current_output)
            error_box.append(e)
        except RecursionError:
            err = SchemeError("stack overflow")
            err.output = ''.join(_current_output)
            error_box.append(err)
        except Exception as e:
            err = SchemeError(str(e))
            err.output = ''.join(_current_output)
            error_box.append(err)

    t = threading.Thread(target=target)
    t.start()
    t.join()

    if error_box:
        raise error_box[0]
    return result_box[0]
