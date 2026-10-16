"""A Scheme interpreter supporting a small, precisely specified subset."""
import sys
import re

# Increase recursion limit for deep non-tail recursion
sys.setrecursionlimit(1000000)

# Handle int-to-str conversion limit in CPython 3.11+
if hasattr(sys, 'set_int_max_str_digits'):
    sys.set_int_max_str_digits(1000000)


class SchemeError(Exception):
    def __init__(self, message, output=''):
        super().__init__(message)
        self.output = output


# ─── Data Types ────────────────────────────────────────────────────────────────

class Symbol:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name
    def __repr__(self):
        return f"Symbol({self.name!r})"

class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr

class SchemeBool:
    __slots__ = ('v',)
    def __init__(self, v):
        self.v = v
    def __bool__(self):
        return self.v

TRUE = SchemeBool(True)
FALSE = SchemeBool(False)
UNSPECIFIED = object()
_UNBOUND = object()

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

class Frame:
    __slots__ = ('vars', 'parent')
    def __init__(self, parent=None):
        self.vars = {}
        self.parent = parent

class _TailCall:
    __slots__ = ('expr', 'env')
    def __init__(self, expr, env):
        self.expr = expr
        self.env = env


# ─── Reader ────────────────────────────────────────────────────────────────────

_INT_RE = re.compile(r'^[+-]?[0-9]+$')

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
            tokens.append(('(', '('))
            i += 1
        elif c == ')':
            tokens.append((')', ')'))
            i += 1
        elif c == "'":
            tokens.append(("'", "'"))
            i += 1
        elif c == '"':
            i += 1
            chars = []
            terminated = False
            while i < n:
                if source[i] == '"':
                    i += 1
                    terminated = True
                    break
                elif source[i] == '\\':
                    i += 1
                    if i >= n:
                        raise SyntaxError("unterminated string")
                    nc = source[i]
                    if nc == '"':
                        chars.append('"')
                    elif nc == '\\':
                        chars.append('\\')
                    elif nc == 'n':
                        chars.append('\n')
                    else:
                        raise SyntaxError(f"bad escape: \\{nc}")
                    i += 1
                else:
                    chars.append(source[i])
                    i += 1
            if not terminated:
                raise SyntaxError("unterminated string")
            tokens.append(('str', ''.join(chars)))
        else:
            start = i
            while i < n and source[i] not in ' \t\n\r()";\'':
                i += 1
            tokens.append(('tok', source[start:i]))
    return tokens


def _parse_atom(tok):
    if tok == '#t':
        return TRUE
    if tok == '#f':
        return FALSE
    if tok.startswith('#'):
        raise SyntaxError(f"invalid syntax: {tok}")
    if _INT_RE.match(tok):
        return int(tok)
    return Symbol(tok)


def _parse_form(tokens, pos):
    if pos[0] >= len(tokens):
        raise SyntaxError("unexpected end of input")
    ttype, tval = tokens[pos[0]]
    if ttype == '(':
        pos[0] += 1
        return _parse_list(tokens, pos)
    elif ttype == ')':
        raise SyntaxError("unexpected )")
    elif ttype == "'":
        pos[0] += 1
        datum = _parse_form(tokens, pos)
        return Pair(Symbol('quote'), Pair(datum, None))
    elif ttype == 'str':
        pos[0] += 1
        return tval
    elif ttype == 'tok':
        pos[0] += 1
        return _parse_atom(tval)
    else:
        raise SyntaxError(f"unexpected token: {tval}")


def _parse_list(tokens, pos):
    elements = []
    while pos[0] < len(tokens):
        ttype, tval = tokens[pos[0]]
        if ttype == ')':
            pos[0] += 1
            result = None
            for e in reversed(elements):
                result = Pair(e, result)
            return result
        if ttype == 'tok' and tval == '.':
            if len(elements) == 0:
                raise SyntaxError("dot with no preceding element")
            pos[0] += 1
            dot_val = _parse_form(tokens, pos)
            if pos[0] >= len(tokens) or tokens[pos[0]][0] != ')':
                raise SyntaxError("expected ) after dotted datum")
            pos[0] += 1
            result = dot_val
            for e in reversed(elements):
                result = Pair(e, result)
            return result
        elements.append(_parse_form(tokens, pos))
    raise SyntaxError("unexpected end of input (unclosed parenthesis)")


def _read_all(source):
    tokens = _tokenize(source)
    forms = []
    pos = [0]
    while pos[0] < len(tokens):
        if tokens[pos[0]][0] == ')':
            raise SyntaxError("unexpected )")
        forms.append(_parse_form(tokens, pos))
    return forms


# ─── Utility Functions ─────────────────────────────────────────────────────────

def _to_list(pair):
    result = []
    cur = pair
    while cur is not None:
        if not isinstance(cur, Pair):
            raise SchemeError("malformed form: improper list")
        result.append(cur.car)
        cur = cur.cdr
    return result


def _is_proper_list(obj):
    while isinstance(obj, Pair):
        obj = obj.cdr
    return obj is None


def _truthy(v):
    return not (v is FALSE)


def _list_to_pair(lst):
    result = None
    for item in reversed(lst):
        result = Pair(item, result)
    return result


def _is_procedure(v):
    return isinstance(v, (Closure, Builtin))


# ─── Display / Write Representations ──────────────────────────────────────────

def _display_repr(val):
    if val is None:
        return "()"
    if type(val) is int:
        return str(val)
    if isinstance(val, SchemeBool):
        return "#t" if val.v else "#f"
    if type(val) is str:
        return val
    if isinstance(val, Symbol):
        return val.name
    if isinstance(val, Pair):
        return _display_pair(val)
    if isinstance(val, (Closure, Builtin)):
        return "#<procedure>"
    if val is UNSPECIFIED:
        return ""
    return str(val)


def _display_pair(p):
    parts = []
    cur = p
    while isinstance(cur, Pair):
        parts.append(_display_repr(cur.car))
        cur = cur.cdr
    if cur is None:
        return "(" + " ".join(parts) + ")"
    else:
        return "(" + " ".join(parts) + " . " + _display_repr(cur) + ")"


def _write_repr(val):
    if val is None:
        return "()"
    if type(val) is int:
        return str(val)
    if isinstance(val, SchemeBool):
        return "#t" if val.v else "#f"
    if type(val) is str:
        return '"' + val.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'
    if isinstance(val, Symbol):
        return val.name
    if isinstance(val, Pair):
        return _write_pair(val)
    if isinstance(val, (Closure, Builtin)):
        return "#<procedure>"
    if val is UNSPECIFIED:
        return ""
    return str(val)


def _write_pair(p):
    parts = []
    cur = p
    while isinstance(cur, Pair):
        parts.append(_write_repr(cur.car))
        cur = cur.cdr
    if cur is None:
        return "(" + " ".join(parts) + ")"
    else:
        return "(" + " ".join(parts) + " . " + _write_repr(cur) + ")"


# ─── Environment ──────────────────────────────────────────────────────────────

def _lookup(name, env):
    sym_name = name.name if isinstance(name, Symbol) else name
    frame = env
    while frame is not None:
        if sym_name in frame.vars:
            val = frame.vars[sym_name]
            if val is _UNBOUND:
                raise SchemeError(f"unbound variable (not yet defined): {sym_name}")
            return val
        frame = frame.parent
    raise SchemeError(f"unbound variable: {sym_name}")


def _set_var(name, value, env):
    sym_name = name.name if isinstance(name, Symbol) else name
    frame = env
    while frame is not None:
        if sym_name in frame.vars:
            if frame.vars[sym_name] is _UNBOUND:
                raise SchemeError(f"cannot set! unbound variable: {sym_name}")
            frame.vars[sym_name] = value
            return
        frame = frame.parent
    raise SchemeError(f"unbound variable: {sym_name}")


# ─── Evaluator ────────────────────────────────────────────────────────────────

def _make_call_env(closure, args):
    frame = Frame(closure.env)
    formals = closure.formals
    if isinstance(formals, Symbol):
        frame.vars[formals.name] = _list_to_pair(args)
    elif formals is None:
        if len(args) != 0:
            raise SchemeError("too many arguments")
    elif isinstance(formals, Pair):
        cur = formals
        i = 0
        while isinstance(cur, Pair) and i < len(args):
            if not isinstance(cur.car, Symbol):
                raise SchemeError("malformed formals")
            frame.vars[cur.car.name] = args[i]
            cur = cur.cdr
            i += 1
        if isinstance(cur, Pair):
            raise SchemeError("too few arguments")
        elif cur is None:
            if i < len(args):
                raise SchemeError("too many arguments")
        else:
            if not isinstance(cur, Symbol):
                raise SchemeError("malformed formals")
            frame.vars[cur.name] = _list_to_pair(args[i:])
    else:
        raise SchemeError("malformed formals")
    return frame


def _is_define_form(form):
    return (isinstance(form, Pair) and isinstance(form.car, Symbol)
            and form.car.name == 'define')


def _get_define_name(form):
    if form.cdr is None:
        raise SchemeError("malformed define")
    target = form.cdr.car
    if isinstance(target, Symbol):
        return target
    if isinstance(target, Pair):
        if not isinstance(target.car, Symbol):
            raise SchemeError("malformed define")
        return target.car
    raise SchemeError("malformed define")


def _execute_define(form, env):
    if form.cdr is None:
        raise SchemeError("malformed define")
    target = form.cdr.car
    if isinstance(target, Symbol):
        if form.cdr.cdr is None:
            raise SchemeError("malformed define: missing expression")
        expr = form.cdr.cdr.car
        val = _eval_tramp(expr, env)
        env.vars[target.name] = val
    elif isinstance(target, Pair):
        name = target.car
        if not isinstance(name, Symbol):
            raise SchemeError("malformed define")
        formals = target.cdr
        body = _to_list(form.cdr.cdr)
        if not body:
            raise SchemeError("malformed define: empty body")
        _validate_formals(formals)
        closure = Closure(formals, body, env)
        env.vars[name.name] = closure
    else:
        raise SchemeError("malformed define")


def _validate_formals(formals):
    if formals is None:
        return
    if isinstance(formals, Symbol):
        return
    if isinstance(formals, Pair):
        cur = formals
        while isinstance(cur, Pair):
            if not isinstance(cur.car, Symbol):
                raise SchemeError("malformed formals: non-symbol")
            cur = cur.cdr
        if cur is not None and not isinstance(cur, Symbol):
            raise SchemeError("malformed formals")
        return
    raise SchemeError("malformed formals")


def _setup_body(body, env):
    """Create frame for internal definitions. Returns new env."""
    def_names = []
    for form in body:
        if _is_define_form(form):
            name = _get_define_name(form)
            def_names.append(name.name)
    if def_names:
        env = Frame(env)
        for n in def_names:
            env.vars[n] = _UNBOUND
    return env


def _execute_body(body, env):
    """Execute body forms. Returns a value or _TailCall for the last form."""
    env = _setup_body(body, env)
    for form in body[:-1]:
        if _is_define_form(form):
            _execute_define(form, env)
        else:
            _eval_tramp(form, env)
    last = body[-1]
    if _is_define_form(last):
        _execute_define(last, env)
        return UNSPECIFIED
    return _TailCall(last, env)


def _eval_tramp(expr, env):
    """Evaluate with trampoline for tail calls."""
    while True:
        result = _eval(expr, env)
        if isinstance(result, _TailCall):
            expr = result.expr
            env = result.env
        else:
            return result


def _eval(expr, env):
    """Core evaluator. Returns a value or _TailCall."""
    # Self-evaluating types
    if expr is None:
        return None
    if type(expr) is int:
        return expr
    if type(expr) is str:
        return expr
    if isinstance(expr, SchemeBool):
        return expr
    if isinstance(expr, Symbol):
        return _lookup(expr, env)

    # Must be a Pair (a form)
    if not isinstance(expr, Pair):
        raise SchemeError(f"cannot evaluate: {expr}")

    head = expr.car

    # Check for dotted form used as application
    if not isinstance(head, Symbol):
        # Non-symbol head: application, but check proper list
        if not _is_proper_list(expr):
            raise SchemeError("dotted form used as application")
        return _do_apply(expr, env)

    name = head.name

    # ─── Special Forms ─────────────────────────────────────────────────────

    if name == 'quote':
        if expr.cdr is None:
            raise SchemeError("malformed quote")
        return expr.cdr.car

    if name == 'if':
        if expr.cdr is None:
            raise SchemeError("malformed if")
        test = expr.cdr.car
        if expr.cdr.cdr is None:
            raise SchemeError("malformed if: missing then-expression")
        then_expr = expr.cdr.cdr.car
        test_val = _eval_tramp(test, env)
        if _truthy(test_val):
            return _TailCall(then_expr, env)
        if expr.cdr.cdr.cdr is not None:
            else_expr = expr.cdr.cdr.cdr.car
            return _TailCall(else_expr, env)
        return UNSPECIFIED

    if name == 'define':
        _execute_define(expr, env)
        return UNSPECIFIED

    if name == 'set!':
        if expr.cdr is None:
            raise SchemeError("malformed set!")
        var = expr.cdr.car
        if not isinstance(var, Symbol):
            raise SchemeError("malformed set!: non-symbol")
        if expr.cdr.cdr is None:
            raise SchemeError("malformed set!: missing expression")
        val = _eval_tramp(expr.cdr.cdr.car, env)
        _set_var(var, val, env)
        return UNSPECIFIED

    if name == 'begin':
        forms = _to_list(expr.cdr)
        if not forms:
            raise SchemeError("malformed begin: empty")
        for f in forms[:-1]:
            _eval_tramp(f, env)
        return _TailCall(forms[-1], env)

    if name == 'lambda':
        if expr.cdr is None:
            raise SchemeError("malformed lambda")
        formals = expr.cdr.car
        body = _to_list(expr.cdr.cdr)
        if not body:
            raise SchemeError("malformed lambda: empty body")
        _validate_formals(formals)
        return Closure(formals, body, env)

    if name == 'cond':
        return _eval_cond(expr, env)

    if name == 'and':
        exprs = _to_list(expr.cdr)
        if not exprs:
            return TRUE
        for e in exprs[:-1]:
            v = _eval_tramp(e, env)
            if not _truthy(v):
                return FALSE
        return _TailCall(exprs[-1], env)

    if name == 'or':
        exprs = _to_list(expr.cdr)
        if not exprs:
            return FALSE
        for e in exprs[:-1]:
            v = _eval_tramp(e, env)
            if _truthy(v):
                return v
        return _TailCall(exprs[-1], env)

    if name == 'let':
        return _eval_let(expr, env)

    if name == 'let*':
        return _eval_letstar(expr, env)

    if name == 'letrec':
        return _eval_letrec(expr, env)

    # ─── Application ───────────────────────────────────────────────────────

    # Check proper list
    if not _is_proper_list(expr):
        raise SchemeError("dotted form used as application")

    return _do_apply(expr, env)


def _eval_cond(expr, env):
    clauses = _to_list(expr.cdr)
    for idx, clause in enumerate(clauses):
        if not isinstance(clause, Pair):
            raise SchemeError("malformed cond clause")
        test = clause.car
        if isinstance(test, Symbol) and test.name == 'else':
            if idx != len(clauses) - 1:
                raise SchemeError("else not last in cond")
            exprs = _to_list(clause.cdr)
            if not exprs:
                return UNSPECIFIED
            for e in exprs[:-1]:
                _eval_tramp(e, env)
            return _TailCall(exprs[-1], env)
        test_val = _eval_tramp(test, env)
        if _truthy(test_val):
            exprs = _to_list(clause.cdr)
            if not exprs:
                return test_val
            for e in exprs[:-1]:
                _eval_tramp(e, env)
            return _TailCall(exprs[-1], env)
    return UNSPECIFIED


def _eval_let(expr, env):
    if expr.cdr is None:
        raise SchemeError("malformed let")
    first = expr.cdr.car
    if isinstance(first, Symbol):
        # Named let: (let name ((v init)...) body...)
        return _eval_named_let(expr, env)
    # Regular let: (let ((v init)...) body...)
    bindings = _to_list(first)
    body = _to_list(expr.cdr.cdr)
    if not body:
        raise SchemeError("malformed let: empty body")
    new_frame = Frame(env)
    for b in bindings:
        if not isinstance(b, Pair):
            raise SchemeError("malformed let binding")
        var = b.car
        if not isinstance(var, Symbol):
            raise SchemeError("malformed let binding: non-symbol")
        if b.cdr is None:
            raise SchemeError("malformed let binding: missing init")
        val = _eval_tramp(b.cdr.car, env)
        new_frame.vars[var.name] = val
    return _execute_body(body, new_frame)


def _eval_named_let(expr, env):
    name_sym = expr.cdr.car
    bindings = _to_list(expr.cdr.cdr.car)
    body = _to_list(expr.cdr.cdr.cdr)
    if not body:
        raise SchemeError("malformed named let: empty body")
    # Evaluate inits in outer scope
    inits = []
    formals_list = []
    for b in bindings:
        if not isinstance(b, Pair):
            raise SchemeError("malformed named let binding")
        var = b.car
        if not isinstance(var, Symbol):
            raise SchemeError("malformed named let binding")
        if b.cdr is None:
            raise SchemeError("malformed named let binding: missing init")
        inits.append(_eval_tramp(b.cdr.car, env))
        formals_list.append(var)
    # Create letrec-style frame
    letrec_frame = Frame(env)
    formals = _list_to_pair(formals_list) if formals_list else None
    closure = Closure(formals, body, letrec_frame)
    letrec_frame.vars[name_sym.name] = closure
    # Call the closure (tail call)
    new_env = _make_call_env(closure, inits)
    return _execute_body(body, new_env)


def _eval_letstar(expr, env):
    if expr.cdr is None:
        raise SchemeError("malformed let*")
    bindings = _to_list(expr.cdr.car)
    body = _to_list(expr.cdr.cdr)
    if not body:
        raise SchemeError("malformed let*: empty body")
    new_frame = Frame(env)
    for b in bindings:
        if not isinstance(b, Pair):
            raise SchemeError("malformed let* binding")
        var = b.car
        if not isinstance(var, Symbol):
            raise SchemeError("malformed let* binding: non-symbol")
        if b.cdr is None:
            raise SchemeError("malformed let* binding: missing init")
        val = _eval_tramp(b.cdr.car, new_frame)
        new_frame.vars[var.name] = val
    return _execute_body(body, new_frame)


def _eval_letrec(expr, env):
    if expr.cdr is None:
        raise SchemeError("malformed letrec")
    bindings = _to_list(expr.cdr.car)
    body = _to_list(expr.cdr.cdr)
    if not body:
        raise SchemeError("malformed letrec: empty body")
    new_frame = Frame(env)
    # Bind all names to _UNBOUND first
    for b in bindings:
        if not isinstance(b, Pair):
            raise SchemeError("malformed letrec binding")
        var = b.car
        if not isinstance(var, Symbol):
            raise SchemeError("malformed letrec binding: non-symbol")
        new_frame.vars[var.name] = _UNBOUND
    # Evaluate inits in order
    for b in bindings:
        var = b.car
        if b.cdr is None:
            raise SchemeError("malformed letrec binding: missing init")
        val = _eval_tramp(b.cdr.car, new_frame)
        new_frame.vars[var.name] = val
    return _execute_body(body, new_frame)


def _do_apply(expr, env):
    """Handle application: evaluate operator, operands, then apply."""
    head = expr.car
    # Evaluate operator
    proc = _eval_tramp(head, env)
    # Evaluate operands left to right
    args = []
    cur = expr.cdr
    while cur is not None:
        args.append(_eval_tramp(cur.car, env))
        cur = cur.cdr
    # Check procedure
    if not _is_procedure(proc):
        raise SchemeError(f"not a procedure: {_display_repr(proc)}")
    # Apply
    if isinstance(proc, Closure):
        new_env = _make_call_env(proc, args)
        return _execute_body(proc.body, new_env)
    else:
        # Builtin - check for apply special handling
        if proc.name == 'apply' and getattr(proc, '_is_apply_builtin', False):
            return _apply_tail(proc, args)
        return proc.func(proc, args)


def _apply_tail(proc, args):
    """Handle apply builtin with tail-call support."""
    if len(args) < 2:
        raise SchemeError("apply: requires at least 2 arguments")
    f = args[0]
    extra = args[1:-1]
    lst = args[-1]
    if not _is_proper_list(lst):
        raise SchemeError("apply: last argument must be a proper list")
    final_args = extra + _to_list(lst)
    if not _is_procedure(f):
        raise SchemeError(f"apply: not a procedure: {_display_repr(f)}")
    if isinstance(f, Closure):
        new_env = _make_call_env(f, final_args)
        return _execute_body(f.body, new_env)
    else:
        return f.func(f, final_args)


# ─── Builtins ──────────────────────────────────────────────────────────────────

def _make_global_env(output):
    env = Frame(None)

    def _check_int(v, fname, idx):
        if type(v) is not int:
            raise SchemeError(f"{fname}: argument {idx} is not an integer")

    def _check_all_ints(args, fname):
        for i, a in enumerate(args):
            _check_int(a, fname, i)

    # ── Arithmetic ──

    def bi_plus(b, args):
        _check_all_ints(args, '+')
        return sum(args)

    def bi_times(b, args):
        _check_all_ints(args, '*')
        r = 1
        for x in args:
            r *= x
        return r

    def bi_minus(b, args):
        if len(args) < 1:
            raise SchemeError("-: requires at least 1 argument")
        _check_all_ints(args, '-')
        if len(args) == 1:
            return -args[0]
        r = args[0]
        for x in args[1:]:
            r -= x
        return r

    def _quotient(a, b):
        q = abs(a) // abs(b)
        if (a < 0) ^ (b < 0):
            q = -q
        return q

    def bi_quotient(b, args):
        if len(args) != 2:
            raise SchemeError("quotient: requires exactly 2 arguments")
        _check_all_ints(args, 'quotient')
        if args[1] == 0:
            raise SchemeError("quotient: division by zero")
        return _quotient(args[0], args[1])

    def bi_remainder(b, args):
        if len(args) != 2:
            raise SchemeError("remainder: requires exactly 2 arguments")
        _check_all_ints(args, 'remainder')
        if args[1] == 0:
            raise SchemeError("remainder: division by zero")
        return args[0] - _quotient(args[0], args[1]) * args[1]

    def bi_modulo(b, args):
        if len(args) != 2:
            raise SchemeError("modulo: requires exactly 2 arguments")
        _check_all_ints(args, 'modulo')
        if args[1] == 0:
            raise SchemeError("modulo: division by zero")
        return args[0] % args[1]

    def _make_cmp(op_name, cmp_fn):
        def bi(b, args):
            if len(args) < 1:
                raise SchemeError(f"{op_name}: requires at least 1 argument")
            _check_all_ints(args, op_name)
            for i in range(len(args) - 1):
                if not cmp_fn(args[i], args[i + 1]):
                    return FALSE
            return TRUE
        return bi

    # ── Number->String ──

    def _int_to_str_radix(n, radix):
        if n == 0:
            return "0"
        neg = n < 0
        n = abs(n)
        digits = []
        while n > 0:
            digits.append(n % radix)
            n //= radix
        chars = []
        for d in reversed(digits):
            if d < 10:
                chars.append(chr(ord('0') + d))
            else:
                chars.append(chr(ord('a') + d - 10))
        s = ''.join(chars)
        if neg:
            s = '-' + s
        return s

    def bi_number_to_string(b, args):
        if len(args) < 1 or len(args) > 2:
            raise SchemeError("number->string: wrong number of arguments")
        _check_int(args[0], 'number->string', 0)
        radix = 10
        if len(args) == 2:
            _check_int(args[1], 'number->string', 1)
            radix = args[1]
            if radix not in (2, 8, 10, 16):
                raise SchemeError("number->string: invalid radix")
        return _int_to_str_radix(args[0], radix)

    # ── Pairs and Lists ──

    def bi_cons(b, args):
        if len(args) != 2:
            raise SchemeError("cons: requires exactly 2 arguments")
        return Pair(args[0], args[1])

    def bi_car(b, args):
        if len(args) != 1:
            raise SchemeError("car: requires exactly 1 argument")
        if not isinstance(args[0], Pair):
            raise SchemeError("car: not a pair")
        return args[0].car

    def bi_cdr(b, args):
        if len(args) != 1:
            raise SchemeError("cdr: requires exactly 1 argument")
        if not isinstance(args[0], Pair):
            raise SchemeError("cdr: not a pair")
        return args[0].cdr

    def bi_list(b, args):
        return _list_to_pair(args)

    def bi_null(b, args):
        if len(args) != 1:
            raise SchemeError("null?: requires exactly 1 argument")
        return TRUE if args[0] is None else FALSE

    def bi_pair(b, args):
        if len(args) != 1:
            raise SchemeError("pair?: requires exactly 1 argument")
        return TRUE if isinstance(args[0], Pair) else FALSE

    def bi_listp(b, args):
        if len(args) != 1:
            raise SchemeError("list?: requires exactly 1 argument")
        return TRUE if _is_proper_list(args[0]) else FALSE

    def bi_length(b, args):
        if len(args) != 1:
            raise SchemeError("length: requires exactly 1 argument")
        cur = args[0]
        n = 0
        while isinstance(cur, Pair):
            n += 1
            cur = cur.cdr
        if cur is not None:
            raise SchemeError("length: not a proper list")
        return n

    def bi_append(b, args):
        if len(args) == 0:
            return None
        # All but last must be proper lists
        for i in range(len(args) - 1):
            if not _is_proper_list(args[i]):
                raise SchemeError("append: argument is not a proper list")
        # Build result: copy all but last, share last
        if len(args) == 1:
            return args[0]
        # Collect all elements from all but last
        elements = []
        for i in range(len(args) - 1):
            cur = args[i]
            while isinstance(cur, Pair):
                elements.append(cur.car)
                cur = cur.cdr
        tail = args[-1]
        result = tail
        for e in reversed(elements):
            result = Pair(e, result)
        return result

    def bi_reverse(b, args):
        if len(args) != 1:
            raise SchemeError("reverse: requires exactly 1 argument")
        cur = args[0]
        result = None
        while isinstance(cur, Pair):
            result = Pair(cur.car, result)
            cur = cur.cdr
        if cur is not None:
            raise SchemeError("reverse: not a proper list")
        return result

    # apply is handled specially in _do_apply, but also available as a value
    def bi_apply(b, args):
        if len(args) < 2:
            raise SchemeError("apply: requires at least 2 arguments")
        f = args[0]
        extra = args[1:-1]
        lst = args[-1]
        if not _is_proper_list(lst):
            raise SchemeError("apply: last argument must be a proper list")
        final_args = extra + _to_list(lst)
        if not _is_procedure(f):
            raise SchemeError(f"apply: not a procedure: {_display_repr(f)}")
        if isinstance(f, Closure):
            new_env = _make_call_env(f, final_args)
            return _eval_tramp(f.body[-1], _setup_body(f.body, new_env)) if False else _eval_tramp(
                f.body[-1], _setup_body(f.body, new_env))
        else:
            return f.func(f, final_args)

    # Fix bi_apply to properly handle closures
    def bi_apply(b, args):
        if len(args) < 2:
            raise SchemeError("apply: requires at least 2 arguments")
        f = args[0]
        extra = args[1:-1]
        lst = args[-1]
        if not _is_proper_list(lst):
            raise SchemeError("apply: last argument must be a proper list")
        final_args = extra + _to_list(lst)
        if not _is_procedure(f):
            raise SchemeError(f"apply: not a procedure: {_display_repr(f)}")
        if isinstance(f, Closure):
            new_env = _make_call_env(f, final_args)
            body = f.body
            env2 = _setup_body(body, new_env)
            for form in body[:-1]:
                if _is_define_form(form):
                    _execute_define(form, env2)
                else:
                    _eval_tramp(form, env2)
            last = body[-1]
            if _is_define_form(last):
                _execute_define(last, env2)
                return UNSPECIFIED
            return _eval_tramp(last, env2)
        else:
            return f.func(f, final_args)

    # ── Equality and Predicates ──

    def bi_eq(b, args):
        if len(args) != 2:
            raise SchemeError("eq?: requires exactly 2 arguments")
        a, b_ = args[0], args[1]
        if a is b_:
            return TRUE
        if type(a) is int and type(b_) is int:
            return TRUE if a == b_ else FALSE
        if isinstance(a, SchemeBool) and isinstance(b_, SchemeBool):
            return TRUE if a.v == b_.v else FALSE
        if a is None and b_ is None:
            return TRUE
        return FALSE

    def bi_equal(b, args):
        if len(args) != 2:
            raise SchemeError("equal?: requires exactly 2 arguments")
        return TRUE if _equal(args[0], args[1]) else FALSE

    def _equal(a, b):
        if a is b:
            return True
        if isinstance(a, Pair) and isinstance(b, Pair):
            # Iterative on cdr to handle long lists
            while isinstance(a, Pair) and isinstance(b, Pair):
                if not _equal(a.car, b.car):
                    return False
                a = a.cdr
                b = b.cdr
            return a is b
        if type(a) is str and type(b) is str:
            return a == b
        if type(a) is int and type(b) is int:
            return a == b
        if isinstance(a, SchemeBool) and isinstance(b, SchemeBool):
            return a.v == b.v
        if isinstance(a, Symbol) and isinstance(b, Symbol):
            return a.name == b.name
        return False

    def bi_not(b, args):
        if len(args) != 1:
            raise SchemeError("not: requires exactly 1 argument")
        return TRUE if args[0] is FALSE else FALSE

    def bi_number(b, args):
        if len(args) != 1:
            raise SchemeError("number?: requires exactly 1 argument")
        return TRUE if type(args[0]) is int else FALSE

    def bi_symbol(b, args):
        if len(args) != 1:
            raise SchemeError("symbol?: requires exactly 1 argument")
        return TRUE if isinstance(args[0], Symbol) else FALSE

    def bi_string(b, args):
        if len(args) != 1:
            raise SchemeError("string?: requires exactly 1 argument")
        return TRUE if type(args[0]) is str else FALSE

    def bi_procedure(b, args):
        if len(args) != 1:
            raise SchemeError("procedure?: requires exactly 1 argument")
        return TRUE if _is_procedure(args[0]) else FALSE

    def bi_string_append(b, args):
        for i, a in enumerate(args):
            if type(a) is not str:
                raise SchemeError(f"string-append: argument {i} is not a string")
        return ''.join(args)

    # ── Output and Errors ──

    def bi_display(b, args):
        if len(args) != 1:
            raise SchemeError("display: requires exactly 1 argument")
        output.append(_display_repr(args[0]))
        return UNSPECIFIED

    def bi_newline(b, args):
        if len(args) != 0:
            raise SchemeError("newline: requires 0 arguments")
        output.append("\n")
        return UNSPECIFIED

    def bi_error(b, args):
        if len(args) < 1:
            raise SchemeError("error: requires at least 1 argument")
        msg = args[0]
        parts = []
        if type(msg) is str:
            parts.append(msg)
        else:
            parts.append(_write_repr(msg))
        for irritant in args[1:]:
            parts.append(" ")
            parts.append(_write_repr(irritant))
        raise SchemeError(''.join(parts))

    # ── Register builtins ──

    env.vars['+'] = Builtin(bi_plus, '+')
    env.vars['*'] = Builtin(bi_times, '*')
    env.vars['-'] = Builtin(bi_minus, '-')
    env.vars['quotient'] = Builtin(bi_quotient, 'quotient')
    env.vars['remainder'] = Builtin(bi_remainder, 'remainder')
    env.vars['modulo'] = Builtin(bi_modulo, 'modulo')
    env.vars['='] = Builtin(_make_cmp('=', lambda a, b: a == b), '=')
    env.vars['<'] = Builtin(_make_cmp('<', lambda a, b: a < b), '<')
    env.vars['>'] = Builtin(_make_cmp('>', lambda a, b: a > b), '>')
    env.vars['<='] = Builtin(_make_cmp('<=', lambda a, b: a <= b), '<=')
    env.vars['>='] = Builtin(_make_cmp('>=', lambda a, b: a >= b), '>=')
    env.vars['number->string'] = Builtin(bi_number_to_string, 'number->string')
    env.vars['cons'] = Builtin(bi_cons, 'cons')
    env.vars['car'] = Builtin(bi_car, 'car')
    env.vars['cdr'] = Builtin(bi_cdr, 'cdr')
    env.vars['list'] = Builtin(bi_list, 'list')
    env.vars['null?'] = Builtin(bi_null, 'null?')
    env.vars['pair?'] = Builtin(bi_pair, 'pair?')
    env.vars['list?'] = Builtin(bi_listp, 'list?')
    env.vars['length'] = Builtin(bi_length, 'length')
    env.vars['append'] = Builtin(bi_append, 'append')
    env.vars['reverse'] = Builtin(bi_reverse, 'reverse')
    apply_bi = Builtin(bi_apply, 'apply')
    apply_bi._is_apply_builtin = True
    env.vars['apply'] = apply_bi
    env.vars['eq?'] = Builtin(bi_eq, 'eq?')
    env.vars['equal?'] = Builtin(bi_equal, 'equal?')
    env.vars['not'] = Builtin(bi_not, 'not')
    env.vars['number?'] = Builtin(bi_number, 'number?')
    env.vars['symbol?'] = Builtin(bi_symbol, 'symbol?')
    env.vars['string?'] = Builtin(bi_string, 'string?')
    env.vars['procedure?'] = Builtin(bi_procedure, 'procedure?')
    env.vars['string-append'] = Builtin(bi_string_append, 'string-append')
    env.vars['display'] = Builtin(bi_display, 'display')
    env.vars['newline'] = Builtin(bi_newline, 'newline')
    env.vars['error'] = Builtin(bi_error, 'error')

    return env


# ─── Public API ────────────────────────────────────────────────────────────────

def run(source):
    output = []
    try:
        forms = _read_all(source)
    except SyntaxError as e:
        raise SchemeError(str(e), '') from None
    except Exception as e:
        raise SchemeError(str(e), '') from None

    env = _make_global_env(output)

    for form in forms:
        try:
            _eval_tramp(form, env)
        except SchemeError as e:
            e.output = ''.join(output)
            raise
        except RecursionError:
            raise SchemeError('stack overflow', ''.join(output)) from None
        except Exception as e:
            raise SchemeError(str(e), ''.join(output)) from None

    return ''.join(output)
