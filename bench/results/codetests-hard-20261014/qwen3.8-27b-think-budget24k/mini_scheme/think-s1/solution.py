import sys
import re

try:
    sys.set_int_max_str_digits(0)
except AttributeError:
    pass

sys.setrecursionlimit(300000)


class SchemeError(Exception):
    def __init__(self, msg, output=''):
        super().__init__(msg)
        self.output = output


# === Data Types ===

class SchemeBool:
    __slots__ = ('val',)
    def __init__(self, val):
        self.val = val

TRUE = SchemeBool(True)
FALSE = SchemeBool(False)

class Symbol:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name

class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr

class EmptyList:
    pass

EMPTY_LIST = EmptyList()

class Unspecified:
    pass

UNSPECIFIED = Unspecified()
UNINITIALIZED = object()

class Closure:
    __slots__ = ('params', 'body', 'defining_env')
    def __init__(self, params, body, defining_env):
        self.params = params
        self.body = body
        self.defining_env = defining_env

class BuiltinProcedure:
    __slots__ = ('name', 'func')
    def __init__(self, name, func):
        self.name = name
        self.func = func


# === Type Predicates ===

def _is_int(x):
    return isinstance(x, int)

def _is_bool(x):
    return isinstance(x, SchemeBool)

def _is_symbol(x):
    return isinstance(x, Symbol)

def _is_string(x):
    return isinstance(x, str)

def _is_pair(x):
    return isinstance(x, Pair)

def _is_empty(x):
    return isinstance(x, EmptyList)

def _is_proc(x):
    return isinstance(x, (Closure, BuiltinProcedure))

def _is_true(x):
    return x is not FALSE


# === List Helpers ===

def _make_list(elems):
    result = EMPTY_LIST
    for e in reversed(elems):
        result = Pair(e, result)
    return result

def _as_list(p):
    result = []
    cur = p
    while isinstance(cur, Pair):
        result.append(cur.car)
        cur = cur.cdr
    if not isinstance(cur, EmptyList):
        raise SchemeError("expected a proper list")
    return result

def _is_proper_list(x):
    while isinstance(x, Pair):
        x = x.cdr
    return isinstance(x, EmptyList)

def _car(x):
    if not isinstance(x, Pair):
        raise SchemeError("car: argument is not a pair")
    return x.car

def _cdr(x):
    if not isinstance(x, Pair):
        raise SchemeError("cdr: argument is not a pair")
    return x.cdr

def _cadr(x):
    return _car(_cdr(x))

def _caddr(x):
    return _car(_cdr(_cdr(x)))

def _cddr(x):
    return _cdr(_cdr(x))


# === Environment ===

class Env:
    __slots__ = ('bindings', 'parent')
    def __init__(self, bindings, parent=None):
        self.bindings = bindings
        self.parent = parent

def _lookup(env, sym):
    e = env
    while e is not None:
        if sym.name in e.bindings:
            v = e.bindings[sym.name]
            if v is UNINITIALIZED:
                raise SchemeError(f"unbound variable: {sym.name}")
            return v
        e = e.parent
    raise SchemeError(f"unbound variable: {sym.name}")

def _set_var(env, sym, val):
    e = env
    while e is not None:
        if sym.name in e.bindings:
            e.bindings[sym.name] = val
            return
        e = e.parent
    raise SchemeError(f"set!: unbound variable: {sym.name}")


# === Reader ===

def _skip_ws(src, pos):
    n = len(src)
    while pos < n:
        c = src[pos]
        if c in ' \t\n\r':
            pos += 1
        elif c == ';':
            while pos < n and src[pos] != '\n':
                pos += 1
        else:
            break
    return pos

def _read_all(source):
    pos = 0
    n = len(source)
    forms = []
    while True:
        pos = _skip_ws(source, pos)
        if pos >= n:
            break
        form, pos = _read_one(source, pos)
        forms.append(form)
    return forms

def _read_one(src, pos):
    n = len(src)
    if pos >= n:
        raise SchemeError("unexpected end of input")
    c = src[pos]
    if c == '(':
        return _read_list(src, pos)
    if c == ')':
        raise SchemeError("unexpected )")
    if c == "'":
        pos += 1
        pos = _skip_ws(src, pos)
        if pos >= n:
            raise SchemeError("unterminated quote")
        datum, pos = _read_one(src, pos)
        return (Symbol('quote'), Pair(datum, EMPTY_LIST)), pos
    if c == '"':
        return _read_string(src, pos)
    start = pos
    while pos < n and src[pos] not in ' \t\n\r()";\'':
        pos += 1
    token = src[start:pos]
    if not token:
        raise SchemeError("empty token")
    return (_read_token(token), pos)

def _read_token(tok):
    if tok == '#t':
        return TRUE
    if tok == '#f':
        return FALSE
    if tok.startswith('#'):
        raise SchemeError(f"invalid token: {tok}")
    if re.fullmatch(r'[+-]?[0-9]+', tok):
        return int(tok)
    return Symbol(tok)

def _read_string(src, pos):
    pos += 1
    n = len(src)
    chars = []
    while pos < n:
        c = src[pos]
        if c == '"':
            return (''.join(chars), pos + 1)
        elif c == '\\':
            if pos + 1 >= n:
                raise SchemeError("unterminated string escape")
            nc = src[pos + 1]
            if nc == '"':
                chars.append('"')
                pos += 2
            elif nc == '\\':
                chars.append('\\')
                pos += 2
            elif nc == 'n':
                chars.append('\n')
                pos += 2
            else:
                raise SchemeError(f"invalid escape: \\{nc}")
        else:
            chars.append(c)
            pos += 1
    raise SchemeError("unterminated string")

def _read_list(src, pos):
    pos += 1
    n = len(src)
    elems = []
    while True:
        pos = _skip_ws(src, pos)
        if pos >= n:
            raise SchemeError("unterminated list")
        c = src[pos]
        if c == ')':
            return _make_list(elems), pos + 1
        if c == '.':
            start = pos
            while pos < n and src[pos] not in ' \t\n\r()";\'':
                pos += 1
            tok = src[start:pos]
            if tok != '.':
                elems.append(Symbol(tok))
                continue
            if not elems:
                raise SchemeError("dot must be preceded by at least one element")
            pos = _skip_ws(src, pos)
            if pos >= n:
                raise SchemeError("unterminated dotted list")
            last, pos = _read_one(src, pos)
            pos = _skip_ws(src, pos)
            if pos >= n or src[pos] != ')':
                raise SchemeError("dotted list must end with )")
            pos += 1
            result = last
            for e in reversed(elems):
                result = Pair(e, result)
            return result, pos
        elem, pos = _read_one(src, pos)
        elems.append(elem)


# === Text Representation ===

def _display_val(v):
    if isinstance(v, int):
        return _int_to_str(v, 10)
    if isinstance(v, SchemeBool):
        return '#t' if v.val else '#f'
    if isinstance(v, str):
        return v
    if isinstance(v, Symbol):
        return v.name
    if isinstance(v, EmptyList):
        return '()'
    if isinstance(v, (Closure, BuiltinProcedure)):
        return '#<procedure>'
    if v is UNSPECIFIED:
        return ''
    if isinstance(v, Pair):
        return _display_pair(v)
    return ''

def _display_pair(p):
    parts = []
    cur = p
    while isinstance(cur, Pair):
        parts.append(_display_val(cur.car))
        cur = cur.cdr
    if isinstance(cur, EmptyList):
        return '(' + ' '.join(parts) + ')'
    else:
        if parts:
            return '(' + ' '.join(parts) + ' . ' + _display_val(cur) + ')'
        return '(' + _display_val(p.car) + ' . ' + _display_val(p.cdr) + ')'

def _write_val(v):
    if isinstance(v, str):
        return '"' + _escape_str(v) + '"'
    if isinstance(v, Pair):
        return _write_pair(v)
    return _display_val(v)

def _write_pair(p):
    parts = []
    cur = p
    while isinstance(cur, Pair):
        parts.append(_write_val(cur.car))
        cur = cur.cdr
    if isinstance(cur, EmptyList):
        return '(' + ' '.join(parts) + ')'
    else:
        if parts:
            return '(' + ' '.join(parts) + ' . ' + _write_val(cur) + ')'
        return '(' + _write_val(p.car) + ' . ' + _write_val(p.cdr) + ')'

def _escape_str(s):
    out = []
    for c in s:
        if c == '"':
            out.append('\\"')
        elif c == '\\':
            out.append('\\\\')
        elif c == '\n':
            out.append('\\n')
        else:
            out.append(c)
    return ''.join(out)

def _int_to_str(n, radix):
    if n == 0:
        return '0'
    neg = n < 0
    n = abs(n)
    digits = '0123456789abcdef'
    res = []
    while n > 0:
        res.append(digits[n % radix])
        n //= radix
    if neg:
        res.append('-')
    return ''.join(reversed(res))


# === Equality ===

def _eq_impl(a, b):
    if _is_symbol(a) and _is_symbol(b):
        return a.name == b.name
    if _is_int(a) and _is_int(b):
        return a == b
    if _is_bool(a) and _is_bool(b):
        return a.val == b.val
    if _is_empty(a) and _is_empty(b):
        return True
    return a is b

def _equal_impl(a, b):
    stack = [(a, b)]
    while stack:
        a, b = stack.pop()
        ta = _type_tag(a)
        tb = _type_tag(b)
        if ta != tb:
            return False
        if ta == 'int':
            if a != b:
                return False
        elif ta == 'bool':
            if a.val != b.val:
                return False
        elif ta == 'symbol':
            if a.name != b.name:
                return False
        elif ta == 'string':
            if a != b:
                return False
        elif ta == 'pair':
            stack.append((a.cdr, b.cdr))
            stack.append((a.car, b.car))
        elif ta == 'proc':
            if a is not b:
                return False
        elif ta == 'unspec':
            if a is not b:
                return False
    return True

def _type_tag(x):
    if isinstance(x, int):
        return 'int'
    if isinstance(x, SchemeBool):
        return 'bool'
    if isinstance(x, Symbol):
        return 'symbol'
    if isinstance(x, str):
        return 'string'
    if isinstance(x, Pair):
        return 'pair'
    if isinstance(x, EmptyList):
        return 'empty'
    if isinstance(x, (Closure, BuiltinProcedure)):
        return 'proc'
    if x is UNSPECIFIED:
        return 'unspec'
    return 'other'


# === Builtin Helpers ===

def _check_ints(args):
    for a in args:
        if not _is_int(a):
            raise SchemeError("expected integer argument")

def _check_ints_at_least(args, n):
    for a in args:
        if not _is_int(a):
            raise SchemeError("expected integer argument")

def _list_length(lst):
    if not _is_proper_list(lst):
        raise SchemeError("length: argument is not a proper list")
    count = 0
    cur = lst
    while isinstance(cur, Pair):
        count += 1
        cur = cur.cdr
    return count

def _list_reverse(lst):
    if not _is_proper_list(lst):
        raise SchemeError("reverse: argument is not a proper list")
    result = EMPTY_LIST
    cur = lst
    while isinstance(cur, Pair):
        result = Pair(cur.car, result)
        cur = cur.cdr
    return result

def _list_append(args):
    if not args:
        return EMPTY_LIST
    for lst in args[:-1]:
        if not _is_proper_list(lst):
            raise SchemeError("append: argument is not a proper list")
    if len(args) == 1:
        return args[0]
    result = args[-1]
    for i in range(len(args) - 2, -1, -1):
        elems = []
        cur = args[i]
        while isinstance(cur, Pair):
            elems.append(cur.car)
            cur = cur.cdr
        for e in reversed(elems):
            result = Pair(e, result)
    return result


# === Parameter Binding ===

def _bind_params(closure, args):
    """Create a new env for a closure call. Returns (env, body_with_internal_defines_setup)."""
    bindings = {}
    params = closure.params
    if isinstance(params, Symbol):
        bindings[params.name] = _make_list(args)
    elif isinstance(params, Pair):
        # Could be dotted or proper list of symbols
        # Walk the params
        plist = []
        rest_sym = None
        cur = params
        while isinstance(cur, Pair):
            p = cur.car
            if not _is_symbol(p):
                raise SchemeError("malformed formals")
            plist.append(p)
            cur = cur.cdr
        if isinstance(cur, Symbol):
            rest_sym = cur
        elif not isinstance(cur, EmptyList):
            raise SchemeError("malformed formals")
        
        if rest_sym is not None:
            if len(args) < len(plist):
                raise SchemeError("wrong number of arguments")
            for i, p in enumerate(plist):
                bindings[p.name] = args[i]
            bindings[rest_sym.name] = _make_list(args[len(plist):])
        else:
            if len(args) != len(plist):
                raise SchemeError("wrong number of arguments")
            for i, p in enumerate(plist):
                bindings[p.name] = args[i]
    else:
        # EMPTY_LIST - zero params
        if args:
            raise SchemeError("wrong number of arguments")
    
    # Add internal defines from body
    for form in closure.body:
        if _is_pair(form) and _is_proper_list(form):
            head = form.car
            if _is_symbol(head) and head.name == 'define':
                dname = _extract_define_name(form)
                if dname not in bindings:
                    bindings[dname] = UNINITIALIZED
    
    return Env(bindings, closure.defining_env)


def _extract_define_name(form):
    """Extract the name from a (define ...) form. form is a proper list."""
    elems = _as_list(form)
    if len(elems) < 2:
        raise SchemeError("malformed define")
    second = elems[1]
    if _is_pair(second):
        # (define (name . formals) body...)
        if not _is_proper_list(second):
            raise SchemeError("malformed define")
        name = second.car
        if not _is_symbol(name):
            raise SchemeError("define: name must be a symbol")
        return name.name
    elif _is_symbol(second):
        return second.name
    else:
        raise SchemeError("define: name must be a symbol")


def _setup_body_env(body, parent_env):
    """Create env for a body, pre-binding internal define names."""
    bindings = {}
    for form in body:
        if _is_pair(form) and _is_proper_list(form):
            head = form.car
            if _is_symbol(head) and head.name == 'define':
                try:
                    dname = _extract_define_name(form)
                    if dname not in bindings:
                        bindings[dname] = UNINITIALIZED
                except SchemeError:
                    pass
    return Env(bindings, parent_env)


# === Evaluator ===

def _eval(expr, env, output):
    """Evaluate in non-tail position."""
    if isinstance(expr, int):
        return expr
    if isinstance(expr, SchemeBool):
        return expr
    if isinstance(expr, str):
        return expr
    if isinstance(expr, Symbol):
        return _lookup(env, expr)
    if isinstance(expr, EmptyList):
        raise SchemeError("invalid expression: ()")
    if isinstance(expr, Pair):
        if not _is_proper_list(expr):
            raise SchemeError("dotted form used as application")
        head = expr.car
        if _is_symbol(head):
            name = head.name
            if name == 'quote':
                return _eval_quote(expr)
            if name == 'lambda':
                return _eval_lambda(expr)
            if name == 'if':
                return _eval_if(expr, env, output)
            if name == 'define':
                return _eval_define(expr, env, output)
            if name == 'set!':
                return _eval_set(expr, env, output)
            if name == 'begin':
                return _eval_begin(expr, env, output)
            if name == 'cond':
                return _eval_cond(expr, env, output)
            if name == 'and':
                return _eval_and(expr, env, output)
            if name == 'or':
                return _eval_or(expr, env, output)
            if name == 'let':
                return _eval_let(expr, env, output)
            if name == 'let*':
                return _eval_letstar(expr, env, output)
            if name == 'letrec':
                return _eval_letrec(expr, env, output)
            if name == 'apply':
                return _eval_apply(expr, env, output)
        # Application
        return _eval_application(expr, env, output)
    raise SchemeError("invalid expression")


def _eval_tail(expr, env, output):
    """Evaluate in tail position using a trampoline loop."""
    body_forms = None
    body_idx = 0
    
    while True:
        if body_forms is not None:
            if body_idx < len(body_forms) - 1:
                _eval(body_forms[body_idx], env, output)
                body_idx += 1
                continue
            else:
                expr = body_forms[body_idx]
                body_forms = None
        
        # Evaluate expr in tail position
        if isinstance(expr, int):
            return expr
        if isinstance(expr, SchemeBool):
            return expr
        if isinstance(expr, str):
            return expr
        if isinstance(expr, Symbol):
            return _lookup(env, expr)
        if isinstance(expr, EmptyList):
            raise SchemeError("invalid expression: ()")
        if not isinstance(expr, Pair):
            raise SchemeError("invalid expression")
        
        if not _is_proper_list(expr):
            raise SchemeError("dotted form used as application")
        
        head = expr.car
        if _is_symbol(head):
            name = head.name
            if name == 'quote':
                return _eval_quote(expr)
            if name == 'lambda':
                return _eval_lambda(expr)
            if name == 'if':
                test = _eval(_cadr(expr), env, output)
                if _is_true(test):
                    expr = _caddr(expr)
                    continue
                else:
                    elems = _as_list(expr)
                    if len(elems) >= 4:
                        expr = elems[3]
                        continue
                    else:
                        return UNSPECIFIED
            if name == 'define':
                _eval_define(expr, env, output)
                return UNSPECIFIED
            if name == 'set!':
                _eval_set(expr, env, output)
                return UNSPECIFIED
            if name == 'begin':
                forms = _as_list(_cdr(expr))
                if not forms:
                    raise SchemeError("begin: empty body")
                for f in forms[:-1]:
                    _eval(f, env, output)
                expr = forms[-1]
                continue
            if name == 'cond':
                clauses = _as_list(_cdr(expr))
                handled = False
                for i, clause in enumerate(clauses):
                    if not _is_pair(clause) or not _is_proper_list(clause) or _is_empty(clause):
                        raise SchemeError("malformed cond clause")
                    test = clause.car
                    if _is_symbol(test) and test.name == 'else':
                        if i != len(clauses) - 1:
                            raise SchemeError("else must be last clause")
                        body = _as_list(_cdr(clause))
                        if not body:
                            raise SchemeError("else clause must have expressions")
                        for e in body[:-1]:
                            _eval(e, env, output)
                        expr = body[-1]
                        handled = True
                        break
                    else:
                        val = _eval(test, env, output)
                        if _is_true(val):
                            body = _as_list(_cdr(clause))
                            if not body:
                                return val
                            for e in body[:-1]:
                                _eval(e, env, output)
                            expr = body[-1]
                            handled = True
                            break
                if not handled:
                    return UNSPECIFIED
                continue
            if name == 'and':
                exprs = _as_list(_cdr(expr))
                if not exprs:
                    return TRUE
                for i, e in enumerate(exprs):
                    if i < len(exprs) - 1:
                        val = _eval(e, env, output)
                        if val is FALSE:
                            return FALSE
                    else:
                        expr = e
                        break
                continue
            if name == 'or':
                exprs = _as_list(_cdr(expr))
                if not exprs:
                    return FALSE
                for i, e in enumerate(exprs):
                    if i < len(exprs) - 1:
                        val = _eval(e, env, output)
                        if _is_true(val):
                            return val
                    else:
                        expr = e
                        break
                continue
            if name == 'let':
                second = _cadr(expr)
                if _is_symbol(second):
                    # Named let
                    let_name = second.name
                    bindings_list = _parse_bindings(_caddr(expr))
                    body = _as_list(_cdr(_cdr(_cdr(expr))))
                    if not body:
                        raise SchemeError("let: empty body")
                    inits = [_eval(init, env, output) for _, init in bindings_list]
                    params = [n for n, _ in bindings_list]
                    letrec_env = Env({let_name: UNINITIALIZED}, env)
                    cl = Closure(params, body, letrec_env)
                    letrec_env.bindings[let_name] = cl
                    # Tail-call the closure
                    new_env = _bind_params(cl, inits)
                    body_forms = cl.body
                    body_idx = 0
                    env = new_env
                    continue
                else:
                    # Regular let
                    bindings_list = _parse_bindings(second)
                    body = _as_list(_cddr(expr))
                    if not body:
                        raise SchemeError("let: empty body")
                    vals = [_eval(init, env, output) for _, init in bindings_list]
                    new_env = Env(dict(zip([n.name for n, _ in bindings_list], vals)), env)
                    for form in body:
                        if _is_pair(form) and _is_proper_list(form):
                            h = form.car
                            if _is_symbol(h) and h.name == 'define':
                                try:
                                    dn = _extract_define_name(form)
                                    if dn not in new_env.bindings:
                                        new_env.bindings[dn] = UNINITIALIZED
                                except SchemeError:
                                    pass
                    for f in body[:-1]:
                        _eval(f, new_env, output)
                    expr = body[-1]
                    env = new_env
                    continue
            if name == 'let*':
                bindings_list = _parse_bindings(_cadr(expr))
                body = _as_list(_cddr(expr))
                if not body:
                    raise SchemeError("let*: empty body")
                new_env = Env({}, env)
                for nm, init in bindings_list:
                    val = _eval(init, env, output)
                    new_env.bindings[nm.name] = val
                for form in body:
                    if _is_pair(form) and _is_proper_list(form):
                        h = form.car
                        if _is_symbol(h) and h.name == 'define':
                            try:
                                dn = _extract_define_name(form)
                                if dn not in new_env.bindings:
                                    new_env.bindings[dn] = UNINITIALIZED
                            except SchemeError:
                                pass
                for f in body[:-1]:
                    _eval(f, new_env, output)
                expr = body[-1]
                env = new_env
                continue
            if name == 'letrec':
                bindings_list = _parse_bindings(_cadr(expr))
                body = _as_list(_cddr(expr))
                if not body:
                    raise SchemeError("letrec: empty body")
                new_env = Env({nm.name: UNINITIALIZED for nm, _ in bindings_list}, env)
                for form in body:
                    if _is_pair(form) and _is_proper_list(form):
                        h = form.car
                        if _is_symbol(h) and h.name == 'define':
                            try:
                                dn = _extract_define_name(form)
                                if dn not in new_env.bindings:
                                    new_env.bindings[dn] = UNINITIALIZED
                            except SchemeError:
                                pass
                for nm, init in bindings_list:
                    val = _eval(init, new_env, output)
                    new_env.bindings[nm.name] = val
                for f in body[:-1]:
                    _eval(f, new_env, output)
                expr = body[-1]
                env = new_env
                continue
            if name == 'apply':
                args_list = _as_list(_cdr(expr))
                if len(args_list) < 2:
                    raise SchemeError("apply: expected at least 2 arguments")
                f = _eval(args_list[0], env, output)
                eval_args = [_eval(a, env, output) for a in args_list[1:]]
                lst = eval_args[-1]
                if not _is_proper_list(lst):
                    raise SchemeError("apply: last argument must be a proper list")
                all_args = eval_args[:-1] + _as_list(lst)
                if not _is_proc(f):
                    raise SchemeError("apply: not a procedure")
                if isinstance(f, Closure):
                    new_env = _bind_params(f, all_args)
                    body_forms = f.body
                    body_idx = 0
                    env = new_env
                    continue
                else:
                    return f.func(all_args, output)
            # Not a special form - application in tail position
            op = _eval(_car(expr), env, output)
            args = [_eval(a, env, output) for a in _as_list(_cdr(expr))]
            if not _is_proc(op):
                raise SchemeError("not a procedure")
            if isinstance(op, Closure):
                new_env = _bind_params(op, args)
                body_forms = op.body
                body_idx = 0
                env = new_env
                continue
            else:
                return op.func(args, output)
        else:
            # Head is not a symbol - application in tail position
            op = _eval(_car(expr), env, output)
            args = [_eval(a, env, output) for a in _as_list(_cdr(expr))]
            if not _is_proc(op):
                raise SchemeError("not a procedure")
            if isinstance(op, Closure):
                new_env = _bind_params(op, args)
                body_forms = op.body
                body_idx = 0
                env = new_env
                continue
            else:
                return op.func(args, output)


def _eval_body(body, env, output):
    """Evaluate a body (list of forms). Last form in tail position."""
    for i, form in enumerate(body):
        if i < len(body) - 1:
            _eval(form, env, output)
        else:
            return _eval_tail(form, env, output)


def _call_proc(proc, args, output):
    if isinstance(proc, Closure):
        env = _bind_params(proc, args)
        return _eval_body(proc.body, env, output)
    elif isinstance(proc, BuiltinProcedure):
        return proc.func(args, output)
    else:
        raise SchemeError("not a procedure")


# === Special Form Evaluators (non-tail) ===

def _eval_quote(expr):
    elems = _as_list(expr)
    if len(elems) != 2:
        raise SchemeError("malformed quote")
    return elems[1]

def _eval_lambda(expr):
    elems = _as_list(expr)
    if len(elems) < 3:
        raise SchemeError("malformed lambda")
    params = elems[1]
    body = elems[2:]
    # Validate params
    if _is_symbol(params):
        pass
    elif _is_pair(params):
        cur = params
        while isinstance(cur, Pair):
            if not _is_symbol(cur.car):
                raise SchemeError("malformed formals")
            cur = cur.cdr
        if not (_is_symbol(cur) or _is_empty(cur)):
            raise SchemeError("malformed formals")
    else:
        raise SchemeError("malformed formals")
    return Closure(params, body, None)  # defining_env set later? No, we need it now.

# Actually, lambda needs the defining env. Let me fix this.

def _eval_lambda(expr, env):
    elems = _as_list(expr)
    if len(elems) < 3:
        raise SchemeError("malformed lambda")
    params = elems[1]
    body = elems[2:]
    if _is_symbol(params):
        pass
    elif _is_pair(params):
        cur = params
        while isinstance(cur, Pair):
            if not _is_symbol(cur.car):
                raise SchemeError("malformed formals")
            cur = cur.cdr
        if not (_is_symbol(cur) or _is_empty(cur)):
            raise SchemeError("malformed formals")
    else:
        raise SchemeError("malformed formals")
    return Closure(params, body, env)

def _eval_if(expr, env, output):
    elems = _as_list(expr)
    if len(elems) < 3:
        raise SchemeError("malformed if")
    test = _eval(elems[1], env, output)
    if _is_true(test):
        return _eval(elems[2], env, output)
    elif len(elems) >= 4:
        return _eval(elems[3], env, output)
    else:
        return UNSPECIFIED

def _eval_define(expr, env, output):
    elems = _as_list(expr)
    if len(elems) < 3:
        raise SchemeError("malformed define")
    second = elems[1]
    if _is_pair(second):
        # (define (name . formals) body...)
        if not _is_proper_list(second):
            raise SchemeError("malformed define")
        name = second.car
        if not _is_symbol(name):
            raise SchemeError("define: name must be a symbol")
        formals = second.cdr
        body = elems[2:]
        if not body:
            raise SchemeError("define: empty body")
        # Validate formals
        if _is_symbol(formals):
            pass
        elif _is_pair(formals):
            cur = formals
            while isinstance(cur, Pair):
                if not _is_symbol(cur.car):
                    raise SchemeError("malformed formals")
                cur = cur.cdr
            if not (_is_symbol(cur) or _is_empty(cur)):
                raise SchemeError("malformed formals")
        else:
            raise SchemeError("malformed formals")
        val = Closure(formals, body, env)
        env.bindings[name.name] = val
    elif _is_symbol(second):
        val = _eval(elems[2], env, output)
        env.bindings[second.name] = val
    else:
        raise SchemeError("define: name must be a symbol")
    return UNSPECIFIED

def _eval_set(expr, env, output):
    elems = _as_list(expr)
    if len(elems) != 3:
        raise SchemeError("malformed set!")
    if not _is_symbol(elems[1]):
        raise SchemeError("set!: name must be a symbol")
    val = _eval(elems[2], env, output)
    _set_var(env, elems[1], val)
    return UNSPECIFIED

def _eval_begin(expr, env, output):
    forms = _as_list(_cdr(expr))
    if not forms:
        raise SchemeError("begin: empty body")
    for f in forms[:-1]:
        _eval(f, env, output)
    return _eval(forms[-1], env, output)

def _eval_cond(expr, env, output):
    clauses = _as_list(_cdr(expr))
    for i, clause in enumerate(clauses):
        if not _is_pair(clause) or not _is_proper_list(clause) or _is_empty(clause):
            raise SchemeError("malformed cond clause")
        test = clause.car
        if _is_symbol(test) and test.name == 'else':
            if i != len(clauses) - 1:
                raise SchemeError("else must be last clause")
            body = _as_list(_cdr(clause))
            if not body:
                raise SchemeError("else clause must