"""A Scheme subset interpreter."""
import sys

if hasattr(sys, 'set_int_max_str_digits'):
    sys.set_int_max_str_digits(0)
sys.setrecursionlimit(200000)


class SchemeError(Exception):
    def __init__(self, message, output=''):
        super().__init__(message)
        self.output = output


# === Data Types ===

class Symbol:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name

class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr

class _NilType:
    pass
NIL = _NilType()

class _UnspecType:
    pass
UNSPEC = _UnspecType()

class _Bool:
    __slots__ = ('val',)
    def __init__(self, val):
        self.val = val

TRUE = _Bool(True)
FALSE = _Bool(False)

class Closure:
    __slots__ = ('formals', 'body', 'env')
    def __init__(self, formals, body, env):
        self.formals = formals
        self.body = body
        self.env = env

class Builtin:
    __slots__ = ('func', 'name')
    def __init__(self, func, name):
        self.func = func
        self.name = name

class _UninitType:
    pass
UNINIT = _UninitType()


# === Reader ===

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
            tokens.append(('(', None))
            i += 1
        elif c == ')':
            tokens.append((')', None))
            i += 1
        elif c == "'":
            tokens.append(("'", None))
            i += 1
        elif c == '"':
            i += 1
            chars = []
            terminated = False
            while i < n:
                c = source[i]
                if c == '"':
                    i += 1
                    terminated = True
                    break
                elif c == '\\':
                    i += 1
                    if i >= n:
                        raise SchemeError("unterminated string escape")
                    ec = source[i]
                    if ec == '"':
                        chars.append('"')
                    elif ec == '\\':
                        chars.append('\\')
                    elif ec == 'n':
                        chars.append('\n')
                    else:
                        raise SchemeError(f"invalid escape: \\{ec}")
                    i += 1
                else:
                    chars.append(c)
                    i += 1
            if not terminated:
                raise SchemeError("unterminated string")
            tokens.append(('string', ''.join(chars)))
        else:
            start = i
            while i < n and source[i] not in ' \t\n\r()";\'':
                i += 1
            tok = source[start:i]
            if tok == '.':
                tokens.append(('dot', None))
            elif tok == '#t':
                tokens.append(('bool', True))
            elif tok == '#f':
                tokens.append(('bool', False))
            elif tok.startswith('#'):
                raise SchemeError(f"invalid token: {tok}")
            elif _is_int_token(tok):
                tokens.append(('int', int(tok)))
            else:
                tokens.append(('sym', tok))
    return tokens


def _parse_all(tokens):
    pos = [0]
    forms = []
    while pos[0] < len(tokens):
        if tokens[pos[0]][0] == ')':
            raise SchemeError("unexpected )")
        forms.append(_parse_expr(tokens, pos))
    return forms


def _parse_expr(tokens, pos):
    if pos[0] >= len(tokens):
        raise SchemeError("unexpected end of input")
    tt, tv = tokens[pos[0]]
    if tt == '(':
        pos[0] += 1
        return _parse_list_body(tokens, pos)
    elif tt == "'":
        pos[0] += 1
        datum = _parse_expr(tokens, pos)
        return Pair(Symbol('quote'), Pair(datum, NIL))
    elif tt == ')':
        raise SchemeError("unexpected )")
    elif tt == 'dot':
        raise SchemeError("unexpected .")
    elif tt == 'int':
        pos[0] += 1
        return tv
    elif tt == 'sym':
        pos[0] += 1
        return Symbol(tv)
    elif tt == 'bool':
        pos[0] += 1
        return TRUE if tv else FALSE
    elif tt == 'string':
        pos[0] += 1
        return tv
    raise SchemeError(f"unexpected token: {tt}")


def _parse_list_body(tokens, pos):
    items = []
    while True:
        if pos[0] >= len(tokens):
            raise SchemeError("unexpected end of input (unclosed parenthesis)")
        tt, tv = tokens[pos[0]]
        if tt == ')':
            pos[0] += 1
            result = NIL
            for item in reversed(items):
                result = Pair(item, result)
            return result
        if tt == 'dot':
            if not items:
                raise SchemeError("dot without preceding elements")
            pos[0] += 1
            if pos[0] >= len(tokens) or tokens[pos[0]][0] == ')':
                raise SchemeError("dot without following datum")
            cdr = _parse_expr(tokens, pos)
            if pos[0] >= len(tokens):
                raise SchemeError("unexpected end after dot datum")
            if tokens[pos[0]][0] != ')':
                raise SchemeError("expected ) after dot datum")
            pos[0] += 1
            result = cdr
            for item in reversed(items):
                result = Pair(item, result)
            return result
        items.append(_parse_expr(tokens, pos))


# === Environment ===

class Frame:
    __slots__ = ('vars', 'parent')
    def __init__(self, parent=None):
        self.vars = {}
        self.parent = parent


def _lookup(name, env):
    frame = env
    while frame is not None:
        if name in frame.vars:
            val = frame.vars[name]
            if isinstance(val, _UninitType):
                raise SchemeError(f"uninitialized variable: {name}")
            return val
        frame = frame.parent
    raise SchemeError(f"unbound variable: {name}")


def _set_var(name, val, env):
    frame = env
    while frame is not None:
        if name in frame.vars:
            frame.vars[name] = val
            return
        frame = frame.parent
    raise SchemeError(f"unbound variable: {name}")


def _define_var(name, val, env):
    frame = env
    while frame is not None:
        if name in frame.vars:
            frame.vars[name] = val
            return
        frame = frame.parent
    g = env
    while g.parent is not None:
        g = g.parent
    g.vars[name] = val


# === Utility ===

def _to_list(obj):
    result = []
    while isinstance(obj, Pair):
        result.append(obj.car)
        obj = obj.cdr
    if not isinstance(obj, _NilType):
        raise SchemeError("malformed form: improper list")
    return result


def _to_scheme_list(items):
    result = NIL
    for item in reversed(items):
        result = Pair(item, result)
    return result


def _is_proper_list(obj):
    while isinstance(obj, Pair):
        obj = obj.cdr
    return isinstance(obj, _NilType)


def _int_to_str(n, radix=10):
    if n == 0:
        return "0"
    neg = n < 0
    n = abs(n)
    digits = []
    while n > 0:
        digits.append("0123456789abcdef"[n % radix])
        n //= radix
    if neg:
        digits.append('-')
    return ''.join(reversed(digits))


# === Display ===

def _display_val(val, out, write_mode=False):
    if isinstance(val, int):
        out.append(_int_to_str(val, 10))
    elif val is TRUE:
        out.append("#t")
    elif val is FALSE:
        out.append("#f")
    elif isinstance(val, str):
        if write_mode:
            s = val.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
            out.append('"' + s + '"')
        else:
            out.append(val)
    elif isinstance(val, Symbol):
        out.append(val.name)
    elif isinstance(val, _NilType):
        out.append("()")
    elif isinstance(val, _UnspecType):
        out.append("")
    elif isinstance(val, Pair):
        out.append("(")
        cur = val
        first = True
        while isinstance(cur, Pair):
            if not first:
                out.append(" ")
            _display_val(cur.car, out, write_mode)
            first = False
            cur = cur.cdr
        if not isinstance(cur, _NilType):
            out.append(" . ")
            _display_val(cur, out, write_mode)
        out.append(")")
    elif isinstance(val, (Closure, Builtin)):
        out.append("#<procedure>")
    else:
        out.append(str(val))


def _write_repr(val):
    out = []
    _display_val(val, out, True)
    return ''.join(out)


# === Evaluator ===

class TailCall:
    __slots__ = ('proc', 'args')
    def __init__(self, proc, args):
        self.proc = proc
        self.args = args


SPECIAL_FORMS = frozenset(('quote', 'if', 'define', 'set!', 'begin', 'cond',
                           'and', 'or', 'lambda', 'let', 'let*', 'letrec'))


def _eval_expr(expr, env, output):
    result = _eval_tail(expr, env, output)
    return _trampoline(result, output)


def _trampoline(result, output):
    while isinstance(result, TailCall):
        proc = result.proc
        args = result.args
        if isinstance(proc, Closure):
            new_env = _make_call_env(proc, args)
            result = _eval_body_tail(proc.body, new_env, output)
        elif isinstance(proc, Builtin):
            result = proc.func(args, output)
        else:
            raise SchemeError("not a procedure")
    return result


def _eval_body_tail(body, env, output):
    if len(body) == 0:
        raise SchemeError("empty body")
    def_names = []
    for form in body:
        if _is_define(form):
            n = _define_name(form)
            if n is not None:
                def_names.append(n)
    if def_names:
        frame = Frame(parent=env)
        for n in def_names:
            frame.vars[n] = UNINIT
        env = frame
    for form in body[:-1]:
        _eval_expr(form, env, output)
    return _eval_tail(body[-1], env, output)


def _is_define(form):
    return (isinstance(form, Pair) and isinstance(form.car, Symbol)
            and form.car.name == 'define')


def _define_name(form):
    target = form.cdr.car if isinstance(form.cdr, Pair) else None
    if isinstance(target, Symbol):
        return target.name
    if isinstance(target, Pair) and isinstance(target.car, Symbol):
        return target.car.name
    return None


def _make_call_env(closure, args):
    frame = Frame(parent=closure.env)
    formals = closure.formals
    if isinstance(formals, Symbol):
        frame.vars[formals.name] = _to_scheme_list(args)
    else:
        cur = formals
        i = 0
        while isinstance(cur, Pair):
            frame.vars[cur.car.name] = args[i]
            i += 1
            cur = cur.cdr
        if isinstance(cur, Symbol):
            frame.vars[cur.name] = _to_scheme_list(args[i:])
    return frame


def _check_arity(formals, n):
    if isinstance(formals, Symbol):
        return
    required = 0
    cur = formals
    while isinstance(cur, Pair):
        required += 1
        cur = cur.cdr
    if isinstance(cur, Symbol):
        if n < required:
            raise SchemeError("too few arguments")
    elif isinstance(cur, _NilType):
        if n != required:
            raise SchemeError("wrong number of arguments")
    else:
        raise SchemeError("malformed formals")


def _eval_tail(expr, env, output):
    if isinstance(expr, int):
        return expr
    if isinstance(expr, str):
        return expr
    if isinstance(expr, _Bool):
        return expr
    if isinstance(expr, _NilType):
        raise SchemeError("cannot evaluate ()")
    if isinstance(expr, _UnspecType):
        return expr
    if isinstance(expr, Symbol):
        return _lookup(expr.name, env)
    if isinstance(expr, Pair):
        head = expr.car
        if isinstance(head, Symbol) and head.name in SPECIAL_FORMS:
            name = head.name
            if name == 'quote':
                return _handle_quote(expr, env, output)
            if name == 'if':
                return _handle_if(expr, env, output)
            if name == 'define':
                return _handle_define(expr, env, output)
            if name == 'set!':
                return _handle_set(expr, env, output)
            if name == 'begin':
                return _handle_begin(expr, env, output)
            if name == 'cond':
                return _handle_cond(expr, env, output)
            if name == 'and':
                return _handle_and(expr, env, output)
            if name == 'or':
                return _handle_or(expr, env, output)
            if name == 'lambda':
                return _handle_lambda(expr, env, output)
            if name == 'let':
                return _handle_let(expr, env, output)
            if name == 'let*':
                return _handle_letstar(expr, env, output)
            if name == 'letrec':
                return _handle_letrec(expr, env, output)
        return _apply_tail(expr, env, output)
    raise SchemeError("invalid expression")


# === Special Form Handlers ===

def _handle_quote(expr, env, output):
    if not isinstance(expr.cdr, Pair):
        raise SchemeError("malformed quote")
    return expr.cdr.car


def _handle_if(expr, env, output):
    if not isinstance(expr.cdr, Pair):
        raise SchemeError("malformed if")
    test = _eval_expr(expr.cdr.car, env, output)
    rest = expr.cdr.cdr
    if not isinstance(rest, Pair):
        raise SchemeError("malformed if")
    if test is FALSE:
        else_rest = rest.cdr
        if isinstance(else_rest, _NilType):
            return UNSPEC
        if not isinstance(else_rest, Pair):
            raise SchemeError("malformed if")
        return _eval_tail(else_rest.car, env, output)
    else:
        return _eval_tail(rest.car, env, output)


def _handle_define(expr, env, output):
    if not isinstance(expr.cdr, Pair):
        raise SchemeError("malformed define")
    target = expr.cdr.car
    body = _to_list(expr.cdr.cdr)
    if isinstance(target, Symbol):
        if len(body) != 1:
            raise SchemeError("malformed define")
        val = _eval_expr(body[0], env, output)
        _define_var(target.name, val, env)
        return UNSPEC
    elif isinstance(target, Pair):
        if not isinstance(target.car, Symbol):
            raise SchemeError("malformed define")
        name = target.car.name
        formals = target.cdr
        if len(body) == 0:
            raise SchemeError("empty body")
        closure = Closure(formals, body, env)
        _define_var(name, closure, env)
        return UNSPEC
    else:
        raise SchemeError("malformed define")


def _handle_set(expr, env, output):
    if not isinstance(expr.cdr, Pair):
        raise SchemeError("malformed set!")
    name = expr.cdr.car
    if not isinstance(name, Symbol):
        raise SchemeError("malformed set!")
    if not isinstance(expr.cdr.cdr, Pair):
        raise SchemeError("malformed set!")
    val = _eval_expr(expr.cdr.cdr.car, env, output)
    _set_var(name.name, val, env)
    return UNSPEC


def _handle_begin(expr, env, output):
    forms = _to_list(expr.cdr)
    if len(forms) == 0:
        raise SchemeError("empty begin")
    for form in forms[:-1]:
        _eval_expr(form, env, output)
    return _eval_tail(forms[-1], env, output)


def _handle_cond(expr, env, output):
    clauses = _to_list(expr.cdr)
    for clause in clauses:
        if not isinstance(clause, Pair):
            raise SchemeError("malformed cond clause")
        test = clause.car
        exprs = _to_list(clause.cdr)
        if isinstance(test, Symbol) and test.name == 'else':
            if len(exprs) == 0:
                return UNSPEC
            for e in exprs[:-1]:
                _eval_expr(e, env, output)
            return _eval_tail(exprs[-1], env, output)
        else:
            val = _eval_expr(test, env, output)
            if val is not FALSE:
                if len(exprs) == 0:
                    return val
                for e in exprs[:-1]:
                    _eval_expr(e, env, output)
                return _eval_tail(exprs[-1], env, output)
    return UNSPEC


def _handle_and(expr, env, output):
    forms = _to_list(expr.cdr)
    if len(forms) == 0:
        return TRUE
    for form in forms[:-1]:
        val = _eval_expr(form, env, output)
        if val is FALSE:
            return FALSE
    return _eval_tail(forms[-1], env, output)


def _handle_or(expr, env, output):
    forms = _to_list(expr.cdr)
    if len(forms) == 0:
        return FALSE
    for form in forms[:-1]:
        val = _eval_expr(form, env, output)
        if val is not FALSE:
            return val
    return _eval_tail(forms[-1], env, output)


def _handle_lambda(expr, env, output):
    if not isinstance(expr.cdr, Pair):
        raise SchemeError("malformed lambda")
    formals = expr.cdr.car
    body = _to_list(expr.cdr.cdr)
    if len(body) == 0:
        raise SchemeError("empty lambda body")
    return Closure(formals, body, env)


def _handle_let(expr, env, output):
    if not isinstance(expr.cdr, Pair):
        raise SchemeError("malformed let")
    first = expr.cdr.car
    if isinstance(first, Symbol):
        # Named let
        name = first.name
        bindings_list = expr.cdr.cdr
        if not isinstance(bindings_list, Pair):
            raise SchemeError("malformed let")
        bindings = _to_list(bindings_list.car)
        body = _to_list(bindings_list.cdr)
        if len(body) == 0:
            raise SchemeError("empty body")
        # Evaluate inits in outer env
        init_vals = []
        formals_syms = []
        for b in bindings:
            if not isinstance(b, Pair) or not isinstance(b.cdr, Pair):
                raise SchemeError("malformed let binding")
            if not isinstance(b.car, Symbol):
                raise SchemeError("malformed let binding")
            formals_syms.append(b.car)
            init_vals.append(_eval_expr(b.cdr.car, env, output))
        # Create frame with name bound to UNINIT
        frame = Frame(parent=env)
        frame.vars[name] = UNINIT
        # Create closure
        formals = _to_scheme_list(formals_syms)
        closure = Closure(formals, body, frame)
        frame.vars[name] = closure
        return TailCall(closure, init_vals)
    else:
        # Regular let
        bindings = _to_list(first)
        body = _to_list(expr.cdr.cdr)
        if len(body) == 0:
            raise SchemeError("empty body")
        pairs = []
        for b in bindings:
            if not isinstance(b, Pair) or not isinstance(b.cdr, Pair):
                raise SchemeError("malformed let binding")
            if not isinstance(b.car, Symbol):
                raise SchemeError("malformed let binding")
            val = _eval_expr(b.cdr.car, env, output)
            pairs.append((b.car.name, val))
        frame = Frame(parent=env)
        for n, v in pairs:
            frame.vars[n] = v
        return _eval_body_tail(body, frame, output)


def _handle_letstar(expr, env, output):
    if not isinstance(expr.cdr, Pair):
        raise SchemeError("malformed let*")
    bindings = _to_list(expr.cdr.car)
    body = _to_list(expr.cdr.cdr)
    if len(body) == 0:
        raise SchemeError("empty body")
    frame = Frame(parent=env)
    for b in bindings:
        if not isinstance(b, Pair) or not isinstance(b.cdr, Pair):
            raise SchemeError("malformed let* binding")
        if not isinstance(b.car, Symbol):
            raise SchemeError("malformed let* binding")
        val = _eval_expr(b.cdr.car, frame, output)
        frame.vars[b.car.name] = val
    return _eval_body_tail(body, frame, output)


def _handle_letrec(expr, env, output):
    if not isinstance(expr.cdr, Pair):
        raise SchemeError("malformed letrec")
    bindings = _to_list(expr.cdr.car)
    body = _to_list(expr.cdr.cdr)
    if len(body) == 0:
        raise SchemeError("empty body")
    frame = Frame(parent=env)
    for b in bindings:
        if not isinstance(b, Pair) or not isinstance(b.cdr, Pair):
            raise SchemeError("malformed letrec binding")
        if not isinstance(b.car, Symbol):
            raise SchemeError("malformed letrec binding")
        frame.vars[b.car.name] = UNINIT
    for b in bindings:
        val = _eval_expr(b.cdr.car, frame, output)
        frame.vars[b.car.name] = val
    return _eval_body_tail(body, frame, output)


# === Apply (procedure call) ===

_ORIGINAL_APPLY = None


def _apply_tail(expr, env, output):
    op = _eval_expr(expr.car, env, output)
    args = []
    cur = expr.cdr
    while isinstance(cur, Pair):
        args.append(_eval_expr(cur.car, env, output))
        cur = cur.cdr
    if not isinstance(cur, _NilType):
        raise SchemeError("dotted form used as application")

    if op is _ORIGINAL_APPLY:
        if len(args) < 2:
            raise SchemeError("apply requires at least 2 arguments")
        proc = args[0]
        rest = args[1:-1]
        last = args[-1]
        extra = _to_list(last)
        full_args = rest + extra
        if not isinstance(proc, (Closure, Builtin)):
            raise SchemeError("not a procedure")
        if isinstance(proc, Closure):
            _check_arity(proc.formals, len(full_args))
        return TailCall(proc, full_args)

    if not isinstance(op, (Closure, Builtin)):
        raise SchemeError("not a procedure")
    if isinstance(op, Closure):
        _check_arity(op.formals, len(args))
    return TailCall(op, args)


# === Builtins ===

def _make_builtin(fn, name):
    return Builtin(fn, name)


def _check_int(x, fname):
    if isinstance(x, int) and not isinstance(x, _Bool):
        return x
    raise SchemeError(f"{fname}: not a number")


def _builtin_add(args, output):
    s = 0
    for a in args:
        s += _check_int(a, '+')
    return s


def _builtin_mul(args, output):
    p = 1
    for a in args:
        p *= _check_int(a, '*')
    return p


def _builtin_sub(args, output):
    if len(args) < 1:
        raise SchemeError("-: requires at least 1 argument")
    r = _check_int(args[0], '-')
    for a in args[1:]:
        r -= _check_int(a, '-')
    return r


def _builtin_quotient(args, output):
    if len(args) != 2:
        raise SchemeError("quotient: requires 2 arguments")
    a = _check_int(args[0], 'quotient')
    b = _check_int(args[1], 'quotient')
    if b == 0:
        raise SchemeError("division by zero")
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        q = -q
    return q


def _builtin_remainder(args, output):
    if len(args) != 2:
        raise SchemeError("remainder: requires 2 arguments")
    a = _check_int(args[0], 'remainder')
    b = _check_int(args[1], 'remainder')
    if b == 0:
        raise SchemeError("division by zero")
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        q = -q
    return a - q * b


def _builtin_modulo(args, output):
    if len(args) != 2:
        raise SchemeError("modulo: requires 2 arguments")
    a = _check_int(args[0], 'modulo')
    b = _check_int(args[1], 'modulo')
    if b == 0:
        raise SchemeError("division by zero")
    return a % b


def _builtin_eq(args, output):
    if len(args) < 1:
        raise SchemeError("=: requires at least 1 argument")
    vals = [_check_int(a, '=') for a in args]
    for i in range(len(vals) - 1):
        if vals[i] != vals[i + 1]:
            return FALSE
    return TRUE


def _builtin_lt(args, output):
    if len(args) < 1:
        raise SchemeError("<: requires at least 1 argument")
    vals = [_check_int(a, '<') for a in args]
    for i in range(len(vals) - 1):
        if vals[i] >= vals[i + 1]:
            return FALSE
    return TRUE


def _builtin_gt(args, output):
    if len(args) < 1:
        raise SchemeError(">: requires at least 1 argument")
    vals = [_check_int(a, '>') for a in args]
    for i in range(len(vals) - 1):
        if vals[i] <= vals[i + 1]:
            return FALSE
    return TRUE


def _builtin_le(args, output):
    if len(args) < 1:
        raise SchemeError("<=: requires at least 1 argument")
    vals = [_check_int(a, '<=') for a in args]
    for i in range(len(vals) - 1):
        if vals[i] > vals[i + 1]:
            return FALSE
    return TRUE


def _builtin_ge(args, output):
    if len(args) < 1:
        raise SchemeError(">=: requires at least 1 argument")
    vals = [_check_int(a, '>=') for a in args]
    for i in range(len(vals) - 1):
        if vals[i] < vals[i + 1]:
            return FALSE
    return TRUE


def _builtin_number_to_string(args, output):
    if len(args) < 1 or len(args) > 2:
        raise SchemeError("number->string: wrong number of arguments")
    n = _check_int(args[0], 'number->string')
    radix = 10
    if len(args) == 2:
        radix = _check_int(args[1], 'number->string')
        if radix not in (2, 8, 10, 16):
            raise SchemeError("number->string: invalid radix")
    return _int_to_str(n, radix)


def _builtin_cons(args, output):
    if len(args) != 2:
        raise SchemeError("cons: requires 2 arguments")
    return Pair(args[0], args[1])


def _builtin_car(args, output):
    if len(args) != 1:
        raise SchemeError("car: requires 1 argument")
    p = args[0]
    if not isinstance(p, Pair):
        raise SchemeError("car: not a pair")
    return p.car


def _builtin_cdr(args, output):
    if len(args) != 1:
        raise SchemeError("cdr: requires 1 argument")
    p = args[0]
    if not isinstance(p, Pair):
        raise SchemeError("cdr: not a pair")
    return p.cdr


def _builtin_list(args, output):
    return _to_scheme_list(args)


def _builtin_null(args, output):
    if len(args) != 1:
        raise SchemeError("null?: requires 1 argument")
    return TRUE if isinstance(args[0], _NilType) else FALSE


def _builtin_pair(args, output):
    if len(args) != 1:
        raise SchemeError("pair?: requires 1 argument")
    return TRUE if isinstance(args[0], Pair) else FALSE


def _builtin_list_p(args, output):
    if len(args) != 1:
        raise SchemeError("list?: requires 1 argument")
    return TRUE if _is_proper_list(args[0]) else FALSE


def _builtin_length(args, output):
    if len(args) != 1:
        raise SchemeError("length: requires 1 argument")
    cur = args[0]
    n = 0
    while isinstance(cur, Pair):
        n += 1
        cur = cur.cdr
    if not isinstance(cur, _NilType):
        raise SchemeError("length: not a proper list")
    return n


def _builtin_append(args, output):
    if len(args) == 0:
        return NIL
    if len(args) == 1:
        if not _is_proper_list(args[0]):
            raise SchemeError("append: not a proper list")
        return args[0]
    # All but last must be proper lists
    for i in range(len(args) - 1):
        if not _is_proper_list(args[i]):
            raise SchemeError("append: not a proper list")
    # Build result
    result = args[-1]
    for i in range(len(args) - 2, -1, -1):
        items = []
        cur = args[i]
        while isinstance(cur, Pair):
            items.append(cur.car)
            cur = cur.cdr
        for item in reversed(items):
            result = Pair(item, result)
    return result


def _builtin_reverse(args, output):
    if len(args) != 1:
        raise SchemeError("reverse: requires 1 argument")
    cur = args[0]
    result = NIL
    while isinstance(cur, Pair):
        result = Pair(cur.car, result)
        cur = cur.cdr
    if not isinstance(cur, _NilType):
        raise SchemeError("reverse: not a proper list")
    return result


def _builtin_apply(args, output):
    if len(args) < 2:
        raise SchemeError("apply: requires at least 2 arguments")
    proc = args[0]
    rest = args[1:-1]
    last = args[-1]
    extra = _to_list(last)
    full_args = rest + extra
    if not isinstance(proc, (Closure, Builtin)):
        raise SchemeError("apply: not a procedure")
    if isinstance(proc, Closure):
        _check_arity(proc.formals, len(full_args))
    if isinstance(proc, Closure):
        new_env = _make_call_env(proc, full_args)
        return _eval_body_tail(proc.body, new_env, output)
    return proc.func(full_args, output)


def _eq_check(a, b):
    if a is b:
        return True
    if isinstance(a, int) and isinstance(b, int):
        return a == b
    if isinstance(a, Symbol) and isinstance(b, Symbol):
        return a.name == b.name
    return False


def _builtin_eqq(args, output):
    if len(args) != 2:
        raise SchemeError("eq?: requires 2 arguments")
    return TRUE if _eq_check(args[0], args[1]) else FALSE


def _equal_check(a, b):
    stack = [(a, b)]
    while stack:
        a, b = stack.pop()
        if a is b:
            continue
        if isinstance(a, int) and isinstance(b, int):
            if a != b:
                return False
        elif isinstance(a, _Bool) and isinstance(b, _Bool):
            if a.val != b.val:
                return False
        elif isinstance(a, str) and isinstance(b, str):
            if a != b:
                return False
        elif isinstance(a, Symbol) and isinstance(b, Symbol):
            if a.name != b.name:
                return False
        elif isinstance(a, _NilType) and isinstance(b, _NilType):
            continue
        elif isinstance(a, Pair) and isinstance(b, Pair):
            stack.append((a.cdr, b.cdr))
            stack.append((a.car, b.car))
        else:
            return False
    return True


def _builtin_equal(args, output):
    if len(args) != 2:
        raise SchemeError("equal?: requires 2 arguments")
    return TRUE if _equal_check(args[0], args[1]) else FALSE


def _builtin_not(args, output):
    if len(args) != 1:
        raise SchemeError("not: requires 1 argument")
    return TRUE if args[0] is FALSE else FALSE


def _builtin_number_p(args, output):
    if len(args) != 1:
        raise SchemeError("number?: requires 1 argument")
    x = args[0]
    return TRUE if isinstance(x, int) and not isinstance(x, _Bool) else FALSE


def _builtin_symbol_p(args, output):
    if len(args) != 1:
        raise SchemeError("symbol?: requires 1 argument")
    return TRUE if isinstance(args[0], Symbol) else FALSE


def _builtin_string_p(args, output):
    if len(args) != 1:
        raise SchemeError("string?: requires 1 argument")
    return TRUE if isinstance(args[0], str) else FALSE


def _builtin_procedure_p(args, output):
    if len(args) != 1:
        raise SchemeError("procedure?: requires 1 argument")
    return TRUE if isinstance(args[0], (Closure, Builtin)) else FALSE


def _builtin_string_append(args, output):
    parts = []
    for a in args:
        if not isinstance(a, str):
            raise SchemeError("string-append: not a string")
        parts.append(a)
    return ''.join(parts)


def _builtin_display(args, output):
    if len(args) != 1:
        raise SchemeError("display: requires 1 argument")
    _display_val(args[0], output, False)
    return UNSPEC


def _builtin_newline(args, output):
    if len(args) != 0:
        raise SchemeError("newline: requires 0 arguments")
    output.append("\n")
    return UNSPEC


def _builtin_error(args, output):
    if len(args) < 1:
        raise SchemeError("error: requires at least 1 argument")
    msg = args[0]
    if not isinstance(msg, str):
        raise SchemeError("error: first argument must be a string")
    parts = [msg]
    for irritant in args[1:]:
        parts.append(" ")
        parts.append(_write_repr(irritant))
    raise SchemeError(''.join(parts))


# === Global Environment ===

def _make_global_env():
    env = Frame()
    def add(name, fn):
        env.vars[name] = Builtin(fn, name)

    add('+', _builtin_add)
    add('*', _builtin_mul)
    add('-', _builtin_sub)
    add('quotient', _builtin_quotient)
    add('remainder', _builtin_remainder)
    add('modulo', _builtin_modulo)
    add('=', _builtin_eq)
    add('<', _builtin_lt)
    add('>', _builtin_gt)
    add('<=', _builtin_le)
    add('>=', _builtin_ge)
    add('number->string', _builtin_number_to_string)
    add('cons', _builtin_cons)
    add('car', _builtin_car)
    add('cdr', _builtin_cdr)
    add('list', _builtin_list)
    add('null?', _builtin_null)
    add('pair?', _builtin_pair)
    add('list?', _builtin_list_p)
    add('length', _builtin_length)
    add('append', _builtin_append)
    add('reverse', _builtin_reverse)
    add('apply', _builtin_apply)
    add('eq?', _builtin_eqq)
    add('equal?', _builtin_equal)
    add('not', _builtin_not)
    add('number?', _builtin_number_p)
    add('symbol?', _builtin_symbol_p)
    add('string?', _builtin_string_p)
    add('procedure?', _builtin_procedure_p)
    add('string-append', _builtin_string_append)
    add('display', _builtin_display)
    add('newline', _builtin_newline)
    add('error', _builtin_error)
    return env


# === Public API ===

def run(source):
    output = []
    try:
        tokens = _tokenize(source)
        forms = _parse_all(tokens)
        env = _make_global_env()
        global _ORIGINAL_APPLY
        _ORIGINAL_APPLY = env.vars.get('apply')
        for form in forms:
            _eval_expr(form, env, output)
        return ''.join(output)
    except SchemeError as e:
        e.output = ''.join(output)
        raise
    except RecursionError:
        raise SchemeError("stack overflow", ''.join(output))
    except Exception as e:
        raise SchemeError(str(e), ''.join(output))
