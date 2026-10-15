import sys
import re
import threading

sys.setrecursionlimit(1000000)
try:
    sys.set_int_max_str_digits(0)
except (AttributeError, ValueError):
    pass

# ─── Exception ────────────────────────────────────────────────────────────────

class SchemeError(Exception):
    def __init__(self, message, output=''):
        super().__init__(message)
        self.output = output

# ─── Data Types ───────────────────────────────────────────────────────────────

class Symbol:
    __slots__ = ('name',)
    def __init__(self, name): self.name = name
    def __repr__(self): return self.name

class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr): self.car = car; self.cdr = cdr

class NilType:
    _instance = None
    def __new__(cls):
        if cls._instance is None: cls._instance = super().__new__(cls)
        return cls._instance
    def __repr__(self): return '()'
NIL = NilType()

class UnspecifiedType:
    _instance = None
    def __new__(cls):
        if cls._instance is None: cls._instance = super().__new__(cls)
        return cls._instance
Unspecified = UnspecifiedType()

class UndefinedSentinel:
    pass
UNDEFINED = UndefinedSentinel()

class Closure:
    __slots__ = ('params', 'rest', 'body', 'env')
    def __init__(self, params, rest, body, env):
        self.params = params; self.rest = rest; self.body = body; self.env = env

class Builtin:
    __slots__ = ('name', 'func', 'min_args', 'max_args')
    def __init__(self, name, func, min_args, max_args):
        self.name = name; self.func = func; self.min_args = min_args; self.max_args = max_args

# ─── Reader ───────────────────────────────────────────────────────────────────

_INT_RE = re.compile(r'^[+-]?[0-9]+$')

def _tokenize(source):
    tokens = []
    i, n = 0, len(source)
    while i < n:
        c = source[i]
        if c in ' \t\n\r':
            i += 1
        elif c == ';':
            while i < n and source[i] != '\n': i += 1
        elif c == '(':
            tokens.append(('(', None)); i += 1
        elif c == ')':
            tokens.append((')', None)); i += 1
        elif c == "'":
            tokens.append(("'", None)); i += 1
        elif c == '"':
            i += 1; s = []
            while i < n and source[i] != '"':
                if source[i] == '\\':
                    i += 1
                    if i >= n: raise ValueError("unterminated string")
                    nc = source[i]
                    if nc == '"': s.append('"')
                    elif nc == '\\': s.append('\\')
                    elif nc == 'n': s.append('\n')
                    else: raise ValueError(f"bad escape \\{nc}")
                    i += 1
                else:
                    s.append(source[i]); i += 1
            if i >= n: raise ValueError("unterminated string")
            i += 1
            tokens.append(('STRING', ''.join(s)))
        else:
            start = i
            while i < n and source[i] not in ' \t\n\r()";\'': i += 1
            tokens.append(('ATOM', source[start:i]))
    return tokens

def _parse_atom(tok):
    if tok == '#t': return True
    if tok == '#f': return False
    if tok.startswith('#'): raise ValueError(f"bad # token: {tok}")
    if _INT_RE.match(tok): return int(tok)
    return Symbol(tok)

def _parse(tokens, pos):
    forms = []
    while pos[0] < len(tokens):
        if tokens[pos[0]][0] == ')': raise ValueError("unexpected )")
        forms.append(_parse_form(tokens, pos))
    return forms

def _parse_form(tokens, pos):
    if pos[0] >= len(tokens): raise ValueError("unexpected end of input")
    tt, tv = tokens[pos[0]]
    if tt == '(':
        pos[0] += 1
        return _parse_list(tokens, pos)
    elif tt == "'":
        pos[0] += 1
        if pos[0] >= len(tokens) or tokens[pos[0]][0] == ')':
            raise ValueError("quote not followed by datum")
        datum = _parse_form(tokens, pos)
        return Pair(Symbol('quote'), Pair(datum, NIL))
    elif tt == ')':
        raise ValueError("unexpected )")
    elif tt == 'STRING':
        pos[0] += 1; return tv
    elif tt == 'ATOM':
        pos[0] += 1; return _parse_atom(tv)
    raise ValueError(f"unexpected token")

def _parse_list(tokens, pos):
    elements = []
    dotted = False; dot_val = None
    while True:
        if pos[0] >= len(tokens): raise ValueError("unbalanced (")
        tt, tv = tokens[pos[0]]
        if tt == ')':
            pos[0] += 1; break
        if tt == 'ATOM' and tv == '.':
            if not elements: raise ValueError("dot without preceding element")
            pos[0] += 1
            if pos[0] >= len(tokens) or tokens[pos[0]][0] == ')':
                raise ValueError("dot not followed by datum")
            dot_val = _parse_form(tokens, pos)
            if pos[0] >= len(tokens) or tokens[pos[0]][0] != ')':
                raise ValueError("expected ) after dot datum")
            pos[0] += 1; dotted = True; break
        elements.append(_parse_form(tokens, pos))
    if dotted:
        result = dot_val
        for e in reversed(elements): result = Pair(e, result)
        return result
    result = NIL
    for e in reversed(elements): result = Pair(e, result)
    return result

# ─── Environment ──────────────────────────────────────────────────────────────

class Frame:
    __slots__ = ('bindings',)
    def __init__(self): self.bindings = {}

class Cell:
    __slots__ = ('value',)
    def __init__(self, value): self.value = value

class Env:
    __slots__ = ('frame', 'parent')
    def __init__(self, frame, parent=None):
        self.frame = frame; self.parent = parent

def _lookup(name, env):
    e = env
    while e is not None:
        if name in e.frame.bindings:
            cell = e.frame.bindings[name]
            if cell.value is UNDEFINED:
                raise SchemeError(f"variable '{name}' not yet defined")
            return cell.value
        e = e.parent
    raise SchemeError(f"unbound variable: {name}")

def _set_var(name, value, env):
    e = env
    while e is not None:
        if name in e.frame.bindings:
            cell = e.frame.bindings[name]
            if cell.value is UNDEFINED:
                raise SchemeError(f"variable '{name}' not yet defined")
            cell.value = value; return
        e = e.parent
    raise SchemeError(f"set!: unbound variable: {name}")

def _define_var(name, value, env):
    env.frame.bindings[name] = Cell(value)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _to_list(pair):
    result = []
    cur = pair
    while isinstance(cur, Pair):
        result.append(cur.car); cur = cur.cdr
    if not isinstance(cur, NilType): return None  # improper
    return result

def _is_proper_list(x):
    while isinstance(x, Pair): x = x.cdr
    return isinstance(x, NilType)

def _list_to_pair(lst):
    result = NIL
    for item in reversed(lst): result = Pair(item, result)
    return result

def _truthy(x):
    return x is not False

def _int_to_radix(n, radix):
    if n == 0: return '0'
    neg = n < 0; n = abs(n)
    digits = []
    while n > 0:
        digits.append('0123456789abcdef'[n % radix]); n //= radix
    s = ''.join(reversed(digits))
    return ('-' + s) if neg else s

# ─── Display / Write ──────────────────────────────────────────────────────────

def _escape_str(s):
    parts = ['"']
    for c in s:
        if c == '"': parts.append('\\"')
        elif c == '\\': parts.append('\\\\')
        elif c == '\n': parts.append('\\n')
        else: parts.append(c)
    parts.append('"')
    return ''.join(parts)

def _display_repr(val, write_mode=False):
    result = []
    # stack items: either str (literal) or tuple ('v', value) or ('cdr', value)
    stack = [('v', val)]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            result.append(item); continue
        kind, v = item
        if kind == 'v':
            if isinstance(v, bool):
                result.append('#t' if v else '#f')
            elif isinstance(v, int):
                result.append(str(v))
            elif isinstance(v, str):
                result.append(_escape_str(v) if write_mode else v)
            elif isinstance(v, Symbol):
                result.append(v.name)
            elif isinstance(v, NilType):
                result.append('()')
            elif isinstance(v, Pair):
                stack.append(')')
                stack.append(('cdr', v.cdr))
                stack.append(('v', v.car))
                stack.append('(')
            elif isinstance(v, (Closure, Builtin)):
                result.append('#<procedure>')
            elif isinstance(v, UnspecifiedType):
                pass
            else:
                result.append(str(v))
        elif kind == 'cdr':
            if isinstance(v, Pair):
                stack.append(('cdr', v.cdr))
                stack.append(' ')
                stack.append(('v', v.car))
            elif isinstance(v, NilType):
                pass
            else:
                stack.append(' . ')
                stack.append(('v', v))
    return ''.join(result)

# ─── Evaluator ────────────────────────────────────────────────────────────────

def _is_define(form):
    return isinstance(form, Pair) and isinstance(form.car, Symbol) and form.car.name == 'define'

def _parse_define(form):
    rest = form.cdr
    if isinstance(rest, NilType): raise SchemeError("(define) malformed")
    target = rest.car
    if isinstance(target, Symbol):
        exprs = _to_list(rest.cdr)
        if exprs is None or len(exprs) != 1:
            raise SchemeError("define: expected one expression")
        return target.name, exprs[0]
    elif isinstance(target, Pair):
        if not isinstance(target.car, Symbol):
            raise SchemeError("define: name must be symbol")
        formals = target.cdr
        body = _to_list(rest.cdr)
        if body is None or len(body) == 0:
            raise SchemeError("define: empty body")
        lam = Pair(Symbol('lambda'), Pair(formals, _list_to_pair(body)))
        return target.car.name, lam
    else:
        raise SchemeError("define: invalid target")

def _parse_formals(formals):
    if isinstance(formals, Symbol):
        return [], formals.name
    if isinstance(formals, NilType):
        return [], None
    if isinstance(formals, Pair):
        params = []; cur = formals
        while isinstance(cur, Pair):
            if not isinstance(cur.car, Symbol):
                raise SchemeError("formals must be symbols")
            params.append(cur.car.name); cur = cur.cdr
        if isinstance(cur, NilType): return params, None
        if isinstance(cur, Symbol): return params, cur.name
        raise SchemeError("invalid formals")
    raise SchemeError("invalid formals")

def _make_call_env(closure, args):
    frame = Frame()
    env = Env(frame, closure.env)
    params = closure.params
    rest = closure.rest
    if rest is None:
        if len(args) != len(params):
            raise SchemeError(f"wrong number of arguments: expected {len(params)}, got {len(args)}")
        for p, a in zip(params, args):
            frame.bindings[p] = Cell(a)
    else:
        if len(args) < len(params):
            raise SchemeError(f"wrong number of arguments: expected at least {len(params)}, got {len(args)}")
        for p, a in zip(params, args):
            frame.bindings[p] = Cell(a)
        frame.bindings[rest] = Cell(_list_to_pair(args[len(params):]))
    return env

def _scan_internal_defines(body):
    names = []
    for form in body:
        if _is_define(form):
            rest = form.cdr
            if isinstance(rest, NilType): continue
            target = rest.car
            if isinstance(target, Symbol):
                names.append(target.name)
            elif isinstance(target, Pair) and isinstance(target.car, Symbol):
                names.append(target.car.name)
    return names

def _process_body(body, env):
    """Process body forms, handling internal defines. Returns (env, last_expr) or ('ret', value)."""
    for form in body[:-1]:
        if _is_define(form):
            name, ve = _parse_define(form)
            val = _eval(ve, env)
            env.frame.bindings[name] = Cell(val)
        else:
            _eval(form, env)
    last = body[-1]
    if _is_define(last):
        name, ve = _parse_define(last)
        val = _eval(ve, env)
        env.frame.bindings[name] = Cell(val)
        return ('ret', Unspecified)
    return ('tail', last, env)

def _eval(expr, env):
    while True:
        # Self-evaluating
        if isinstance(expr, bool): return expr
        if isinstance(expr, int): return expr
        if isinstance(expr, str): return expr
        if isinstance(expr, NilType):
            raise SchemeError("() cannot be evaluated")
        if isinstance(expr, Symbol):
            return _lookup(expr.name, env)

        if not isinstance(expr, Pair):
            raise SchemeError(f"cannot evaluate: {expr}")

        head = expr.car
        if isinstance(head, Symbol):
            name = head.name

            # quote
            if name == 'quote':
                rest = _to_list(expr.cdr)
                if rest is None or len(rest) != 1:
                    raise SchemeError("(quote) malformed")
                return rest[0]

            # if
            if name == 'if':
                parts = _to_list(expr.cdr)
                if parts is None or len(parts) < 2 or len(parts) > 3:
                    raise SchemeError("(if) malformed")
                tv = _eval(parts[0], env)
                if _truthy(tv):
                    expr = parts[1]; continue
                elif len(parts) == 3:
                    expr = parts[2]; continue
                else:
                    return Unspecified

            # define
            if name == 'define':
                dname, dexpr = _parse_define(expr)
                val = _eval(dexpr, env)
                env.frame.bindings[dname] = Cell(val)
                return Unspecified

            # set!
            if name == 'set!':
                parts = _to_list(expr.cdr)
                if parts is None or len(parts) != 2:
                    raise SchemeError("(set!) malformed")
                if not isinstance(parts[0], Symbol):
                    raise SchemeError("set!: target must be symbol")
                val = _eval(parts[1], env)
                _set_var(parts[0].name, val, env)
                return Unspecified

            # begin
            if name == 'begin':
                parts = _to_list(expr.cdr)
                if parts is None or len(parts) == 0:
                    raise SchemeError("(begin) malformed")
                for f in parts[:-1]:
                    _eval(f, env)
                expr = parts[-1]; continue

            # cond
            if name == 'cond':
                clauses = _to_list(expr.cdr)
                if clauses is None: raise SchemeError("(cond) malformed")
                matched = False
                for clause in clauses:
                    if not isinstance(clause, Pair):
                        raise SchemeError("cond: clause must be a list")
                    cparts = _to_list(clause)
                    if cparts is None: raise SchemeError("cond: improper clause")
                    test = cparts[0]
                    if isinstance(test, Symbol) and test.name == 'else':
                        exprs = cparts[1:]
                        if not exprs: return Unspecified
                        for e in exprs[:-1]: _eval(e, env)
                        expr = exprs[-1]; matched = True; break
                    else:
                        tv = _eval(test, env)
                        if _truthy(tv):
                            exprs = cparts[1:]
                            if not exprs: return tv
                            for e in exprs[:-1]: _eval(e, env)
                            expr = exprs[-1]; matched = True; break
                if not matched:
                    return Unspecified
                if matched: continue

            # and
            if name == 'and':
                parts = _to_list(expr.cdr)
                if parts is None: raise SchemeError("(and) malformed")
                if not parts: return True
                for e in parts[:-1]:
                    v = _eval(e, env)
                    if v is False: return False
                expr = parts[-1]; continue

            # or
            if name == 'or':
                parts = _to_list(expr.cdr)
                if parts is None: raise SchemeError("(or) malformed")
                if not parts: return False
                for e in parts[:-1]:
                    v = _eval(e, env)
                    if v is not False: return v
                expr = parts[-1]; continue

            # lambda
            if name == 'lambda':
                rest = expr.cdr
                if isinstance(rest, NilType): raise SchemeError("(lambda) malformed")
                formals = rest.car
                body = _to_list(rest.cdr)
                if body is None or len(body) == 0:
                    raise SchemeError("lambda: empty body")
                params, rname = _parse_formals(formals)
                return Closure(params, rname, body, env)

            # let / let* / letrec / named let
            if name in ('let', 'let*', 'letrec'):
                rest = expr.cdr
                if isinstance(rest, NilType): raise SchemeError(f"({name}) malformed")
                bindings_expr = rest.car
                body = _to_list(rest.cdr)
                if body is None or len(body) == 0:
                    raise SchemeError(f"{name}: empty body")

                if name == 'let':
                    bindings = _to_list(bindings_expr)
                    if bindings is None: raise SchemeError("let: bad bindings")
                    inits = []
                    for b in bindings:
                        bl = _to_list(b)
                        if bl is None or len(bl) != 2:
                            raise SchemeError("let: bad binding")
                        inits.append(_eval(bl[1], env))
                    frame = Frame()
                    new_env = Env(frame, env)
                    for b, v in zip(bindings, inits):
                        bl = _to_list(b)
                        frame.bindings[bl[0].name] = Cell(v)
                    # internal defines
                    id_names = _scan_internal_defines(body)
                    for n2 in id_names:
                        if n2 not in frame.bindings:
                            frame.bindings[n2] = Cell(UNDEFINED)
                    result = _process_body(body, new_env)
                    if result[0] == 'ret': return result[1]
                    expr = result[1]; env = result[2]; continue

                elif name == 'let*':
                    bindings = _to_list(bindings_expr)
                    if bindings is None: raise SchemeError("let*: bad bindings")
                    frame = Frame()
                    new_env = Env(frame, env)
                    # pre-bind internal defines
                    id_names = _scan_internal_defines(body)
                    for n2 in id_names:
                        frame.bindings[n2] = Cell(UNDEFINED)
                    for b in bindings:
                        bl = _to_list(b)
                        if bl is None or len(bl) != 2:
                            raise SchemeError("let*: bad binding")
                        v = _eval(bl[1], new_env)
                        frame.bindings[bl[0].name] = Cell(v)
                    result = _process_body(body, new_env)
                    if result[0] == 'ret': return result[1]
                    expr = result[1]; env = result[2]; continue

                else:  # letrec
                    bindings = _to_list(bindings_expr)
                    if bindings is None: raise SchemeError("letrec: bad bindings")
                    frame = Frame()
                    new_env = Env(frame, env)
                    for b in bindings:
                        bl = _to_list(b)
                        if bl is None or len(bl) != 2:
                            raise SchemeError("letrec: bad binding")
                        frame.bindings[bl[0].name] = Cell(UNDEFINED)
                    id_names = _scan_internal_defines(body)
                    for n2 in id_names:
                        if n2 not in frame.bindings:
                            frame.bindings[n2] = Cell(UNDEFINED)
                    for b in bindings:
                        bl = _to_list(b)
                        v = _eval(bl[1], new_env)
                        frame.bindings[bl[0].name] = Cell(v)
                    result = _process_body(body, new_env)
                    if result[0] == 'ret': return result[1]
                    expr = result[1]; env = result[2]; continue

            # named let: (let name ((v init)...) body...)
            if name == 'let':
                pass  # handled above

            # Check for named let (let with symbol as second element)
            # Actually we need to restructure: check before the let/let*/letrec block
            # Let me handle it here by re-checking

        # Named let check: (let NAME ((v init)...) body...)
        if isinstance(head, Symbol) and head.name == 'let':
            rest = expr.cdr
            if not isinstance(rest, NilType):
                second = rest.car
                if isinstance(second, Symbol):
                    lname = second.name
                    bindings_expr = rest.cdr.car if isinstance(rest.cdr, Pair) else NIL
                    body = _to_list(rest.cdr.cdr) if isinstance(rest.cdr, Pair) and isinstance(rest.cdr.cdr, Pair) else None
                    if body is None:
                        body = _to_list(rest.cdr.cdr) if isinstance(rest.cdr, Pair) else None
                    if body is None or len(body) == 0:
                        raise SchemeError("named let: empty body")
                    bindings = _to_list(bindings_expr)
                    if bindings is None: raise SchemeError("named let: bad bindings")
                    inits = []
                    for b in bindings:
                        bl = _to_list(b)
                        if bl is None or len(bl) != 2:
                            raise SchemeError("named let: bad binding")
                        inits.append(_eval(bl[1], env))
                    # Create frame for the named let
                    frame = Frame()
                    let_env = Env(frame, env)
                    # Create closure
                    params = []
                    for b in bindings:
                        bl = _to_list(b)
                        params.append(bl[0].name)
                    # Internal defines in body
                    id_names = _scan_internal_defines(body)
                    # The closure captures let_env (which has the name)
                    closure = Closure(params, None, body, let_env)
                    frame.bindings[lname] = Cell(closure)
                    # Call the closure with inits (tail call)
                    call_frame = Frame()
                    call_env = Env(call_frame, let_env)
                    for p, v in zip(params, inits):
                        call_frame.bindings[p] = Cell(v)
                    for n2 in id_names:
                        if n2 not in call_frame.bindings:
                            call_frame.bindings[n2] = Cell(UNDEFINED)
                    # Process body
                    result = _process_body(body, call_env)
                    if result[0] == 'ret': return result[1]
                    expr = result[1]; env = result[2]; continue

        # apply special handling for TCO
        if isinstance(head, Symbol) and head.name == 'apply':
            apply_val = None
            try: apply_val = _lookup('apply', env)
            except SchemeError: pass
            if isinstance(apply_val, Builtin) and apply_val.name == 'apply':
                parts = _to_list(expr.cdr)
                if parts is None or len(parts) < 2:
                    raise SchemeError("apply: requires at least 2 arguments")
                f = _eval(parts[0], env)
                rest_args = []
                for a in parts[1:-1]:
                    rest_args.append(_eval(a, env))
                lst = _eval(parts[-1], env)
                if not _is_proper_list(lst):
                    raise SchemeError("apply: last argument must be a proper list")
                cur = lst
                while isinstance(cur, Pair):
                    rest_args.append(cur.car); cur = cur.cdr
                if not isinstance(f, (Closure, Builtin)):
                    raise SchemeError("apply: not a procedure")
                if isinstance(f, Closure):
                    env = _make_call_env(f, rest_args)
                    expr = f.body[-1] if len(f.body) == 1 else None
                    if expr is None:
                        # process body
                        result = _process_body(f.body, env)
                        if result[0] == 'ret': return result[1]
                        expr = result[1]; env = result[2]; continue
                    continue
                else:
                    _check_arity(f, len(rest_args))
                    return f.func(rest_args)

        # Application
        if not _is_proper_list(expr):
            raise SchemeError("dotted form used as application")
        op = _eval(expr.car, env)
        args = []
        cur = expr.cdr
        while isinstance(cur, Pair):
            args.append(_eval(cur.car, env)); cur = cur.cdr
        if not isinstance(op, (Closure, Builtin)):
            raise SchemeError(f"not a procedure: {_display_repr(op)}")
        if isinstance(op, Closure):
            env = _make_call_env(op, args)
            body = op.body
            result = _process_body(body, env)
            if result[0] == 'ret': return result[1]
            expr = result[1]; env = result[2]; continue
        else:
            _check_arity(op, len(args))
            return op.func(args)

def _check_arity(builtin, nargs):
    if nargs < builtin.min_args:
        raise SchemeError(f"{builtin.name}: too few arguments")
    if builtin.max_args is not None and nargs > builtin.max_args:
        raise SchemeError(f"{builtin.name}: too many arguments")

# ─── Builtins ─────────────────────────────────────────────────────────────────

_output_buf = None

def _get_output():
    return _output_buf

def _is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)

def _make_builtins():
    blts = {}

    def _b(name, func, min_a, max_a=None):
        blts[name] = Builtin(name, func, min_a, max_a)

    # Numbers
    def _plus(args):
        r = 0
        for a in args:
            if not _is_int(a): raise SchemeError("+: not an integer")
            r += a
        return r
    _b('+', _plus, 0)

    def _times(args):
        r = 1
        for a in args:
            if not _is_int(a): raise SchemeError("*: not an integer")
            r *= a
        return r
    _b('*', _times, 0)

    def _minus(args):
        for a in args:
            if not _is_int(a): raise SchemeError("-: not an integer")
        if len(args) == 1: return -args[0]
        r = args[0]
        for a in args[1:]: r -= a
        return r
    _b('-', _minus, 1)

    def _quotient(args):
        a, b = args
        if not _is_int(a) or not _is_int(b): raise SchemeError("quotient: not integers")
        if b == 0: raise SchemeError("quotient: division by zero")
        q = abs(a) // abs(b)
        if (a < 0) != (b < 0): q = -q
        return q
    _b('quotient', _quotient, 2, 2)

    def _remainder(args):
        a, b = args
        if not _is_int(a) or not _is_int(b): raise SchemeError("remainder: not integers")
        if b == 0: raise SchemeError("remainder: division by zero")
        q = abs(a) // abs(b)
        if (a < 0) != (b < 0): q = -q
        return a - b * q
    _b('remainder', _remainder, 2, 2)

    def _modulo(args):
        a, b = args
        if not _is_int(a) or not _is_int(b): raise SchemeError("modulo: not integers")
        if b == 0: raise SchemeError("modulo: division by zero")
        return a % b
    _b('modulo', _modulo, 2, 2)

    def _make_cmp(name, cmp_fn):
        def fn(args):
            for a in args:
                if not _is_int(a): raise SchemeError(f"{name}: not an integer")
            for i in range(len(args) - 1):
                if not cmp_fn(args[i], args[i+1]): return False
            return True
        return fn
    _b('=', _make_cmp('=', lambda a,b: a==b), 1)
    _b('<', _make_cmp('<', lambda a,b: a<b), 1)
    _b('>', _make_cmp('>', lambda a,b: a>b), 1)
    _b('<=', _make_cmp('<=', lambda a,b: a<=b), 1)
    _b('>=', _make_cmp('>=', lambda a,b: a>=b), 1)

    def _number_to_string(args):
        n = args[0]
        if not _is_int(n): raise SchemeError("number->string: not an integer")
        radix = 10
        if len(args) == 2:
            radix = args[1]
            if not _is_int(radix) or radix not in (2, 8, 10, 16):
                raise SchemeError("number->string: bad radix")
        if radix == 10: return str(n)
        return _int_to_radix(n, radix)
    _b('number->string', _number_to_string, 1, 2)

    # Lists and pairs
    def _cons(args): return Pair(args[0], args[1])
    _b('cons', _cons, 2, 2)

    def _car(args):
        p = args[0]
        if not isinstance(p, Pair): raise SchemeError("car: not a pair")
        return p.car
    _b('car', _car, 1, 1)

    def _cdr(args):
        p = args[0]
        if not isinstance(p, Pair): raise SchemeError("cdr: not a pair")
        return p.cdr
    _b('cdr', _cdr, 1, 1)

    def _list(args): return _list_to_pair(args)
    _b('list', _list, 0)

    def _null_q(args): return isinstance(args[0], NilType)
    _b('null?', _null_q, 1, 1)

    def _pair_q(args): return isinstance(args[0], Pair)
    _b('pair?', _pair_q, 1, 1)

    def _list_q(args): return _is_proper_list(args[0])
    _b('list?', _list_q, 1, 1)

    def _length(args):
        l = args[0]; n = 0
        while isinstance(l, Pair): n += 1; l = l.cdr
        if not isinstance(l, NilType): raise SchemeError("length: not a proper list")
        return n
    _b('length', _length, 1, 1)

    def _append(args):
        if not args: return NIL
        result = []
        for i, a in enumerate(args[:-1]):
            cur = a
            while isinstance(cur, Pair):
                result.append(cur.car); cur = cur.cdr
            if not isinstance(cur, NilType):
                raise SchemeError("append: not a proper list")
        last = args[-1]
        r = last
        for item in reversed(result): r = Pair(item, r)
        return r
    _b('append', _append, 0)

    def _reverse(args):
        l = args[0]; result = []
        while isinstance(l, Pair): result.append(l.car); l = l.cdr
        if not isinstance(l, NilType): raise SchemeError("reverse: not a proper list")
        return _list_to_pair(result)
    _b('reverse', _reverse, 1, 1)

    def _apply(args):
        f = args[0]; rest = args[1:-1]; lst = args[-1]
        if not _is_proper_list(lst): raise SchemeError("apply: last argument must be a proper list")
        all_args = list(rest)
        cur = lst
        while isinstance(cur, Pair): all_args.append(cur.car); cur = cur.cdr
        if not isinstance(f, (Closure, Builtin)): raise SchemeError("apply: not a procedure")
        if isinstance(f, Closure):
            env2 = _make_call_env(f, all_args)
            return _eval_body(f.body, env2)
        else:
            _check_arity(f, len(all_args))
            return f.func(all_args)
    _b('apply', _apply, 2)

    # Equality and predicates
    def _eq_q(args):
        a, b = args
        if isinstance(a, bool) and isinstance(b, bool): return a is b
        if _is_int(a) and _is_int(b): return a == b
        if isinstance(a, Symbol) and isinstance(b, Symbol): return a is b
        if isinstance(a, NilType) and isinstance(b, NilType): return True