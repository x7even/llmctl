import sys
import re

try:
    sys.set_int_max_str_digits(0)
except AttributeError:
    pass

sys.setrecursionlimit(200000)


# === Data Types ===

class SchemeError(Exception):
    def __init__(self, msg=""):
        super().__init__(msg)
        self.output = ""


class Symbol:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name
    def __eq__(self, other):
        return isinstance(other, Symbol) and self.name == other.name
    def __hash__(self):
        return hash(('Sym', self.name))
    def __repr__(self):
        return f"Symbol({self.name!r})"


class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr
    def __repr__(self):
        return f"Pair({self.car!r}, {self.cdr!r})"


class Closure:
    __slots__ = ('formals', 'body', 'env')
    def __init__(self, formals, body, env):
        self.formals = formals
        self.body = body
        self.env = env


class Builtin:
    __slots__ = ('name', 'func', 'min_args', 'max_args')
    def __init__(self, name, func, min_args=0, max_args=None):
        self.name = name
        self.func = func
        self.min_args = min_args
        self.max_args = max_args
    def call(self, args, output):
        if len(args) < self.min_args:
            raise SchemeError(f"{self.name}: too few arguments")
        if self.max_args is not None and len(args) > self.max_args:
            raise SchemeError(f"{self.name}: too many arguments")
        return self.func(args, output)


class TailCall:
    __slots__ = ('proc', 'args')
    def __init__(self, proc, args):
        self.proc = proc
        self.args = args


UNSPECIFIED = object()
UNINITIALIZED = object()

SPECIAL_FORMS = frozenset({
    'quote', 'if', 'define', 'set!', 'begin', 'cond',
    'and', 'or', 'let', 'let*', 'letrec', 'lambda'
})


# === Environment ===

class Env:
    __slots__ = ('bindings', 'parent')
    def __init__(self, bindings, parent=None):
        self.bindings = bindings
        self.parent = parent

    def lookup(self, sym):
        env = self
        while env is not None:
            if sym in env.bindings:
                val = env.bindings[sym]
                if val is UNINITIALIZED:
                    raise SchemeError(f"uninitialized variable: {sym.name}")
                return val
            env = env.parent
        raise SchemeError(f"unbound variable: {sym.name}")

    def set(self, sym, value):
        env = self
        while env is not None:
            if sym in env.bindings:
                env.bindings[sym] = value
                return
            env = env.parent
        raise SchemeError(f"unbound variable: {sym.name}")


# === Reader ===

_INT_RE = re.compile(r'[+-]?[0-9]+\Z')

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
            terminated = False
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
                        raise SchemeError("invalid escape sequence in string")
                elif source[i] == '"':
                    i += 1
                    terminated = True
                    break
                else:
                    chars.append(source[i])
                    i += 1
            if not terminated:
                raise SchemeError("unterminated string")
            tokens.append(('STR', ''.join(chars)))
        else:
            start = i
            while i < n and source[i] not in ' \t\n\r()"\'':
                i += 1
            tok = source[start:i]
            if tok == '#t':
                tokens.append(True)
            elif tok == '#f':
                tokens.append(False)
            elif tok.startswith('#'):
                raise SchemeError(f"invalid token: {tok}")
            elif _INT_RE.match(tok):
                tokens.append(int(tok))
            else:
                tokens.append(Symbol(tok))
    return tokens


def _parse_one(tokens, i):
    if i >= len(tokens):
        raise SchemeError("unexpected end of input")
    tok = tokens[i]
    if tok == '(':
        i += 1
        return _parse_list(tokens, i)
    elif tok == ')':
        raise SchemeError("unexpected )")
    elif tok == "'":
        i += 1
        if i >= len(tokens):
            raise SchemeError("quote not followed by datum")
        datum, i = _parse_one(tokens, i)
        return [Symbol('quote'), datum]
    else:
        i += 1
        return tok


def _parse_list(tokens, i):
    elements = []
    while True:
        if i >= len(tokens):
            raise SchemeError("unbalanced (")
        tok = tokens[i]
        if tok == ')':
            i += 1
            return elements, i
        elif isinstance(tok, Symbol) and tok.name == '.':
            if not elements:
                raise SchemeError("dot must be preceded by at least one element")
            i += 1
            if i >= len(tokens):
                raise SchemeError("unbalanced (")
            datum, i = _parse_one(tokens, i)
            if i >= len(tokens) or tokens[i] != ')':
                raise SchemeError("expected ) after dotted form")
            i += 1
            result = datum
            for e in reversed(elements):
                result = Pair(e, result)
            return result, i
        else:
            elem, i = _parse_one(tokens, i)
            elements.append(elem)


def _read_all(source):
    tokens = _tokenize(source)
    forms = []
    i = 0
    while i < len(tokens):
        form, i = _parse_one(tokens, i)
        forms.append(form)
    return forms


# === Utility ===

def is_true(x):
    return x is not False


def is_procedure(x):
    return isinstance(x, (Closure, Builtin))


def _check_ints(args, name):
    for a in args:
        if isinstance(a, bool) or not isinstance(a, int):
            raise SchemeError(f"{name}: all arguments must be integers")


def int_to_string(n, radix=10):
    if n == 0:
        return "0"
    negative = n < 0
    n = abs(n)
    digits = "0123456789abcdef"
    result = []
    while n > 0:
        result.append(digits[n % radix])
        n //= radix
    if negative:
        result.append('-')
    return ''.join(reversed(result))


def display_value(x):
    if x is UNSPECIFIED:
        return ""
    if isinstance(x, bool):
        return "#t" if x else "#f"
    if isinstance(x, int):
        return int_to_string(x, 10)
    if isinstance(x, str):
        return x
    if isinstance(x, Symbol):
        return x.name
    if isinstance(x, (Closure, Builtin)):
        return "#<procedure>"
    if isinstance(x, list):
        if len(x) == 0:
            return "()"
        parts = [display_value(e) for e in x]
        return "(" + " ".join(parts) + ")"
    if isinstance(x, Pair):
        parts = []
        p = x
        while isinstance(p, Pair):
            parts.append(display_value(p.car))
            p = p.cdr
        parts.append(" . " + display_value(p))
        return "(" + " ".join(parts) + ")"
    return ""


def write_value(x):
    if x is UNSPECIFIED:
        return ""
    if isinstance(x, bool):
        return "#t" if x else "#f"
    if isinstance(x, int):
        return int_to_string(x, 10)
    if isinstance(x, str):
        s = x.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        return '"' + s + '"'
    if isinstance(x, Symbol):
        return x.name
    if isinstance(x, (Closure, Builtin)):
        return "#<procedure>"
    if isinstance(x, list):
        if len(x) == 0:
            return "()"
        parts = [write_value(e) for e in x]
        return "(" + " ".join(parts) + ")"
    if isinstance(x, Pair):
        parts = []
        p = x
        while isinstance(p, Pair):
            parts.append(write_value(p.car))
            p = p.cdr
        parts.append(" . " + write_value(p))
        return "(" + " ".join(parts) + ")"
    return ""


def scheme_equal(a, b):
    stack = [(a, b)]
    while stack:
        a, b = stack.pop()
        if a is b:
            continue
        if isinstance(a, bool) or isinstance(b, bool):
            if not (isinstance(a, bool) and isinstance(b, bool) and a == b):
                return False
            continue
        if isinstance(a, int) and isinstance(b, int):
            if a != b:
                return False
            continue
        if isinstance(a, str) and isinstance(b, str):
            if a != b:
                return False
            continue
        if isinstance(a, Symbol) and isinstance(b, Symbol):
            if a.name != b.name:
                return False
            continue
        if isinstance(a, (Closure, Builtin)) and isinstance(b, (Closure, Builtin)):
            if a is not b:
                return False
            continue
        if a is UNSPECIFIED and b is UNSPECIFIED:
            continue
        if isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                return False
            for i in range(len(a)):
                stack.append((a[i], b[i]))
            continue
        if isinstance(a, Pair) and isinstance(b, Pair):
            stack.append((a.cdr, b.cdr))
            stack.append((a.car, b.car))
            continue
        return False
    return True


def check_arity(proc, args):
    if isinstance(proc, Builtin):
        if len(args) < proc.min_args:
            raise SchemeError(f"{proc.name}: too few arguments")
        if proc.max_args is not None and len(args) > proc.max_args:
            raise SchemeError(f"{proc.name}: too many arguments")
    elif isinstance(proc, Closure):
        formals = proc.formals
        if isinstance(formals, Symbol):
            pass
        elif isinstance(formals, list):
            if len(args) != len(formals):
                raise SchemeError(f"wrong number of arguments: expected {len(formals)}, got {len(args)}")
        elif isinstance(formals, Pair):
            count = 0
            p = formals
            while isinstance(p, Pair):
                count += 1
                p = p.cdr
            if len(args) < count:
                raise SchemeError(f"wrong number of arguments: expected at least {count}, got {len(args)}")


def make_env(formals, args, parent_env):
    if isinstance(formals, Symbol):
        return Env({formals: list(args)}, parent_env)
    elif isinstance(formals, list):
        bindings = {}
        for sym, val in zip(formals, args):
            bindings[sym] = val
        return Env(bindings, parent_env)
    elif isinstance(formals, Pair):
        fixed = []
        p = formals
        while isinstance(p, Pair):
            fixed.append(p.car)
            p = p.cdr
        rest_sym = p
        bindings = {}
        for sym, val in zip(fixed, args[:len(fixed)]):
            bindings[sym] = val
        bindings[rest_sym] = list(args[len(fixed):])
        return Env(bindings, parent_env)
    raise SchemeError("invalid formals")


def get_internal_defs(forms):
    names = []
    for form in forms:
        if (isinstance(form, list) and len(form) >= 2
                and isinstance(form[0], Symbol) and form[0].name == 'define'):
            if len(form) >= 3:
                p = form[1]
                if isinstance(p, Symbol):
                    names.append(p)
                elif isinstance(p, list) and len(p) >= 1 and isinstance(p[0], Symbol):
                    names.append(p[0])
                elif isinstance(p, Pair) and isinstance(p.car, Symbol):
                    names.append(p.car)
    return names


# === Evaluator ===

def eval(expr, env, output):
    if isinstance(expr, bool):
        return expr
    if isinstance(expr, int):
        return expr
    if isinstance(expr, str):
        return expr
    if isinstance(expr, Symbol):
        return env.lookup(expr)
    if isinstance(expr, list):
        if len(expr) == 0:
            raise SchemeError("cannot apply empty list")
        head = expr[0]
        if isinstance(head, Symbol) and head.name in SPECIAL_FORMS:
            return eval_special(head.name, expr, env, output, tail=False)
        op = eval(head, env, output)
        args = [eval(a, env, output) for a in expr[1:]]
        if not is_procedure(op):
            raise SchemeError("not a procedure")
        check_arity(op, args)
        if isinstance(op, Closure):
            new_env = make_env(op.formals, args, op.env)
            return eval_body(op.body, new_env, output)
        else:
            return op.call(args, output)
    if isinstance(expr, Pair):
        raise SchemeError("dotted form used as application")
    raise SchemeError("invalid expression")


def eval_tail(expr, env, output):
    if isinstance(expr, bool):
        return expr
    if isinstance(expr, int):
        return expr
    if isinstance(expr, str):
        return expr
    if isinstance(expr, Symbol):
        return env.lookup(expr)
    if isinstance(expr, list):
        if len(expr) == 0:
            raise SchemeError("cannot apply empty list")
        head = expr[0]
        if isinstance(head, Symbol) and head.name in SPECIAL_FORMS:
            return eval_special(head.name, expr, env, output, tail=True)
        op = eval(head, env, output)
        args = [eval(a, env, output) for a in expr[1:]]
        if not is_procedure(op):
            raise SchemeError("not a procedure")
        check_arity(op, args)
        if isinstance(op, Builtin) and op.name == 'apply':
            f = args[0]
            mid = args[1:-1]
            lst = args[-1]
            if not isinstance(lst, list):
                raise SchemeError("apply: last argument must be a proper list")
            all_args = mid + lst
            if not is_procedure(f):
                raise SchemeError("apply: first argument is not a procedure")
            check_arity(f, all_args)
            return TailCall(f, all_args)
        return TailCall(op, args)
    if isinstance(expr, Pair):
        raise SchemeError("dotted form used as application")
    raise SchemeError("invalid expression")


def eval_body(forms, env, output):
    i = 0
    while True:
        internal_defs = get_internal_defs(forms)
        if internal_defs:
            env = Env({sym: UNINITIALIZED for sym in internal_defs}, env)
        if i < len(forms) - 1:
            eval(forms[i], env, output)
            i += 1
        else:
            result = eval_tail(forms[i], env, output)
            if isinstance(result, TailCall):
                proc, args = result.proc, result.args
                if isinstance(proc, Closure):
                    env = make_env(proc.formals, args, proc.env)
                    forms = proc.body
                    i = 0
                else:
                    return proc.call(args, output)
            else:
                return result


# === Special Forms ===

def eval_special(name, expr, env, output, tail=False):
    if name == 'quote':
        if len(expr) != 2:
            raise SchemeError("quote: expected (quote datum)")
        return expr[1]
    elif name == 'if':
        if len(expr) not in (3, 4):
            raise SchemeError("if: expected (if test then) or (if test then else)")
        test = eval(expr[1], env, output)
        if is_true(test):
            if tail:
                return eval_tail(expr[2], env, output)
            return eval(expr[2], env, output)
        else:
            if len(expr) == 4:
                if tail:
                    return eval_tail(expr[3], env, output)
                return eval(expr[3], env, output)
            return UNSPECIFIED
    elif name == 'define':
        return eval_define(expr, env, output)
    elif name == 'set!':
        if len(expr) != 3:
            raise SchemeError("set!: expected (set! name expr)")
        sym = expr[1]
        if not isinstance(sym, Symbol):
            raise SchemeError("set!: name must be a symbol")
        val = eval(expr[2], env, output)
        env.set(sym, val)
        return UNSPECIFIED
    elif name == 'begin':
        forms = expr[1:]
        if not forms:
            raise SchemeError("begin: empty")
        for f in forms[:-1]:
            eval(f, env, output)
        if tail:
            return eval_tail(forms[-1], env, output)
        return eval(forms[-1], env, output)
    elif name == 'cond':
        return eval_cond(expr, env, output, tail)
    elif name == 'and':
        args = expr[1:]
        if not args:
            return True
        for a in args[:-1]:
            val = eval(a, env, output)
            if val is False:
                return False
        if tail:
            return eval_tail(args[-1], env, output)
        return eval(args[-1], env, output)
    elif name == 'or':
        args = expr[1:]
        if not args:
            return False
        for a in args[:-1]:
            val = eval(a, env, output)
            if is_true(val):
                return val
        if tail:
            return eval_tail(args[-1], env, output)
        return eval(args[-1], env, output)
    elif name == 'let':
        return eval_let(expr, env, output)
    elif name == 'let*':
        return eval_letstar(expr, env, output)
    elif name == 'letrec':
        return eval_letrec(expr, env, output)
    elif name == 'lambda':
        return eval_lambda(expr, env, output)
    raise SchemeError(f"unknown special form: {name}")


def eval_define(expr, env, output):
    if len(expr) < 3:
        raise SchemeError("define: invalid form")
    name_or_params = expr[1]
    if isinstance(name_or_params, Symbol):
        if len(expr) != 3:
            raise SchemeError("define: invalid form")
        val = eval(expr[2], env, output)
        env.bindings[name_or_params] = val
        return UNSPECIFIED
    elif isinstance(name_or_params, (list, Pair)):
        if isinstance(name_or_params, list):
            fname = name_or_params[0]
            formals = name_or_params[1:]
        else:
            fname = name_or_params.car
            formals = name_or_params.cdr
        if not isinstance(fname, Symbol):
            raise SchemeError("define: name must be a symbol")
        body = expr[2:]
        if not body:
            raise SchemeError("define: body must be non-empty")
        closure = Closure(formals, body, env)
        env.bindings[fname] = closure
        return UNSPECIFIED
    else:
        raise SchemeError("define: invalid form")


def eval_lambda(expr, env, output):
    if len(expr) < 3:
        raise SchemeError("lambda: expected (lambda formals body...)")
    formals = expr[1]
    body = expr[2:]
    if not body:
        raise SchemeError("lambda: body must be non-empty")
    if isinstance(formals, Symbol):
        pass
    elif isinstance(formals, list):
        for f in formals:
            if not isinstance(f, Symbol):
                raise SchemeError("lambda: formals must be symbols")
    elif isinstance(formals, Pair):
        p = formals
        while isinstance(p, Pair):
            if not isinstance(p.car, Symbol):
                raise SchemeError("lambda: formals must be symbols")
            p = p.cdr
        if not isinstance(p, Symbol):
            raise SchemeError("lambda: invalid dotted formals")
    else:
        raise SchemeError("lambda: invalid formals")
    return Closure(formals, body, env)


def eval_let(expr, env, output):
    if len(expr) < 3:
        raise SchemeError("let: expected (let ((v init) ...) body...)")
    if isinstance(expr[1], Symbol):
        return eval_named_let(expr, env, output)
    bindings = expr[1]
    body = expr[2:]
    if not isinstance(bindings, list):
        raise SchemeError("let: bindings must be a list")
    for b in bindings:
        if not isinstance(b, list) or len(b) != 2 or not isinstance(b[0], Symbol):
            raise SchemeError("let: invalid binding")
    vals = [eval(init, env, output) for _, init in bindings]
    new_env = Env({b[0]: v for b, v in zip(bindings, vals)}, env)
    return eval_body(body, new_env, output)


def eval_letstar(expr, env, output):
    if len(expr) < 3:
        raise SchemeError("let*: expected (let* ((v init) ...) body...)")
    bindings = expr[1]
    body = expr[2:]
    if not isinstance(bindings, list):
        raise SchemeError("let*: bindings must be a list")
    for b in bindings:
        if not isinstance(b, list) or len(b) != 2 or not isinstance(b[0], Symbol):
            raise SchemeError("let*: invalid binding")
    current_env = env
    for sym, init in bindings:
        val = eval(init, current_env, output)
        current_env = Env({sym: val}, current_env)
    return eval_body(body, current_env, output)


def eval_letrec(expr, env, output):
    if len(expr) < 3:
        raise SchemeError("letrec: expected (letrec ((v init) ...) body...)")
    bindings = expr[1]
    body = expr[2:]
    if not isinstance(bindings, list):
        raise SchemeError("letrec: bindings must be a list")
    for b in bindings:
        if not isinstance(b, list) or len(b) != 2 or not isinstance(b[0], Symbol):
            raise SchemeError("letrec: invalid binding")
    new_env = Env({b[0]: UNINITIALIZED for b in bindings}, env)
    for sym, init in bindings:
        val = eval(init, new_env, output)
        new_env.bindings[sym] = val
    return eval_body(body, new_env, output)


def eval_named_let(expr, env, output):
    if len(expr) < 4:
        raise SchemeError("named let: invalid form")
    name = expr[1]
    if not isinstance(name, Symbol):
        raise SchemeError("named let: name must be a symbol")
    bindings = expr[2]
    body = expr[3:]
    if not isinstance(bindings, list):
        raise SchemeError("named let: bindings must be a list")
    for b in bindings:
        if not isinstance(b, list) or len(b) != 2 or not isinstance(b[0], Symbol):
            raise SchemeError("named let: invalid binding")
    args = [eval(init, env, output) for _, init in bindings]
    formals = [b[0] for b in bindings]
    rec_env = Env({}, env)
    rec_env.bindings[name] = UNINITIALIZED
    closure = Closure(formals, body, rec_env)
    rec_env.bindings[name] = closure
    call_env = make_env(formals, args, rec_env)
    return eval_body(body, call_env, output)


def eval_cond(expr, env, output, tail=False):
    clauses = expr[1:]
    if not clauses:
        raise SchemeError("cond: no clauses")
    for i, clause in enumerate(clauses):
        if not isinstance(clause, list) or len(clause) < 1:
            raise SchemeError("cond: invalid clause")
        test = clause[0]
        if isinstance(test, Symbol) and test.name == 'else':
            if i != len(clauses) - 1:
                raise SchemeError("cond: else must be last clause")
            if len(clause) < 2:
                raise SchemeError("cond: else clause needs expressions")
            for j in range(1, len(clause) - 1):
                eval(clause[j], env, output)
            if tail:
                return eval_tail(clause[-1], env, output)
            return eval(clause[-1], env, output)
        else:
            val = eval(test, env, output)
            if is_true(val):
                if len(clause) == 1:
                    return val
                for j in range(1, len(clause) - 1):
                    eval(clause[j], env, output)
                if tail:
                    return eval_tail(clause[-1], env, output)
                return eval(clause[-1], env, output)
    return UNSPECIFIED


# === Builtins ===

def builtin_plus(args, output):
    _check_ints(args, '+')
    return sum(args)

def builtin_star(args, output):
    _check_ints(args, '*')
    result = 1
    for a in args:
        result *= a
    return result

def builtin_minus(args, output):
    _check_ints(args, '-')
    if len(args) == 1:
        return -args[0]
    result = args[0]
    for a in args[1:]:
        result -= a
    return result

def builtin_quotient(args, output):
    a, b = args
    _check_ints(args, 'quotient')
    if b == 0:
        raise SchemeError("quotient: division by zero")
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        q = -q
    return q

def builtin_remainder(args, output):
    a, b = args
    _check_ints(args, 'remainder')
    if b == 0:
        raise SchemeError("remainder: division by zero")
    r = abs(a) % abs(b)
    if a < 0:
        r = -r
    return r

def builtin_modulo(args, output):
    a, b = args
    _check_ints(args, 'modulo')
    if b == 0:
        raise SchemeError("modulo: division by zero")
    r = abs(a) % abs(b)
    if b < 0:
        r = -r
    return r

def builtin_eq_op(args, output):
    _check_ints(args, '=')
    for i in range(len(args) - 1):
        if args[i] != args[i + 1]:
            return False
    return True

def builtin_lt(args, output):
    _check_ints(args, '<')
    for i in range(len(args) - 1):
        if not (args[i] < args[i + 1]):
            return False
    return True

def builtin_gt(args, output):
    _check_ints(args, '>')
    for i in range(len(args) - 1):
        if not (args[i] > args[i + 1]):
            return False
    return True

def builtin_le(args, output):
    _check_ints(args, '<=')
    for i in range(len(args) - 1):
        if not (args[i] <= args[i + 1]):
            return False
    return True

def builtin_ge(args, output):
    _check_ints(args, '>=')
    for i in range(len(args) - 1):
        if not (args[i] >= args[i + 1]):
            return False
    return True

def builtin_number_to_string(args, output):
    n = args[0]
    if isinstance(n, bool) or not isinstance(n, int):
        raise SchemeError("number->string: first argument must be an integer")
    if len(args) == 1:
        return int_to_string(n, 10)
    radix = args[1]
    if isinstance(radix, bool) or not isinstance(radix, int) or radix not in (2, 8, 10, 16):
        raise SchemeError("number->string: radix must be 2, 8, 10, or 16")
    return int_to_string(n, radix)

def builtin_cons(args, output):
    return Pair(args[0], args[1])

def builtin_car(args, output):
    p = args[0]
    if isinstance(p, list):
        if len(p) == 0:
            raise SchemeError("car: argument is not a pair")
        return p[0]
    if isinstance(p, Pair):
        return p.car
    raise SchemeError("car: argument is not a pair")

def builtin_cdr(args, output):
    p = args[0]
    if isinstance(p, list):
        if len(p) == 0:
            raise SchemeError("cdr: argument is not a pair")
        return p[1:]
    if isinstance(p, Pair):
        return p.cdr
    raise SchemeError("cdr: argument is not a pair")

def builtin_list(args, output):
    return list(args)

def builtin_null_p(args, output):
    return isinstance(args[0], list) and len(args[0]) == 0

def builtin_pair_p(args, output):
    x = args[0]
    if isinstance(x, Pair):
        return True
    if isinstance(x, list) and len(x) > 0:
        return True
    return False

def builtin_list_p(args, output):
    return isinstance(args[0], list)

def builtin_length(args, output):
    x = args[0]
    if isinstance(x, list):
        return len(x)
    raise SchemeError("length: argument is not a proper list")

def builtin_append(args, output):
    if len(args) == 0:
        return []
    for a in args[:-1]:
        if not isinstance(a, list):
            raise SchemeError("append: argument is not a proper list")
    last = args[-1]
    if isinstance(last, list):
        result = []
        for a in args:
            result.extend(a)
        return result
    else:
        total = sum(len(a) for a in args[:-1])
        if total == 0:
            return last
        p = last
        for a in reversed(args[:-1]):
            for elem in reversed(a):
                p = Pair(elem, p)
        return p

def builtin_reverse(args, output):
    x = args[0]
    if not isinstance(x, list):
        raise SchemeError("reverse: argument is not a proper list")
    return x[::-1]

def builtin_apply(args, output):
    f = args[0]
    mid = args[1:-1]
    lst = args[-1]
    if not isinstance(lst, list):
        raise SchemeError("apply: last argument must be a proper list")
    all_args = mid + lst
    if not is_procedure(f):
        raise SchemeError("apply: first argument is not a procedure")
    check_arity(f, all_args)
    if isinstance(f, Closure):
        env = make_env(f.formals, all_args, f.env)
        return eval_body(f.body, env, output)
    else:
        return f.call(all_args, output)

def builtin_eqq(args, output):
    a, b = args
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, int) and isinstance(b, int):
        return a == b
    if isinstance(a, Symbol) and isinstance(b, Symbol):
        return a.name == b.name
    if a is UNSPECIFIED and b is UNSPECIFIED:
        return True
    if isinstance(a, list) and isinstance(b, list):
        if len(a) == 0 and len(b) == 0:
            return True
        return a is b
    return a is b

def builtin_equal(args, output):
    return scheme_equal(args[0], args[1])

def builtin_not(args, output):
    return args[0] is False

def builtin_number_p(args, output):
    return isinstance(args[0], int) and not isinstance(args[0], bool)

def builtin_symbol_p(args, output):
    return isinstance(args[0], Symbol)

def builtin_string_p(args, output):
    return isinstance(args[0], str)

def builtin_procedure_p(args, output):
    return isinstance(args[0], (Closure, Builtin))

def builtin_string_append(args, output):
    for a in args:
        if not isinstance(a, str):
            raise SchemeError("string-append: all arguments must be strings")
    return ''.join(args)

def builtin_display(args, output):
    output.append(display_value(args[0]))
    return UNSPECIFIED

def builtin_newline(args, output):
    output.append("\n")
    return UNSPECIFIED

def builtin_error(args, output):
    msg = args[0]
    if not isinstance(msg, str):
        raise SchemeError("error: first argument must be a string")
    full_msg = msg
    for irritant in args[1:]:
        full_msg += " " + write_value(irritant)
    raise SchemeError(full_msg)


def make_global_env():
    env = Env({})
    env.bindings[Symbol('+')] = Builtin('+', builtin_plus, 0, None)
    env.bindings[Symbol('*')] = Builtin('*', builtin_star, 0, None)
    env.bindings[Symbol('-')] = Builtin('-', builtin_minus, 1, None)
    env.bindings[Symbol('quotient')] = Builtin('quotient', builtin_quotient, 2, 2)
    env.bindings[Symbol('remainder')] = Builtin('remainder', builtin_remainder, 2, 2)
    env.bindings[Symbol('modulo')] = Builtin('modulo', builtin_modulo, 2, 2)
    env.bindings[Symbol('=')] = Builtin('=', builtin_eq_op, 1, None)
    env.bindings[Symbol('<')] = Builtin('<', builtin_lt, 1, None)
    env.bindings[Symbol('>')] = Builtin('>', builtin_gt, 1, None)
    env.bindings[Symbol('<=')] = Builtin('<=', builtin_le, 1, None)
    env.bindings[Symbol('>=')] = Builtin('>=', builtin_ge, 1, None)
    env.bindings[Symbol('number->string')] = Builtin('number->string', builtin_number_to_string, 1, 2)
    env.bindings[Symbol('cons')] = Builtin('cons', builtin_cons, 2, 2)
    env.bindings[Symbol('car')] = Builtin('car', builtin_car, 1, 1)
    env.bindings[Symbol('cdr')] = Builtin('cdr', builtin_cdr, 1, 1)
    env.bindings[Symbol('list')] = Builtin('list', builtin_list, 0, None)
    env.bindings[Symbol('null?')] = Builtin('null?', builtin_null_p, 1, 1)
    env.bindings[Symbol('pair?')] = Builtin('pair?', builtin_pair_p, 1, 1)
    env.bindings[Symbol('list?')] = Builtin('list?', builtin_list_p, 1, 1)
    env.bindings[Symbol('length')] = Builtin('length', builtin_length, 1, 1)
    env.bindings[Symbol('append')] = Builtin('append', builtin_append, 0, None)
    env.bindings[Symbol('reverse')] = Builtin('reverse', builtin_reverse, 1, 1)
    env.bindings[Symbol('apply')] = Builtin('apply', builtin_apply, 2, None)
    env.bindings[Symbol('eq?')] = Builtin('eq?', builtin_eqq, 2, 2)
    env.bindings[Symbol('equal?')] = Builtin('equal?', builtin_equal, 2, 2)
    env.bindings[Symbol('not')] = Builtin('not', builtin_not, 1, 1)
    env.bindings[Symbol('number?')] = Builtin('number?', builtin_number_p, 1, 1)
    env.bindings[Symbol('symbol?')] = Builtin('symbol?', builtin_symbol_p, 1, 1)
    env.bindings[Symbol('string?')] = Builtin('string?', builtin_string_p, 1, 1)
    env.bindings[Symbol('procedure?')] = Builtin('procedure?', builtin_procedure_p, 1, 1)
    env.bindings[Symbol('string-append')] = Builtin('string-append', builtin_string_append, 0, None)
    env.bindings[Symbol('display')] = Builtin('display', builtin_display, 1, 1)
    env.bindings[Symbol('newline')] = Builtin('newline', builtin_newline, 0, 0)
    env.bindings[Symbol('error')] = Builtin('error', builtin_error, 1, None)
    return env


# === Public API ===

def run(source):
    try:
        forms = _read_all(source)
    except SchemeError:
        raise
    except Exception as e:
        raise SchemeError(str(e))

    global_env = make_global_env()
    output = []

    try:
        for form in forms:
            eval(form, global_env, output)
    except SchemeError as e:
        e.output = ''.join(output)
        raise
    except RecursionError:
        exc = SchemeError("maximum recursion depth exceeded")
        exc.output = ''.join(output)
        raise exc
    except Exception as e:
        exc = SchemeError(str(e))
        exc.output = ''.join(output)
        raise exc

    return ''.join(output)