"""A Scheme interpreter implementing a small subset of Scheme."""

import sys
import threading

sys.setrecursionlimit(200000)
try:
    sys.set_int_max_str_digits(0)
except (AttributeError, ValueError):
    pass
try:
    threading.stack_size(128 * 1024 * 1024)
except (ValueError, RuntimeError):
    pass


class SchemeError(Exception):
    def __init__(self, message, output=''):
        super().__init__(message)
        self.output = output


# === Data Types ===

class Symbol:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name
    def __repr__(self):
        return self.name
    def __eq__(self, other):
        return isinstance(other, Symbol) and self.name == other.name
    def __hash__(self):
        return hash(('sym', self.name))


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


class Cell:
    __slots__ = ('value',)
    def __init__(self, value):
        self.value = value


class Frame:
    __slots__ = ('vars', 'parent')
    def __init__(self, parent):
        self.vars = {}
        self.parent = parent


class Closure:
    __slots__ = ('params', 'body', 'env')
    def __init__(self, params, body, env):
        self.params = params
        self.body = body
        self.env = env


class Builtin:
    __slots__ = ('func', 'name')
    def __init__(self, func, name='builtin'):
        self.func = func
        self.name = name


class _Unspecified:
    def __repr__(self):
        return '<unspecified>'

UNSPECIFIED = _Unspecified()
UNBOUND = object()


class TailCall:
    __slots__ = ('proc', 'args')
    def __init__(self, proc, args):
        self.proc = proc
        self.args = args


# === Helpers ===

def is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)

def is_procedure(x):
    return isinstance(x, (Closure, Builtin))

def is_proper_list(x):
    while isinstance(x, Pair):
        x = x.cdr
    return isinstance(x, _Nil)

def to_list(x):
    result = []
    while isinstance(x, Pair):
        result.append(x.car)
        x = x.cdr
    return result

def list_to_scheme(lst):
    result = NIL
    for item in reversed(lst):
        result = Pair(item, result)
    return result

def body_to_list(pair):
    result = []
    current = pair
    while isinstance(current, Pair):
        result.append(current.car)
        current = current.cdr
    return result

def int_to_str(n, radix=10):
    if n == 0:
        return '0'
    negative = n < 0
    n = abs(n)
    digits = []
    digit_chars = '0123456789abcdef'
    while n > 0:
        digits.append(digit_chars[n % radix])
        n //= radix
    if negative:
        digits.append('-')
    return ''.join(reversed(digits))


# === Display / Write ===

def display_value(x):
    if isinstance(x, bool):
        return '#t' if x else '#f'
    if is_int(x):
        return int_to_str(x)
    if isinstance(x, str):
        return x
    if isinstance(x, Symbol):
        return x.name
    if isinstance(x, _Nil):
        return '()'
    if isinstance(x, _Unspecified):
        return ''
    if isinstance(x, (Closure, Builtin)):
        return '#<procedure>'
    if isinstance(x, Pair):
        return display_pair(x)
    return ''

def display_pair(p):
    parts = []
    current = p
    while isinstance(current, Pair):
        parts.append(display_value(current.car))
        current = current.cdr
    if isinstance(current, _Nil):
        return '(' + ' '.join(parts) + ')'
    else:
        parts.append('. ' + display_value(current))
        return '(' + ' '.join(parts) + ')'

def write_value(x):
    if isinstance(x, str):
        escaped = x.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        return '"' + escaped + '"'
    if isinstance(x, Pair):
        return write_pair(x)
    return display_value(x)

def write_pair(p):
    parts = []
    current = p
    while isinstance(current, Pair):
        parts.append(write_value(current.car))
        current = current.cdr
    if isinstance(current, _Nil):
        return '(' + ' '.join(parts) + ')'
    else:
        parts.append('. ' + write_value(current))
        return '(' + ' '.join(parts) + ')'


# === Reader ===

def tokenize(source):
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
            if i < n:
                i += 1
        elif c == '(':
            tokens.append(('(', None))
            i += 1
        elif c == ')':
            tokens.append((')', None))
            i += 1
        elif c == '"':
            i += 1
            chars = []
            terminated = False
            while i < n:
                if source[i] == '\\':
                    i += 1
                    if i >= n:
                        raise SchemeError("unterminated string")
                    ec = source[i]
                    if ec == '"':
                        chars.append('"')
                    elif ec == '\\':
                        chars.append('\\')
                    elif ec == 'n':
                        chars.append('\n')
                    else:
                        raise SchemeError("bad escape character")
                    i += 1
                elif source[i] == '"':
                    i += 1
                    terminated = True
                    break
                else:
                    chars.append(source[i])
                    i += 1
            if not terminated:
                raise SchemeError("unterminated string")
            tokens.append(('string', ''.join(chars)))
        elif c == "'":
            tokens.append(("'", None))
            i += 1
        else:
            start = i
            while i < n and source[i] not in ' \t\n\r()";\'':
                i += 1
            tokens.append(('atom', source[start:i]))
    return tokens


def parse_all(tokens):
    pos = [0]

    def peek():
        if pos[0] < len(tokens):
            return tokens[pos[0]]
        return None

    def advance():
        t = tokens[pos[0]]
        pos[0] += 1
        return t

    def parse_datum():
        t = peek()
        if t is None:
            raise SchemeError("unexpected end of input")
        kind, val = t
        if kind == '(':
            advance()
            return parse_list_body()
        elif kind == ')':
            raise SchemeError("unexpected )")
        elif kind == "'":
            advance()
            datum = parse_datum()
            return Pair(Symbol('quote'), Pair(datum, NIL))
        elif kind == 'string':
            advance()
            return val
        elif kind == 'atom':
            advance()
            return parse_atom(val)
        else:
            raise SchemeError("unexpected token")

    def parse_list_body():
        elements = []
        tail = None
        while True:
            t = peek()
            if t is None:
                raise SchemeError("unbalanced (")
            kind, val = t
            if kind == ')':
                advance()
                break
            if kind == 'atom' and val == '.':
                if len(elements) == 0:
                    raise SchemeError("dot with no preceding elements")
                advance()
                tail = parse_datum()
                t2 = peek()
                if t2 is None or t2[0] != ')':
                    raise SchemeError("expected ) after dotted tail")
                advance()
                break
            elem = parse_datum()
            elements.append(elem)
        if tail is not None:
            result = tail
        else:
            result = NIL
        for elem in reversed(elements):
            result = Pair(elem, result)
        return result

    forms = []
    while pos[0] < len(tokens):
        forms.append(parse_datum())
    return forms


def parse_atom(s):
    if s == '#t':
        return True
    if s == '#f':
        return False
    if s.startswith('#'):
        raise SchemeError("invalid # token: " + s)
    if is_integer_token(s):
        return int(s)
    return Symbol(s)


def is_integer_token(s):
    if not s:
        return False
    i = 0
    if s[0] in '+-':
        i = 1
    if i >= len(s):
        return False
    while i < len(s):
        if not ('0' <= s[i] <= '9'):
            return False
        i += 1
    return True


# === Environment ===

def lookup(name, env):
    while env is not None:
        if name in env.vars:
            cell = env.vars[name]
            if cell.value is UNBOUND:
                raise SchemeError("unbound variable: " + name.name)
            return cell.value
        env = env.parent
    raise SchemeError("unbound variable: " + name.name)


def find_binding(name, env):
    while env is not None:
        if name in env.vars:
            return env.vars[name]
        env = env.parent
    return None


def set_in_frame(frame, name, value):
    if name in frame.vars:
        frame.vars[name].value = value
    else:
        frame.vars[name] = Cell(value)


# === Builtin helpers ===

def _check_int(x, fname):
    if not is_int(x):
        raise SchemeError(fname + ": expected integer, got " + display_value(x))

def _check_pair(x, fname):
    if not isinstance(x, Pair):
        raise SchemeError(fname + ": expected pair, got " + display_value(x))


# === Builtins ===

def builtin_add(args, ctx):
    s = 0
    for a in args:
        _check_int(a, '+')
        s += a
    return s

def builtin_sub(args, ctx):
    for a in args:
        _check_int(a, '-')
    if len(args) == 1:
        return -args[0]
    r = args[0]
    for a in args[1:]:
        r -= a
    return r

def builtin_mul(args, ctx):
    p = 1
    for a in args:
        _check_int(a, '*')
        p *= a
    return p

def builtin_quotient(args, ctx):
    if len(args) != 2:
        raise SchemeError("quotient: expects 2 arguments")
    a, b = args
    _check_int(a, 'quotient')
    _check_int(b, 'quotient')
    if b == 0:
        raise SchemeError("quotient: division by zero")
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        q = -q
    return q

def builtin_remainder(args, ctx):
    if len(args) != 2:
        raise SchemeError("remainder: expects 2 arguments")
    a, b = args
    _check_int(a, 'remainder')
    _check_int(b, 'remainder')
    if b == 0:
        raise SchemeError("remainder: division by zero")
    r = abs(a) % abs(b)
    if a < 0:
        r = -r
    return r

def builtin_modulo(args, ctx):
    if len(args) != 2:
        raise SchemeError("modulo: expects 2 arguments")
    a, b = args
    _check_int(a, 'modulo')
    _check_int(b, 'modulo')
    if b == 0:
        raise SchemeError("modulo: division by zero")
    r = a % b
    return r

def builtin_eq(args, ctx):
    if len(args) < 1:
        raise SchemeError("=: expects at least 1 argument")
    for a in args:
        _check_int(a, '=')
    for i in range(len(args) - 1):
        if args[i] != args[i + 1]:
            return False
    return True

def builtin_lt(args, ctx):
    if len(args) < 1:
        raise SchemeError("<: expects at least 1 argument")
    for a in args:
        _check_int(a, '<')
    for i in range(len(args) - 1):
        if args[i] >= args[i + 1]:
            return False
    return True

def builtin_gt(args, ctx):
    if len(args) < 1:
        raise SchemeError(">: expects at least 1 argument")
    for a in args:
        _check_int(a, '>')
    for i in range(len(args) - 1):
        if args[i] <= args[i + 1]:
            return False
    return True

def builtin_le(args, ctx):
    if len(args) < 1:
        raise SchemeError("<=: expects at least 1 argument")
    for a in args:
        _check_int(a, '<=')
    for i in range(len(args) - 1):
        if args[i] > args[i + 1]:
            return False
    return True

def builtin_ge(args, ctx):
    if len(args) < 1:
        raise SchemeError(">=: expects at least 1 argument")
    for a in args:
        _check_int(a, '>=')
    for i in range(len(args) - 1):
        if args[i] < args[i + 1]:
            return False
    return True

def builtin_number_to_string(args, ctx):
    if len(args) == 1:
        n, radix = args[0], 10
    elif len(args) == 2:
        n, radix = args
    else:
        raise SchemeError("number->string: wrong number of arguments")
    _check_int(n, 'number->string')
    if not is_int(radix) or radix not in (2, 8, 10, 16):
        raise SchemeError("number->string: invalid radix")
    return int_to_str(n, radix)

def builtin_cons(args, ctx):
    if len(args) != 2:
        raise SchemeError("cons: expects 2 arguments")
    return Pair(args[0], args[1])

def builtin_car(args, ctx):
    if len(args) != 1:
        raise SchemeError("car: expects 1 argument")
    _check_pair(args[0], 'car')
    return args[0].car

def builtin_cdr(args, ctx):
    if len(args) != 1:
        raise SchemeError("cdr: expects 1 argument")
    _check_pair(args[0], 'cdr')
    return args[0].cdr

def builtin_list(args, ctx):
    return list_to_scheme(args)

def builtin_null(args, ctx):
    if len(args) != 1:
        raise SchemeError("null?: expects 1 argument")
    return isinstance(args[0], _Nil)

def builtin_pair(args, ctx):
    if len(args) != 1:
        raise SchemeError("pair?: expects 1 argument")
    return isinstance(args[0], Pair)

def builtin_listp(args, ctx):
    if len(args) != 1:
        raise SchemeError("list?: expects 1 argument")
    return is_proper_list(args[0])

def builtin_length(args, ctx):
    if len(args) != 1:
        raise SchemeError("length: expects 1 argument")
    x = args[0]
    count = 0
    while isinstance(x, Pair):
        count += 1
        x = x.cdr
    if not isinstance(x, _Nil):
        raise SchemeError("length: not a proper list")
    return count

def builtin_append(args, ctx):
    if len(args) == 0:
        return NIL
    if len(args) == 1:
        return args[0]
    for i in range(len(args) - 1):
        if not is_proper_list(args[i]):
            raise SchemeError("append: not a proper list")
    result = args[-1]
    for i in range(len(args) - 2, -1, -1):
        items = to_list(args[i])
        for item in reversed(items):
            result = Pair(item, result)
    return result

def builtin_reverse(args, ctx):
    if len(args) != 1:
        raise SchemeError("reverse: expects 1 argument")
    x = args[0]
    if not is_proper_list(x):
        raise SchemeError("reverse: not a proper list")
    items = to_list(x)
    result = NIL
    for item in items:
        result = Pair(item, result)
    return result

def builtin_eqq(args, ctx):
    if len(args) != 2:
        raise SchemeError("eq?: expects 2 arguments")
    a, b = args
    if isinstance(a, bool) and isinstance(b, bool):
        return a is b
    if is_int(a) and is_int(b):
        return a == b
    if isinstance(a, Symbol) and isinstance(b, Symbol):
        return a.name == b.name
    if isinstance(a, _Nil) and isinstance(b, _Nil):
        return True
    return a is b

def builtin_equal(args, ctx):
    if len(args) != 2:
        raise SchemeError("equal?: expects 2 arguments")
    return _equal_impl(args[0], args[1])

def _equal_impl(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a is b
    if is_int(a) and is_int(b):
        return a == b
    if isinstance(a, Symbol) and isinstance(b, Symbol):
        return a.name == b.name
    if isinstance(a, str) and isinstance(b, str):
        return a == b
    if isinstance(a, _Nil) and isinstance(b, _Nil):
        return True
    if isinstance(a, Pair) and isinstance(b, Pair):
        return _equal_impl(a.car, b.car) and _equal_impl(a.cdr, b.cdr)
    return a is b

def builtin_not(args, ctx):
    if len(args) != 1:
        raise SchemeError("not: expects 1 argument")
    return args[0] is False

def builtin_numberp(args, ctx):
    if len(args) != 1:
        raise SchemeError("number?: expects 1 argument")
    return is_int(args[0])

def builtin_symbolp(args, ctx):
    if len(args) != 1:
        raise SchemeError("symbol?: expects 1 argument")
    return isinstance(args[0], Symbol)

def builtin_stringp(args, ctx):
    if len(args) != 1:
        raise SchemeError("string?: expects 1 argument")
    return isinstance(args[0], str)

def builtin_procedurep(args, ctx):
    if len(args) != 1:
        raise SchemeError("procedure?: expects 1 argument")
    return is_procedure(args[0])

def builtin_string_append(args, ctx):
    for a in args:
        if not isinstance(a, str):
            raise SchemeError("string-append: expected string")
    return ''.join(args)

def builtin_display(args, ctx):
    if len(args) != 1:
        raise SchemeError("display: expects 1 argument")
    ctx.output.append(display_value(args[0]))
    return UNSPECIFIED

def builtin_newline(args, ctx):
    if len(args) != 0:
        raise SchemeError("newline: expects 0 arguments")
    ctx.output.append('\n')
    return UNSPECIFIED

def builtin_error(args, ctx):
    if len(args) < 1:
        raise SchemeError("error: expects at least 1 argument")
    msg = args[0]
    if not isinstance(msg, str):
        raise SchemeError("error: first argument must be a string")
    parts = [msg]
    for irritant in args[1:]:
        parts.append(' ' + write_value(irritant))
    raise SchemeError(''.join(parts))


# apply is special-cased in the evaluator
APPLY_BUILTIN = Builtin(None, 'apply')


def make_global_env():
    env = Frame(None)

    def add(name, func):
        env.vars[Symbol(name)] = Cell(Builtin(func, name))

    add('+', builtin_add)
    add('-', builtin_sub)
    add('*', builtin_mul)
    add('quotient', builtin_quotient)
    add('remainder', builtin_remainder)
    add('modulo', builtin_modulo)
    add('=', builtin_eq)
    add('<', builtin_lt)
    add('>', builtin_gt)
    add('<=', builtin_le)
    add('>=', builtin_ge)
    add('number->string', builtin_number_to_string)
    add('cons', builtin_cons)
    add('car', builtin_car)
    add('cdr', builtin_cdr)
    add('list', builtin_list)
    add('null?', builtin_null)
    add('pair?', builtin_pair)
    add('list?', builtin_listp)
    add('length', builtin_length)
    add('append', builtin_append)
    add('reverse', builtin_reverse)
    env.vars[Symbol('apply')] = Cell(APPLY_BUILTIN)
    add('eq?', builtin_eqq)
    add('equal?', builtin_equal)
    add('not', builtin_not)
    add('number?', builtin_numberp)
    add('symbol?', builtin_symbolp)
    add('string?', builtin_stringp)
    add('procedure?', builtin_procedurep)
    add('string-append', builtin_string_append)
    add('display', builtin_display)
    add('newline', builtin_newline)
    add('error', builtin_error)

    return env


# === Evaluator ===

class Context:
    def __init__(self):
        self.output = []
        self.global_env = None


def eval_non_tail(expr, env, ctx):
    result = eval_expr(expr, env, ctx)
    while isinstance(result, TailCall):
        result = apply_proc(result.proc, result.args, ctx)
    return result


def trampoline(expr, env, ctx):
    result = eval_expr(expr, env, ctx)
    while isinstance(result, TailCall):
        result = apply_proc(result.proc, result.args, ctx)
    return result


def eval_expr(expr, env, ctx):
    if isinstance(expr, bool):
        return expr
    if is_int(expr):
        return expr
    if isinstance(expr, str):
        return expr
    if isinstance(expr, Symbol):
        return lookup(expr, env)
    if isinstance(expr, _Nil):
        raise SchemeError("cannot evaluate ()")
    if isinstance(expr, Pair):
        head = expr.car
        if isinstance(head, Symbol):
            name = head.name
            if name == 'quote':
                return _eval_quote(expr, env, ctx)
            elif name == 'if':
                return _eval_if(expr, env, ctx)
            elif name == 'define':
                return _eval_define(expr, env, ctx)
            elif name == 'set!':
                return _eval_set(expr, env, ctx)
            elif name == 'begin':
                return _eval_begin(expr, env, ctx)
            elif name == 'cond':
                return _eval_cond(expr, env, ctx)
            elif name == 'and':
                return _eval_and(expr, env, ctx)
            elif name == 'or':
                return _eval_or(expr, env, ctx)
            elif name == 'lambda':
                return _eval_lambda(expr, env, ctx)
            elif name == 'let':
                return _eval_let(expr, env, ctx)
            elif name == 'let*':
                return _eval_letstar(expr, env, ctx)
            elif name == 'letrec':
                return _eval_letrec(expr, env, ctx)
        return _eval_application(expr, env, ctx)
    if isinstance(expr, _Unspecified):
        return expr
    raise SchemeError("cannot evaluate expression")


def _eval_quote(expr, env, ctx):
    rest = expr.cdr
    if not isinstance(rest, Pair):
        raise SchemeError("(quote) is malformed")
    if isinstance(rest.cdr, Pair):
        raise SchemeError("quote: too many arguments")
    return rest.car


def _eval_if(expr, env, ctx):
    rest = expr.cdr
    if not isinstance(rest, Pair):
        raise SchemeError("malformed if")
    test = rest.car
    rest = rest.cdr
    if not isinstance(rest, Pair):
        raise SchemeError("malformed if")
    then_expr = rest.car
    rest = rest.cdr
    if isinstance(rest, Pair):
        else_expr = rest.car
        if isinstance(rest.cdr, Pair):
            raise SchemeError("malformed if: too many arguments")
        val = eval_non_tail(test, env, ctx)
        if val is not False:
            return eval_expr(then_expr, env, ctx)
        else:
            return eval_expr(else_expr, env, ctx)
    elif isinstance(rest, _Nil):
        val = eval_non_tail(test, env, ctx)
        if val is not False:
            return eval_expr(then_expr, env, ctx)
        else:
            return UNSPECIFIED
    else:
        raise SchemeError("malformed if")


def _eval_define(expr, env, ctx):
    rest = expr.cdr
    if not isinstance(rest, Pair):
        raise SchemeError("malformed define")
    target = rest.car
    if isinstance(target, Symbol):
        rest2 = rest.cdr
        if not isinstance(rest2, Pair):
            raise SchemeError("malformed define")
        if isinstance(rest2.cdr, Pair):
            raise SchemeError("malformed define")
        val = eval_non_tail(rest2.car, env, ctx)
        set_in_frame(env, target, val)
        return UNSPECIFIED
    elif isinstance(target, Pair):
        name = target.car
        if not isinstance(name, Symbol):
            raise SchemeError("malformed define: name must be a symbol")
        formals = target.cdr
        body = body_to_list(rest.cdr)
        if not body:
            raise SchemeError("malformed define: empty body")
        closure = make_closure(formals, body, env)
        set_in_frame(env, name, closure)
        return UNSPECIFIED
    else:
        raise SchemeError("malformed define")


def _eval_set(expr, env, ctx):
    rest = expr.cdr
    if not isinstance(rest, Pair):
        raise SchemeError("malformed set!")
    name = rest.car
    if not isinstance(name, Symbol):
        raise SchemeError("set!: name must be a symbol")
    rest = rest.cdr
    if not isinstance(rest, Pair):
        raise SchemeError("malformed set!")
    if isinstance(rest.cdr, Pair):
        raise SchemeError("malformed set!")
    val = eval_non_tail(rest.car, env, ctx)
    cell = find_binding(name, env)
    if cell is None:
        raise SchemeError("set!: unbound variable: " + name.name)
    if cell.value is UNBOUND:
        raise SchemeError("set!: unbound variable: " + name.name)
    cell.value = val
    return UNSPECIFIED


def _eval_begin(expr, env, ctx):
    exprs = body_to_list(expr.cdr)
    if not exprs:
        raise SchemeError("(begin) is malformed")
    for e in exprs[:-1]:
        eval_non_tail(e, env, ctx)
    return eval_expr(exprs[-1], env, ctx)


def _eval_cond(expr, env, ctx):
    clauses = body_to_list(expr.cdr)
    for i, clause in enumerate(clauses):
        if not isinstance(clause, Pair):
            raise SchemeError("malformed cond clause")
        test = clause.car
        if isinstance(test, Symbol) and test.name == 'else':
            if i != len(clauses) - 1:
                raise SchemeError("cond: else must be last clause")
            exprs = body_to_list(clause.cdr)
            if not exprs:
                return UNSPECIFIED
            for e in exprs[:-1]:
                eval_non_tail(e, env, ctx)
            return eval_expr(exprs[-1], env, ctx)
        else:
            val = eval_non_tail(test, env, ctx)
            if val is not False:
                exprs = body_to_list(clause.cdr)
                if not exprs:
                    return val
                for e in exprs[:-1]:
                    eval_non_tail(e, env, ctx)
                return eval_expr(exprs[-1], env, ctx)
    return UNSPECIFIED


def _eval_and(expr, env, ctx):
    exprs = body_to_list(expr.cdr)
    if not exprs:
        return True
    for i, e in enumerate(exprs):
        if i == len(exprs) - 1:
            return eval_expr(e, env, ctx)
        else:
            val = eval_non_tail(e, env, ctx)
            if val is False:
                return False
    return True


def _eval_or(expr, env, ctx):
    exprs = body_to_list(expr.cdr)
    if not exprs:
        return False
    for i, e in enumerate(exprs):
        if i == len(exprs) - 1:
            return eval_expr(e, env, ctx)
        else:
            val = eval_non_tail(e, env, ctx)
            if val is not False:
                return val
    return False


def _eval_lambda(expr, env, ctx):
    rest = expr.cdr
    if not isinstance(rest, Pair):
        raise SchemeError("malformed lambda")
    formals = rest.car
    body = body_to_list(rest.cdr)
    if not body:
        raise SchemeError("malformed lambda: empty body")
    return make_closure(formals, body, env)


def _eval_let(expr, env, ctx):
    rest = expr.cdr
    if not isinstance(rest, Pair):
        raise SchemeError("malformed let")
    first = rest.car
    if isinstance(first, Symbol):
        return _eval_named_let(expr, env, ctx)
    bindings = first
    body = body_to_list(rest.cdr)
    if not body:
        raise SchemeError("malformed let: empty body")
    frame = Frame(env)
    current = bindings
    while isinstance(current, Pair):
        binding = current.car
        if not isinstance(binding, Pair):
            raise SchemeError("malformed let binding")
        var = binding.car
        if not isinstance(var, Symbol):
            raise SchemeError("let: binding name must be a symbol")
        init_rest = binding.cdr
        if not isinstance(init_rest, Pair):
            raise SchemeError("malformed let binding: missing init")
        if isinstance(init_rest.cdr, Pair):
            raise SchemeError("malformed let binding: too many inits")
        val = eval_non_tail(init_rest.car, env, ctx)
        frame.vars[var] = Cell(val)
        current = current.cdr
    if not isinstance(current, _Nil):
        raise SchemeError("malformed let bindings")
    return process_body(body, frame, ctx)


def _eval_letstar(expr, env, ctx):
    rest = expr.cdr
    if not isinstance(rest, Pair):
        raise SchemeError("malformed let*")
    bindings = rest.car
    body = body_to_list(rest.cdr)
    if not body:
        raise SchemeError("malformed let*: empty body")
    frame = Frame(env)
    current = bindings
    while isinstance(current, Pair):
        binding = current.car
        if not isinstance(binding, Pair):
            raise SchemeError("malformed let* binding")
        var = binding.car
        if not isinstance(var, Symbol):
            raise SchemeError("let*: binding name must be a symbol")
        init_rest = binding.cdr
        if not isinstance(init_rest, Pair):
            raise SchemeError("malformed let* binding: missing init")
        if isinstance(init_rest.cdr, Pair):
            raise SchemeError("malformed let* binding: too many inits")
        val = eval_non_tail(init_rest.car, frame, ctx)
        frame.vars[var] = Cell(val)
        current = current.cdr
    if not isinstance(current, _Nil):
        raise SchemeError("malformed let* bindings")
    return process_body(body, frame, ctx)


def _eval_letrec(expr, env, ctx):
    rest = expr.cdr
    if not isinstance(rest, Pair):
        raise SchemeError("malformed letrec")
    bindings = rest.car
    body = body_to_list(rest.cdr)
    if not body:
        raise SchemeError("malformed letrec: empty body")
    frame = Frame(env)
    names_inits = []
    current = bindings
    while isinstance(current, Pair):
        binding = current.car
        if not isinstance(binding, Pair):
            raise SchemeError("malformed letrec binding")
        var = binding.car
        if not isinstance(var, Symbol):
            raise SchemeError("letrec: binding name must be a symbol")
        init_rest = binding.cdr
        if not isinstance(init_rest, Pair):
            raise SchemeError("malformed letrec binding: missing init")
        if isinstance(init_rest.cdr, Pair):
            raise SchemeError("malformed letrec binding: too many inits")
        frame.vars[var] = Cell(UNBOUND)
        names_inits.append((var, init_rest.car))
        current = current.cdr
    if not isinstance(current, _Nil):
        raise SchemeError("malformed letrec bindings")
    for var, init_expr in names_inits:
        val = eval_non_tail(init_expr, frame, ctx)
        frame.vars[var].value = val
    return process_body(body, frame, ctx)


def _eval_named_let(expr, env, ctx):
    rest = expr.cdr
    name = rest.car
    bindings = rest.cdr.car
    body = body_to_list(rest.cdr.cdr)
    if not body:
        raise SchemeError("malformed named let: empty body")
    params = []
    inits = []
    current = bindings
    while isinstance(current, Pair):
        binding = current.car
        if not isinstance(binding, Pair):
            raise SchemeError("malformed named let binding")
        var = binding.car
        if not isinstance(var, Symbol):
            raise SchemeError("named let: binding name must be a symbol")
        init_rest = binding.cdr
        if not isinstance(init_rest, Pair):
            raise SchemeError("malformed named let binding: missing init")
        if isinstance(init_rest.cdr, Pair):
            raise SchemeError("malformed named let binding: too many inits")
        params.append(var)
        val = eval_non_tail(init_rest.car, env, ctx)
        inits.append(val)
        current = current.cdr
    if not isinstance(current, _Nil):
        raise SchemeError("malformed named let bindings")
    frame = Frame(env)
    frame.vars[name] = Cell(UNBOUND)
    closure = Closure(('fixed', params), body, frame)
    frame.vars[name].value = closure
    return apply_proc(closure, inits, ctx)


def _eval_application(expr, env, ctx):
    if not is_proper_list(expr):
        raise SchemeError("dotted form used as application")
    op = eval_non_tail(expr.car, env, ctx)
    args = []
    current = expr.cdr
    while isinstance(current, Pair):
        args.append(eval_non_tail(current.car, env, ctx))
        current = current.cdr
    if not isinstance(current, _Nil):
        raise SchemeError("dotted form used as application")
    if not is_procedure(op):
        raise SchemeError("not a procedure: " + display_value(op))
    if isinstance(op, Closure):
        check_arity(op.params, len(args))
    return TailCall(op, args)


# === Closure / Application ===

def make_closure(formals, body, env):
    if isinstance(formals, Symbol):
        return Closure(('variadic', formals), body, env)
    elif isinstance(formals, _Nil):
        return Closure(('fixed', []), body, env)
    elif isinstance(formals, Pair):
        params = []
        current = formals
        while isinstance(current, Pair):
            p = current.car
            if not isinstance(p, Symbol):
                raise SchemeError("lambda: parameter must be a symbol")
            params.append(p)
            current = current.cdr
        if isinstance(current, Symbol):
            return Closure(('dotted', params, current), body, env)
        elif isinstance(current, _Nil):
            return Closure(('fixed', params), body, env)
        else:
            raise SchemeError("malformed lambda formals")
    else:
        raise SchemeError("malformed lambda formals")


def check_arity(params, n_args):
    kind = params[0]
    if kind == 'fixed':
        _, names = params
        if n_args != len(names):
            raise SchemeError("wrong number of arguments: expected " +
                              str(len(names)) + ", got " + str(n_args))
    elif kind == 'dotted':
        _, names, _ = params
        if n_args < len(names):
            raise SchemeError("too few arguments: expected at least " +
                              str(len(names)) + ", got " + str(n_args))


def bind_params(frame, params, args):
    kind = params[0]
    if kind == 'fixed':
        _, names = params
        for name, val in zip(names, args):
            frame.vars[name] = Cell(val)
    elif kind == 'dotted':
        _, names, rest_name = params
        for name, val in zip(names, args):
            frame.vars[name] = Cell(val)
        rest_args = args[len(names):]
        frame.vars[rest_name] = Cell(list_to_scheme(rest_args))
    elif kind == 'variadic':
        _, args_name = params
        frame.vars[args_name] = Cell(list_to_scheme(args))


def apply_proc(proc, args, ctx):
    if proc is APPLY_BUILTIN:
        if len(args) < 2:
            raise SchemeError("apply: too few arguments")
        f = args[0]
        lst = args[-1]
        if not is_proper_list(lst):
            raise SchemeError("apply: last argument is not a proper list")
        rest = args[1:-1]
        expanded = rest + to_list(lst)
        if not is_procedure(f):
            raise SchemeError("apply: first argument is not a procedure")
        if isinstance(f, Closure):
            check_arity(f.params, len(expanded))
        return apply_proc(f, expanded, ctx)
    elif isinstance(proc, Closure):
        frame = Frame(proc.env)
        bind_params(frame, proc.params, args)
        body = proc.body
        return process_body(body, frame, ctx)
    elif isinstance(proc, Builtin):
        return proc.func(args, ctx)
    else:
        raise SchemeError("not a procedure")


# === Internal Definitions ===

def process_body(body, frame, ctx):
    def_names = set()
    for form in body:
        if isinstance(form, Pair) and isinstance(form.car, Symbol) and form.car.name == 'define':
            rest = form.cdr
            if isinstance(rest, Pair):
                target = rest.car
                if isinstance(target, Symbol):
                    def_names.add(target)
                elif isinstance(target, Pair) and isinstance(target.car, Symbol):
                    def_names.add(target.car)
    for name in def_names:
        frame.vars[name] = Cell(UNBOUND)
    for i, form in enumerate(body):
        if i < len(body) - 1:
            eval_non_tail(form, frame, ctx)
        else:
            return eval_expr(form, frame, ctx)


# === Main Entry Point ===

def _run(source):
    ctx = Context()
    ctx.global_env = make_global_env()

    try:
        tokens = tokenize(source)
        forms = parse_all(tokens)
    except SchemeError:
        raise
    except Exception as e:
        raise SchemeError(str(e))

    try:
        for form in forms:
            trampoline(form, ctx.global_env, ctx)
    except SchemeError as e:
        e.output = ''.join(ctx.output)
        raise
    except RecursionError:
        raise SchemeError("stack overflow", ''.join(ctx.output))
    except Exception as e:
        raise SchemeError(str(e), ''.join(ctx.output))

    return ''.join(ctx.output)


def run(source: str) -> str:
    result = [None]
    error = [None]

    def worker():
        try:
            result[0] = _run(source)
        except SchemeError as e:
            error[0] = e
        except Exception as e:
            error[0] = SchemeError(str(e), '')

    t = threading.Thread(target=worker)
    t.start()
    t.join()

    if error[0] is not None:
        raise error[0]
    return result[0]
