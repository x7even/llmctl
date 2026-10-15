"""Scheme interpreter for a small, precisely specified subset."""
import sys
import threading

try:
    sys.set_int_max_str_digits(0)
except (AttributeError, ValueError):
    pass


class SchemeError(Exception):
    def __init__(self, message, output=''):
        super().__init__(message)
        self.output = output


# ===================== Data Types =====================

class Bool:
    __slots__ = ('val',)
    def __init__(self, val): self.val = val

class Sym:
    __slots__ = ('name',)
    def __init__(self, name): self.name = name

class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr): self.car = car; self.cdr = cdr

class EmptyList:
    pass

class Unspecified:
    pass

class Uninitialized:
    pass

class Closure:
    __slots__ = ('formals', 'body', 'env')
    def __init__(self, formals, body, env):
        self.formals = formals; self.body = body; self.env = env

class Builtin:
    __slots__ = ('name', 'func')
    def __init__(self, name, func): self.name = name; self.func = func

TRUE = Bool(True)
FALSE = Bool(False)
NIL = EmptyList()
UNSPECIFIED = Unspecified()
UNINIT = Uninitialized()


# ===================== Type predicates =====================

def is_int(x): return isinstance(x, int) and not isinstance(x, bool)
def is_bool(x): return isinstance(x, Bool)
def is_string(x): return isinstance(x, str)
def is_symbol(x): return isinstance(x, Sym)
def is_pair(x): return isinstance(x, Pair)
def is_nil(x): return isinstance(x, EmptyList)
def is_procedure(x): return isinstance(x, (Closure, Builtin))
def is_true(x): return not (isinstance(x, Bool) and not x.val)

def is_proper_list(x):
    while isinstance(x, Pair):
        x = x.cdr
    return isinstance(x, EmptyList)

def list_to_scheme(items):
    r = NIL
    for item in reversed(items):
        r = Pair(item, r)
    return r

def scheme_to_list(p):
    items = []
    while isinstance(p, Pair):
        items.append(p.car)
        p = p.cdr
    return items


# ===================== Reader =====================

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
        elif c == '(':
            tokens.append(('(', '(')); i += 1
        elif c == ')':
            tokens.append((')', ')')); i += 1
        elif c == "'":
            tokens.append(("'", "'")); i += 1
        elif c == '"':
            i += 1
            chars = []
            terminated = False
            while i < n:
                c = source[i]
                if c == '"':
                    i += 1; terminated = True; break
                elif c == '\\':
                    i += 1
                    if i >= n:
                        raise SchemeError("unterminated string")
                    ec = source[i]
                    if ec == '"': chars.append('"')
                    elif ec == '\\': chars.append('\\')
                    elif ec == 'n': chars.append('\n')
                    else: raise SchemeError("invalid escape")
                    i += 1
                else:
                    chars.append(c); i += 1
            if not terminated:
                raise SchemeError("unterminated string")
            tokens.append(('string', ''.join(chars)))
        else:
            j = i
            while j < n and source[j] not in ' \t\n\r()";\'':
                j += 1
            tokens.append(('atom', source[i:j]))
            i = j
    return tokens


def parse_integer(s):
    if not s: return None
    start = 1 if s[0] in '+-' else 0
    if start >= len(s): return None
    for c in s[start:]:
        if c < '0' or c > '9': return None
    return int(s)


def parse_atom(s):
    if s == '#t': return TRUE
    if s == '#f': return FALSE
    if s.startswith('#'): raise SchemeError(f"invalid token: {s}")
    n = parse_integer(s)
    if n is not None: return n
    return Sym(s)


def read_datum(tokens, pos):
    if pos >= len(tokens):
        raise SchemeError("unexpected end of input")
    ttype, tval = tokens[pos]
    if ttype == "'":
        datum, pos = read_datum(tokens, pos + 1)
        return Pair(Sym('quote'), Pair(datum, NIL)), pos
    elif ttype == '(':
        return read_list(tokens, pos + 1)
    elif ttype == ')':
        raise SchemeError("unexpected )")
    elif ttype == 'string':
        return tval, pos + 1
    elif ttype == 'atom':
        return parse_atom(tval), pos + 1
    raise SchemeError("unexpected token")


def read_list(tokens, pos):
    elements = []
    dot_seen = False
    while True:
        if pos >= len(tokens):
            raise SchemeError("unbalanced (")
        ttype, tval = tokens[pos]
        if ttype == ')':
            if dot_seen:
                raise SchemeError("dot not followed by datum")
            return list_to_scheme(elements), pos + 1
        if ttype == 'atom' and tval == '.' and not dot_seen:
            if len(elements) == 0:
                raise SchemeError("dot must be preceded by at least one element")
            dot_seen = True
            pos += 1
            if pos >= len(tokens):
                raise SchemeError("unexpected end of input after dot")
            datum, pos = read_datum(tokens, pos)
            if pos >= len(tokens) or tokens[pos][0] != ')':
                raise SchemeError("expected ) after dot datum")
            result = datum
            for elem in reversed(elements):
                result = Pair(elem, result)
            return result, pos + 1
        if dot_seen:
            raise SchemeError("expected ) after dot datum")
        datum, pos = read_datum(tokens, pos)
        elements.append(datum)


def read_all(source):
    tokens = tokenize(source)
    forms = []
    pos = 0
    while pos < len(tokens):
        datum, pos = read_datum(tokens, pos)
        forms.append(datum)
    return forms


# ===================== Environment =====================

class Frame:
    __slots__ = ('vars', 'parent')
    def __init__(self, parent=None):
        self.vars = {}
        self.parent = parent

    def lookup(self, name):
        f = self
        while f is not None:
            if name in f.vars:
                val = f.vars[name]
                if isinstance(val, Uninitialized):
                    raise SchemeError(f"uninitialized variable: {name}")
                return val
            f = f.parent
        raise SchemeError(f"unbound variable: {name}")

    def set(self, name, value):
        f = self
        while f is not None:
            if name in f.vars:
                f.vars[name] = value
                return
            f = f.parent
        raise SchemeError(f"unbound variable: {name}")

    def define(self, name, value):
        self.vars[name] = value


# ===================== Output =====================

class Output:
    def __init__(self): self.parts = []
    def write(self, s): self.parts.append(s)
    def get(self): return ''.join(self.parts)


# ===================== Display / Write =====================

def display_str(x):
    if isinstance(x, int) and not isinstance(x, bool): return str(x)
    if isinstance(x, Bool): return '#t' if x.val else '#f'
    if isinstance(x, str): return x
    if isinstance(x, Sym): return x.name
    if isinstance(x, EmptyList): return '()'
    if isinstance(x, Unspecified): return ''
    if isinstance(x, (Closure, Builtin)): return '#<procedure>'
    if isinstance(x, Pair): return display_pair(x)
    return str(x)

def display_pair(p):
    parts = ['(']
    parts.append(display_str(p.car))
    cur = p.cdr
    while isinstance(cur, Pair):
        parts.append(' ')
        parts.append(display_str(cur.car))
        cur = cur.cdr
    if not isinstance(cur, EmptyList):
        parts.append(' . ')
        parts.append(display_str(cur))
    parts.append(')')
    return ''.join(parts)

def write_str(x):
    if isinstance(x, str):
        return '"' + x.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'
    if isinstance(x, Pair):
        return write_pair(x)
    return display_str(x)

def write_pair(p):
    parts = ['(']
    parts.append(write_str(p.car))
    cur = p.cdr
    while isinstance(cur, Pair):
        parts.append(' ')
        parts.append(write_str(cur.car))
        cur = cur.cdr
    if not isinstance(cur, EmptyList):
        parts.append(' . ')
        parts.append(write_str(cur))
    parts.append(')')
    return ''.join(parts)


# ===================== Evaluator =====================

class TailCall:
    __slots__ = ('proc', 'args')
    def __init__(self, proc, args): self.proc = proc; self.args = args


def car(p):
    if not isinstance(p, Pair): raise SchemeError("car: not a pair")
    return p.car

def cdr(p):
    if not isinstance(p, Pair): raise SchemeError("cdr: not a pair")
    return p.cdr


def eval_expr(expr, env):
    if isinstance(expr, int) and not isinstance(expr, bool): return expr
    if isinstance(expr, Bool): return expr
    if isinstance(expr, str): return expr
    if isinstance(expr, Unspecified): return expr
    if isinstance(expr, Sym): return env.lookup(expr.name)
    if isinstance(expr, EmptyList): raise SchemeError("cannot evaluate ()")
    if isinstance(expr, Pair):
        if not is_proper_list(expr):
            raise SchemeError("dotted form cannot be used as application")
        head = expr.car
        rest = expr.cdr
        if isinstance(head, Sym):
            name = head.name
            if name == 'quote': return eval_quote(rest)
            if name == 'if': return eval_if(rest, env)
            if name == 'lambda': return eval_lambda(rest, env)
            if name == 'define': return eval_define(rest, env)
            if name == 'set!': return eval_setbang(rest, env)
            if name == 'begin': return eval_begin(rest, env)
            if name == 'cond': return eval_cond(rest, env)
            if name == 'and': return eval_and(rest, env)
            if name == 'or': return eval_or(rest, env)
            if name == 'let': return eval_let(rest, env)
            if name == 'let*': return eval_letstar(rest, env)
            if name == 'letrec': return eval_letrec(rest, env)
            if name == 'apply': return eval_apply_form(rest, env)
        return eval_application(expr, env)
    raise SchemeError("cannot evaluate expression")


def eval_quote(args):
    if is_nil(args): raise SchemeError("malformed quote")
    return car(args)

def eval_if(args, env):
    if is_nil(args): raise SchemeError("malformed if")
    test = car(args); rest = cdr(args)
    if is_nil(rest): raise SchemeError("malformed if")
    then = car(rest); rest = cdr(rest)
    tv = eval_non_tail(test, env)
    if is_true(tv):
        return eval_expr(then, env)
    if not is_nil(rest):
        return eval_expr(car(rest), env)
    return UNSPECIFIED

def eval_lambda(args, env):
    if is_nil(args): raise SchemeError("malformed lambda")
    formals = car(args)
    body = scheme_to_list(cdr(args))
    if len(body) == 0: raise SchemeError("empty body")
    return Closure(formals, body, env)

def eval_define(args, env):
    if is_nil(args): raise SchemeError("malformed define")
    target = car(args); rest = cdr(args)
    if is_symbol(target):
        if is_nil(rest): raise SchemeError("malformed define")
        val = eval_non_tail(car(rest), env)
        env.define(target.name, val)
        return UNSPECIFIED
    elif is_pair(target):
        name = car(target)
        if not is_symbol(name): raise SchemeError("malformed define")
        formals = cdr(target)
        body = scheme_to_list(rest)
        if len(body) == 0: raise SchemeError("empty body")
        env.define(name.name, Closure(formals, body, env))
        return UNSPECIFIED
    raise SchemeError("malformed define")

def eval_setbang(args, env):
    if is_nil(args): raise SchemeError("malformed set!")
    name = car(args)
    if not is_symbol(name): raise SchemeError("malformed set!")
    rest = cdr(args)
    if is_nil(rest): raise SchemeError("malformed set!")
    val = eval_non_tail(car(rest), env)
    env.set(name.name, val)
    return UNSPECIFIED

def eval_begin(args, env):
    if is_nil(args): raise SchemeError("malformed begin")
    forms = scheme_to_list(args)
    for f in forms[:-1]:
        eval_non_tail(f, env)
    return eval_expr(forms[-1], env)

def eval_cond(args, env):
    if is_nil(args): raise SchemeError("malformed cond")
    for clause in scheme_to_list(args):
        if not is_pair(clause): raise SchemeError("malformed cond clause")
        test = car(clause)
        exprs = scheme_to_list(cdr(clause))
        if is_symbol(test) and test.name == 'else':
            if len(exprs) == 0: return UNSPECIFIED
            for e in exprs[:-1]: eval_non_tail(e, env)
            return eval_expr(exprs[-1], env)
        tv = eval_non_tail(test, env)
        if is_true(tv):
            if len(exprs) == 0: return tv
            for e in exprs[:-1]: eval_non_tail(e, env)
            return eval_expr(exprs[-1], env)
    return UNSPECIFIED

def eval_and(args, env):
    if is_nil(args): return TRUE
    exprs = scheme_to_list(args)
    for i, e in enumerate(exprs):
        if i == len(exprs) - 1:
            return eval_expr(e, env)
        v = eval_non_tail(e, env)
        if not is_true(v): return FALSE
    return TRUE

def eval_or(args, env):
    if is_nil(args): return FALSE
    exprs = scheme_to_list(args)
    for i, e in enumerate(exprs):
        if i == len(exprs) - 1:
            return eval_expr(e, env)
        v = eval_non_tail(e, env)
        if is_true(v): return v
    return FALSE

def eval_let(args, env):
    if is_nil(args): raise SchemeError("malformed let")
    first = car(args); rest = cdr(args)
    if is_symbol(first):
        return eval_named_let(first, rest, env)
    bindings = scheme_to_list(first)
    body = scheme_to_list(rest)
    if len(body) == 0: raise SchemeError("empty body")
    frame = Frame(env)
    for b in bindings:
        if not is_pair(b): raise SchemeError("malformed let binding")
        v = car(b)
        if not is_symbol(v): raise SchemeError("malformed let binding")
        if is_nil(cdr(b)): raise SchemeError("malformed let binding")
        frame.vars[v.name] = eval_non_tail(car(cdr(b)), env)
    return execute_body(body, frame)

def eval_named_let(name, args, env):
    if is_nil(args): raise SchemeError("malformed named let")
    bindings = scheme_to_list(car(args))
    body = scheme_to_list(cdr(args))
    if len(body) == 0: raise SchemeError("empty body")
    formals = list_to_scheme([b.car for b in bindings])
    frame = Frame(env)
    closure = Closure(formals, body, frame)
    frame.vars[name.name] = closure
    inits = [car(cdr(b)) for b in bindings]
    arg_vals = [eval_non_tail(init, env) for init in inits]
    return TailCall(closure, arg_vals)

def eval_letstar(args, env):
    if is_nil(args): raise SchemeError("malformed let*")
    bindings = scheme_to_list(car(args))
    body = scheme_to_list(cdr(args))
    if len(body) == 0: raise SchemeError("empty body")
    frame = Frame(env)
    for b in bindings:
        if not is_pair(b): raise SchemeError("malformed let* binding")
        v = car(b)
        if not is_symbol(v): raise SchemeError("malformed let* binding")
        if is_nil(cdr(b)): raise SchemeError("malformed let* binding")
        frame.vars[v.name] = eval_non_tail(car(cdr(b)), frame)
    return execute_body(body, frame)

def eval_letrec(args, env):
    if is_nil(args): raise SchemeError("malformed letrec")
    bindings = scheme_to_list(car(args))
    body = scheme_to_list(cdr(args))
    if len(body) == 0: raise SchemeError("empty body")
    frame = Frame(env)
    for b in bindings:
        if not is_pair(b): raise SchemeError("malformed letrec binding")
        v = car(b)
        if not is_symbol(v): raise SchemeError("malformed letrec binding")
        frame.vars[v.name] = UNINIT
    for b in bindings:
        v = car(b)
        val = eval_non_tail(car(cdr(b)), frame)
        frame.vars[v.name] = val
    return execute_body(body, frame)

def eval_apply_form(args, env):
    if is_nil(args): raise SchemeError("malformed apply")
    items = scheme_to_list(args)
    if len(items) < 2: raise SchemeError("apply requires at least 2 arguments")
    proc = eval_non_tail(items[0], env)
    fixed = [eval_non_tail(a, env) for a in items[1:-1]]
    last = eval_non_tail(items[-1], env)
    if not is_proper_list(last):
        raise SchemeError("apply: last argument must be a proper list")
    all_args = fixed + scheme_to_list(last)
    if not is_procedure(proc):
        raise SchemeError("apply: not a procedure")
    return TailCall(proc, all_args)

def eval_application(form, env):
    head = form.car
    arg_exprs = scheme_to_list(form.cdr)
    proc = eval_non_tail(head, env)
    args = [eval_non_tail(a, env) for a in arg_exprs]
    if not is_procedure(proc):
        raise SchemeError(f"not a procedure: {display_str(proc)}")
    return TailCall(proc, args)


def eval_non_tail(expr, env):
    result = eval_expr(expr, env)
    if isinstance(result, TailCall):
        return do_tail_call(result)
    return result


def do_tail_call(tc):
    proc = tc.proc
    args = tc.args
    if isinstance(proc, Closure):
        return apply_closure(proc, args)
    elif isinstance(proc, Builtin):
        return proc.func(args)
    raise SchemeError("not a procedure")


def apply_closure(closure, args):
    frame = Frame(closure.env)
    bind_formals(closure.formals, args, frame)
    body = closure.body
    inner = setup_internal_defs(body, frame)
    for form in body[:-1]:
        eval_non_tail(form, inner)
    return eval_non_tail(body[-1], inner)


def setup_internal_defs(body, env):
    names = extract_internal_defs(body)
    if names:
        inner = Frame(env)
        for name in names:
            inner.vars[name] = UNINIT
        return inner
    return env


def extract_internal_defs(body):
    names = []
    for form in body:
        if is_pair(form) and is_symbol(form.car) and form.car.name == 'define':
            if is_pair(form.cdr):
                target = form.cdr.car
                if is_symbol(target):
                    names.append(target.name)
                elif is_pair(target) and is_symbol(target.car):
                    names.append(target.car.name)
    return names


def bind_formals(formals, args, frame):
    if is_symbol(formals):
        frame.vars[formals.name] = list_to_scheme(args)
    elif is_nil(formals):
        if len(args) != 0: raise SchemeError("wrong number of arguments")
    elif is_pair(formals):
        params = []
        cur = formals
        while is_pair(cur):
            p = cur.car
            if not is_symbol(p): raise SchemeError("malformed formals")
            params.append(p.name)
            cur = cur.cdr
        if is_nil(cur):
            if len(args) != len(params): raise SchemeError("wrong number of arguments")
            for name, arg in zip(params, args):
                frame.vars[name] = arg
        elif is_symbol(cur):
            if len(args) < len(params): raise SchemeError("wrong number of arguments")
            for name, arg in zip(params, args):
                frame.vars[name] = arg
            frame.vars[cur.name] = list_to_scheme(args[len(params):])
        else:
            raise SchemeError("malformed formals")
    else:
        raise SchemeError("malformed formals")


def execute_body(body, env):
    inner = setup_internal_defs(body, env)
    for i, form in enumerate(body):
        if i == len(body) - 1:
            if is_pair(form) and is_symbol(form.car) and form.car.name == 'define':
                do_internal_define(form, inner)
                return UNSPECIFIED
            return eval_expr(form, inner)
        else:
            if is_pair(form) and is_symbol(form.car) and form.car.name == 'define':
                do_internal_define(form, inner)
            else:
                eval_non_tail(form, inner)
    return UNSPECIFIED


def do_internal_define(form, env):
    args = form.cdr
    target = car(args)
    rest = cdr(args)
    if is_symbol(target):
        if is_nil(rest): raise SchemeError("malformed define")
        env.vars[target.name] = eval_non_tail(car(rest), env)
    elif is_pair(target):
        name = car(target)
        if not is_symbol(name): raise SchemeError("malformed define")
        formals = cdr(target)
        body = scheme_to_list(rest)
        if len(body) == 0: raise SchemeError("empty body")
        env.vars[name.name] = Closure(formals, body, env)
    else:
        raise SchemeError("malformed define")


def run_tail(expr, env):
    while True:
        result = eval_expr(expr, env)
        if isinstance(result, TailCall):
            proc = result.proc
            args = result.args
            if isinstance(proc, Closure):
                frame = Frame(proc.env)
                bind_formals(proc.formals, args, frame)
                body = proc.body
                inner = setup_internal_defs(body, frame)
                for form in body[:-1]:
                    eval_non_tail(form, inner)
                expr = body[-1]
                env = inner
            elif isinstance(proc, Builtin):
                return proc.func(args)
            else:
                raise SchemeError("not a procedure")
        else:
            return result


# ===================== Builtins =====================

def _check_int(x, fname):
    if not is_int(x):
        raise SchemeError(f"{fname}: expected integer, got {display_str(x)}")

def _check_arity(args, lo, hi=None, name=''):
    n = len(args)
    if hi is None:
        if n != lo: raise SchemeError(f"{name}: wrong number of arguments")
    else:
        if n < lo or (hi != -1 and n > hi):
            raise SchemeError(f"{name}: wrong number of arguments")

def builtin_plus(args):
    r = 0
    for a in args: _check_int(a, '+'); r += a
    return r

def builtin_times(args):
    r = 1
    for a in args: _check_int(a, '*'); r *= a
    return r

def builtin_minus(args):
    if len(args) < 1: raise SchemeError("-: wrong number of arguments")
    _check_int(args[0], '-')
    if len(args) == 1: return -args[0]
    r = args[0]
    for a in args[1:]: _check_int(a, '-'); r -= a
    return r

def builtin_quotient(args):
    if len(args) != 2: raise SchemeError("quotient: wrong number of arguments")
    a, b = args
    _check_int(a, 'quotient'); _check_int(b, 'quotient')
    if b == 0: raise SchemeError("quotient: division by zero")
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0): q = -q
    return q

def builtin_remainder(args):
    if len(args) != 2: raise SchemeError("remainder: wrong number of arguments")
    a, b = args
    _check_int(a, 'remainder'); _check_int(b, 'remainder')
    if b == 0: raise SchemeError("remainder: division by zero")
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0): q = -q
    return a - b * q

def builtin_modulo(args):
    if len(args) != 2: raise SchemeError("modulo: wrong number of arguments")
    a, b = args
    _check_int(a, 'modulo'); _check_int(b, 'modulo')
    if b == 0: raise SchemeError("modulo: division by zero")
    return a % b

def builtin_compare(args, op, name):
    if len(args) < 1: raise SchemeError(f"{name}: needs at least 1 argument")
    for a in args: _check_int(a, name)
    for i in range(len(args) - 1):
        if not op(args[i], args[i+1]): return FALSE
    return TRUE

def builtin_number_to_string(args):
    if len(args) < 1 or len(args) > 2:
        raise SchemeError("number->string: wrong number of arguments")
    n = args[0]
    _check_int(n, 'number->string')
    if len(args) == 2:
        radix = args[1]
        _check_int(radix, 'number->string')
        if radix not in (2, 8, 10, 16):
            raise SchemeError("number->string: invalid radix")
    else:
        radix = 10
    if n < 0:
        return '-' + _int_to_radix(-n, radix)
    return _int_to_radix(n, radix)

def _int_to_radix(n, radix):
    if n == 0: return '0'
    digits = []
    while n > 0:
        d = n % radix
        if d < 10: digits.append(chr(ord('0') + d))
        else: digits.append(chr(ord('a') + d - 10))
        n //= radix
    return ''.join(reversed(digits))

def builtin_cons(args):
    if len(args) != 2: raise SchemeError("cons: wrong number of arguments")
    return Pair(args[0], args[1])

def builtin_car(args):
    if len(args) != 1: raise SchemeError("car: wrong number of arguments")
    p = args[0]
    if not is_pair(p): raise SchemeError("car: not a pair")
    return p.car

def builtin_cdr(args):
    if len(args) != 1: raise SchemeError("cdr: wrong number of arguments")
    p = args[0]
    if not is_pair(p): raise SchemeError("cdr: not a pair")
    return p.cdr

def builtin_list(args):
    return list_to_scheme(args)

def builtin_null(args):
    if len(args) != 1: raise SchemeError("null?: wrong number of arguments")
    return TRUE if is_nil(args[0]) else FALSE

def builtin_pair(args):
    if len(args) != 1: raise SchemeError("pair?: wrong number of arguments")
    return TRUE if is_pair(args[0]) else FALSE

def builtin_list_p(args):
    if len(args) != 1: raise SchemeError("list?: wrong number of arguments")
    return TRUE if is_proper_list(args[0]) else FALSE

def builtin_length(args):
    if len(args) != 1: raise SchemeError("length: wrong number of arguments")
    l = args[0]
    n = 0
    while is_pair(l):
        n += 1; l = l.cdr
    if not is_nil(l): raise SchemeError("length: not a proper list")
    return n

def builtin_append(args):
    if len(args) == 0: return NIL
    if len(args) == 1:
        if not is_proper_list(args[0]): raise SchemeError("append: not a proper list")
        return args[0]
    for a in args[:-1]:
        if not is_proper_list(a): raise SchemeError("append: not a proper list")
    last = args[-1]
    result = last
    for a in reversed(args[:-1]):
        items = scheme_to_list(a)
        for item in reversed(items):
            result = Pair(item, result)
    return result

def builtin_reverse(args):
    if len(args) != 1: raise SchemeError("reverse: wrong number of arguments")
    l = args[0]
    if not is_proper_list(l): raise SchemeError("reverse: not a proper list")
    result = NIL
    cur = l
    while is_pair(cur):
        result = Pair(cur.car, result)
        cur = cur.cdr
    return result

def builtin_apply(args):
    if len(args) < 2: raise SchemeError("apply: wrong number of arguments")
    proc = args[0]
    if not is_procedure(proc): raise SchemeError("apply: not a procedure")
    fixed = args[1:-1]
    last = args[-1]
    if not is_proper_list(last): raise SchemeError("apply: last argument must be a proper list")
    all_args = list(fixed) + scheme_to_list(last)
    if isinstance(proc, Closure):
        return apply_closure(proc, all_args)
    return proc.func(all_args)

def builtin_eq(args):
    if len(args) != 2: raise SchemeError("eq?: wrong number of arguments")
    a, b = args
    if isinstance(a, int) and not isinstance(a, bool) and isinstance(b, int) and not isinstance(b, bool):
        return TRUE if a == b else FALSE
    if is_symbol(a) and is_symbol(b):
        return TRUE if a.name == b.name else FALSE
    if is_bool(a) and is_bool(b):
        return TRUE if a.val == b.val else FALSE
    if is_nil(a) and is_nil(b):
        return TRUE
    if isinstance(a, Unspecified) and isinstance(b, Unspecified):
        return TRUE
    return TRUE if a is b else FALSE

def builtin_equal(args):
    if len(args) != 2: raise SchemeError("equal?: wrong number of arguments")
    return TRUE if deep_equal(args[0], args[1]) else FALSE

def deep_equal(a, b):
    stack = [(a, b)]
    while stack:
        a, b = stack.pop()
        if a is b: continue
        if isinstance(a, int) and not isinstance(a, bool):
            if not (isinstance(b, int) and not isinstance(b, bool)): return False
            if a != b: return False
            continue
        if is_bool(a):
            if not is_bool(b): return False
            if a.val != b.val: return False
            continue
        if is_string(a):
            if not is_string(b): return False
            if a != b: return False
            continue
        if is_symbol(a):
            if not is_symbol(b): return False
            if a.name != b.name: return False
            continue
        if is_nil(a):
            if not is_nil(b): return False
            continue
        if isinstance(a, Unspecified):
            if not isinstance(b, Unspecified): return False
            continue
        if is_pair(a):
            if not is_pair(b): return False
            stack.append((a.cdr, b.cdr))
            stack.append((a.car, b.car))
            continue
        if is_procedure(a):
            if not is_procedure(b): return False
            if a is not b: return False
            continue
        return False
    return True

def builtin_not(args):
    if len(args) != 1: raise SchemeError("not: wrong number of arguments")
    return TRUE if not is_true(args[0]) else FALSE

def builtin_number_p(args):
    if len(args) != 1: raise SchemeError("number?: wrong number of arguments")
    return TRUE if is_int(args[0]) else FALSE

def builtin_symbol_p(args):
    if len(args) != 1: raise SchemeError("symbol?: wrong number of arguments")
    return TRUE if is_symbol(args[0]) else FALSE

def builtin_string_p(args):
    if len(args) != 1: raise SchemeError("string?: wrong number of arguments")
    return TRUE if is_string(args[0]) else FALSE

def builtin_procedure_p(args):
    if len(args) != 1: raise SchemeError("procedure?: wrong number of arguments")
    return TRUE if is_procedure(args[0]) else FALSE

def builtin_string_append(args):
    parts = []
    for a in args:
        if not is_string(a): raise SchemeError("string-append: not a string")
        parts.append(a)
    return ''.join(parts)


# ===================== Global Environment =====================

def make_global_env(output):
    env = Frame()

    def bi(name, func):
        env.vars[name] = Builtin(name, func)

    bi('+', builtin_plus)
    bi('*', builtin_times)
    bi('-', builtin_minus)
    bi('quotient', builtin_quotient)
    bi('remainder', builtin_remainder)
    bi('modulo', builtin_modulo)
    bi('=', lambda a: builtin_compare(a, lambda x, y: x == y, '='))
   