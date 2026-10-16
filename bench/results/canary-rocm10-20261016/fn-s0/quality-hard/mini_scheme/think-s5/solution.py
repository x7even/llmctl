import sys
import threading

if hasattr(sys, 'set_int_max_str_digits'):
    try:
        sys.set_int_max_str_digits(0)
    except Exception:
        pass

# === Data Types ===

class SchemeError(Exception):
    def __init__(self, msg, output=''):
        super().__init__(msg)
        self.output = output

class Symbol:
    __slots__ = ('name',)
    def __init__(self, name): self.name = name
    def __repr__(self): return self.name
    def __hash__(self): return hash(self.name)
    def __eq__(self, other): return isinstance(other, Symbol) and self.name == other.name

_symbols = {}
def intern(name):
    if name not in _symbols:
        _symbols[name] = Symbol(name)
    return _symbols[name]

class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr): self.car = car; self.cdr = cdr

class NilType:
    def __repr__(self): return '()'
NIL = NilType()

class UnspecifiedType:
    def __repr__(self): return ''
UNSPECIFIED = UnspecifiedType()

class UnassignedType:
    pass
UNASSIGNED = UnassignedType()

class Closure:
    __slots__ = ('formals', 'body', 'env')
    def __init__(self, formals, body, env):
        self.formals = formals; self.body = body; self.env = env

class Builtin:
    __slots__ = ('name', 'fn')
    def __init__(self, name, fn): self.name = name; self.fn = fn

# === Reader ===

class _Reader:
    def __init__(self, src): self.src = src; self.pos = 0
    def skip_ws(self):
        while self.pos < len(self.src):
            ch = self.src[self.pos]
            if ch in ' \t\n\r': self.pos += 1
            elif ch == ';':
                while self.pos < len(self.src) and self.src[self.pos] != '\n': self.pos += 1
            else: break
    def read(self):
        self.skip_ws()
        if self.pos >= len(self.src): return None
        ch = self.src[self.pos]
        if ch == '(': return self.read_list()
        if ch == ')': raise SchemeError("unexpected )")
        if ch == "'":
            self.pos += 1
            datum = self.read()
            if datum is None: raise SchemeError("quote not followed by datum")
            return Pair(intern('quote'), Pair(datum, NIL))
        if ch == '"': return self.read_string()
        return self.read_atom()
    def read_list(self):
        self.pos += 1
        elements = []; dot_seen = False; after_dot = None
        while True:
            self.skip_ws()
            if self.pos >= len(self.src): raise SchemeError("unbalanced (")
            if self.src[self.pos] == ')':
                if dot_seen and after_dot is None: raise SchemeError("dot without following datum")
                self.pos += 1; break
            datum = self.read()
            if datum is None: raise SchemeError("unbalanced (")
            if dot_seen:
                if after_dot is not None: raise SchemeError("too many items after dot")
                after_dot = datum
            elif isinstance(datum, Symbol) and datum.name == '.':
                if len(elements) == 0: raise SchemeError("dot without preceding element")
                dot_seen = True
            else: elements.append(datum)
        result = after_dot if dot_seen else NIL
        for elem in reversed(elements): result = Pair(elem, result)
        return result
    def read_string(self):
        self.pos += 1; chars = []
        while self.pos < len(self.src):
            ch = self.src[self.pos]
            if ch == '"': self.pos += 1; return ''.join(chars)
            if ch == '\\':
                self.pos += 1
                if self.pos >= len(self.src): raise SchemeError("unterminated string")
                esc = self.src[self.pos]
                if esc == '"': chars.append('"')
                elif esc == '\\': chars.append('\\')
                elif esc == 'n': chars.append('\n')
                else: raise SchemeError(f"invalid escape: \\{esc}")
                self.pos += 1
            else: chars.append(ch); self.pos += 1
        raise SchemeError("unterminated string")
    def read_atom(self):
        start = self.pos
        while self.pos < len(self.src):
            if self.src[self.pos] in ' \t\n\r()";\'': break
            self.pos += 1
        token = self.src[start:self.pos]
        if not token: raise SchemeError("empty token")
        return self.classify(token)
    def classify(self, token):
        if self.is_int(token): return int(token)
        if token == '#t': return True
        if token == '#f': return False
        if token.startswith('#'): raise SchemeError(f"unknown token: {token}")
        return intern(token)
    def is_int(self, t):
        i = 0
        if i < len(t) and t[i] in '+-': i += 1
        if i >= len(t): return False
        while i < len(t):
            if not ('0' <= t[i] <= '9'): return False
            i += 1
        return True

def read_all(source):
    r = _Reader(source); forms = []
    while True:
        r.skip_ws()
        if r.pos >= len(r.src): break
        form = r.read()
        if form is None: break
        forms.append(form)
    return forms

# === Environment ===

class Environment:
    __slots__ = ('vars', 'parent')
    def __init__(self, parent=None): self.vars = {}; self.parent = parent
    def lookup(self, sym):
        env = self
        while env is not None:
            if sym in env.vars:
                v = env.vars[sym]
                if isinstance(v, UnassignedType): raise SchemeError(f"unassigned variable: {sym.name}")
                return v
            env = env.parent
        raise SchemeError(f"unbound variable: {sym.name}")
    def set(self, sym, val):
        env = self
        while env is not None:
            if sym in env.vars: env.vars[sym] = val; return
            env = env.parent
        raise SchemeError(f"set!: unbound variable: {sym.name}")
    def define(self, sym, val): self.vars[sym] = val

# === Helpers ===

def to_list(p):
    r = []; cur = p
    while isinstance(cur, Pair): r.append(cur.car); cur = cur.cdr
    if cur is not NIL: raise SchemeError("malformed form (improper list)")
    return r

def is_true(v): return v is not False

def is_proper_list(x):
    cur = x
    while isinstance(cur, Pair): cur = cur.cdr
    return cur is NIL

def list_to_python(p):
    r = []; cur = p
    while isinstance(cur, Pair): r.append(cur.car); cur = cur.cdr
    if cur is not NIL: raise SchemeError("not a proper list")
    return r

def python_to_list(items):
    r = NIL
    for item in reversed(items): r = Pair(item, r)
    return r

def scan_internal_defines(body):
    names = []
    for form in body:
        if isinstance(form, Pair) and isinstance(form.car, Symbol) and form.car.name == 'define':
            if form.cdr is NIL: continue
            target = form.cdr.car
            if isinstance(target, Symbol): names.append(target)
            elif isinstance(target, Pair) and isinstance(target.car, Symbol): names.append(target.car)
    return names

# === Display / Write ===

def int_to_str(n, radix=10):
    if n == 0: return '0'
    neg = n < 0; n = abs(n)
    digits = '0123456789abcdef'
    parts = []
    while n > 0:
        parts.append(digits[n % radix]); n //= radix
    if neg: parts.append('-')
    return ''.join(reversed(parts))

def atom_repr(val, write_mode):
    if isinstance(val, bool): return '#t' if val else '#f'
    if isinstance(val, int): return int_to_str(val)
    if isinstance(val, str):
        if write_mode:
            return '"' + val.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'
        return val
    if isinstance(val, Symbol): return val.name
    if val is NIL: return '()'
    if val is UNSPECIFIED: return ''
    if isinstance(val, (Closure, Builtin)): return '#<procedure>'
    return str(val)

def display_repr(val, write_mode=False):
    parts = []
    _display_val(val, parts, write_mode)
    return ''.join(parts)

def _display_val(val, parts, write_mode):
    if isinstance(val, Pair):
        parts.append('(')
        cur = val; first = True
        while isinstance(cur, Pair):
            if not first: parts.append(' ')
            first = False
            _display_val(cur.car, parts, write_mode)
            cur = cur.cdr
        if cur is not NIL:
            parts.append(' . '); _display_val(cur, parts, write_mode)
        parts.append(')')
    else:
        parts.append(atom_repr(val, write_mode))

# === Equal? ===

def scheme_equal(a, b):
    stack = [(a, b)]
    while stack:
        x, y = stack.pop()
        if x is y: continue
        if isinstance(x, bool) or isinstance(y, bool):
            if x is not y: return False
            continue
        if isinstance(x, int) and isinstance(y, int):
            if x != y: return False
            continue
        if isinstance(x, Symbol) and isinstance(y, Symbol):
            if x.name != y.name: return False
            continue
        if isinstance(x, str) and isinstance(y, str):
            if x != y: return False
            continue
        if isinstance(x, Pair) and isinstance(y, Pair):
            cx, cy = x, y
            while isinstance(cx, Pair) and isinstance(cy, Pair):
                stack.append((cx.car, cy.car))
                cx = cx.cdr; cy = cy.cdr
            stack.append((cx, cy))
            continue
        return False
    return True

# === Evaluator ===

def eval_expr(expr, env, output):
    while True:
        if isinstance(expr, bool): return expr
        if isinstance(expr, int): return expr
        if isinstance(expr, str): return expr
        if expr is NIL: raise SchemeError("cannot evaluate ()")
        if expr is UNSPECIFIED: return UNSPECIFIED
        if isinstance(expr, Symbol): return env.lookup(expr)
        if not isinstance(expr, Pair): return expr

        head = expr.car
        if isinstance(head, Symbol):
            hn = head.name

            if hn == 'quote':
                if expr.cdr is NIL: raise SchemeError("malformed quote")
                return expr.cdr.car

            if hn == 'if':
                args = to_list(expr.cdr)
                if len(args) < 2 or len(args) > 3: raise SchemeError("malformed if")
                tv = eval_expr(args[0], env, output)
                if is_true(tv): expr = args[1]; continue
                if len(args) == 3: expr = args[2]; continue
                return UNSPECIFIED

            if hn == 'lambda':
                args = to_list(expr.cdr)
                if len(args) < 2: raise SchemeError("malformed lambda")
                return Closure(args[0], args[1:], env)

            if hn == 'define':
                args = to_list(expr.cdr)
                if len(args) < 2: raise SchemeError("malformed define")
                target = args[0]
                if isinstance(target, Symbol):
                    val = eval_expr(args[1], env, output)
                    env.define(target, val)
                    return UNSPECIFIED
                elif isinstance(target, Pair):
                    name = target.car
                    if not isinstance(name, Symbol): raise SchemeError("malformed define")
                    formals = target.cdr
                    body = args[1:]
                    if len(body) == 0: raise SchemeError("malformed define: empty body")
                    env.define(name, Closure(formals, body, env))
                    return UNSPECIFIED
                else: raise SchemeError("malformed define")

            if hn == 'set!':
                args = to_list(expr.cdr)
                if len(args) != 2: raise SchemeError("malformed set!")
                name = args[0]
                if not isinstance(name, Symbol): raise SchemeError("set!: not a symbol")
                val = eval_expr(args[1], env, output)
                env.set(name, val)
                return UNSPECIFIED

            if hn == 'begin':
                args = to_list(expr.cdr)
                if len(args) == 0: raise SchemeError("malformed begin")
                for i in range(len(args) - 1): eval_expr(args[i], env, output)
                expr = args[-1]; continue

            if hn == 'cond':
                clauses = to_list(expr.cdr)
                for ci, clause in enumerate(clauses):
                    if not isinstance(clause, Pair): raise SchemeError("malformed cond clause")
                    test = clause.car
                    try: body = to_list(clause.cdr)
                    except SchemeError: raise SchemeError("malformed cond clause")
                    if isinstance(test, Symbol) and test.name == 'else':
                        if ci != len(clauses) - 1: raise SchemeError("else must be last")
                        if not body: return UNSPECIFIED
                        for e in body[:-1]: eval_expr(e, env, output)
                        expr = body[-1]; continue
                    tv = eval_expr(test, env, output)
                    if is_true(tv):
                        if not body: return tv
                        for e in body[:-1]: eval_expr(e, env, output)
                        expr = body[-1]; continue
                return UNSPECIFIED

            if hn == 'and':
                args = to_list(expr.cdr)
                if len(args) == 0: return True
                for i in range(len(args) - 1):
                    v = eval_expr(args[i], env, output)
                    if not is_true(v): return False
                expr = args[-1]; continue

            if hn == 'or':
                args = to_list(expr.cdr)
                if len(args) == 0: return False
                for i in range(len(args) - 1):
                    v = eval_expr(args[i], env, output)
                    if is_true(v): return v
                expr = args[-1]; continue

            if hn == 'let':
                # (let ((v init)...) body...) or (let name ((v init)...) body...)
                rest = expr.cdr
                if rest is NIL: raise SchemeError("malformed let")
                first = rest.car
                if isinstance(first, Symbol):
                    # Named let
                    name = first
                    bindings_form = rest.cdr
                    if bindings_form is NIL: raise SchemeError("malformed named let")
                    bindings = to_list(bindings_form.car)
                    body = to_list(bindings_form.cdr)
                    if len(body) == 0: raise SchemeError("malformed let: empty body")
                    var_names = []; init_vals = []
                    for b in bindings:
                        if not isinstance(b, Pair) or not isinstance(b.car, Symbol): raise SchemeError("malformed let binding")
                        var_names.append(b.car)
                        if b.cdr is NIL: raise SchemeError("malformed let binding: no init")
                        if not isinstance(b.cdr.cdr, NilType) and not (isinstance(b.cdr, Pair) and b.cdr.cdr is NIL):
                            raise SchemeError("malformed let binding")
                        init_vals.append(eval_expr(b.cdr.car, env, output))
                    # Create letrec frame
                    letrec_env = Environment(env)
                    closure = Closure(python_to_list(var_names), body, letrec_env)
                    letrec_env.define(name, closure)
                    # Call closure (tail call)
                    call_env = Environment(letrec_env)
                    for vn, iv in zip(var_names, init_vals): call_env.define(vn, iv)
                    idefs = scan_internal_defines(body)
                    for d in idefs: call_env.define(d, UNASSIGNED)
                    for form in body[:-1]: eval_expr(form, call_env, output)
                    expr = body[-1]; env = call_env; continue
                else:
                    # Regular let
                    bindings = to_list(first)
                    body = to_list(rest.cdr)
                    if len(body) == 0: raise SchemeError("malformed let: empty body")
                    var_names = []; init_vals = []
                    for b in bindings:
                        if not isinstance(b, Pair) or not isinstance(b.car, Symbol): raise SchemeError("malformed let binding")
                        var_names.append(b.car)
                        if b.cdr is NIL: raise SchemeError("malformed let binding: no init")
                        if not (isinstance(b.cdr, Pair) and b.cdr.cdr is NIL): raise SchemeError("malformed let binding")
                        init_vals.append(eval_expr(b.cdr.car, env, output))
                    new_env = Environment(env)
                    for vn, iv in zip(var_names, init_vals): new_env.define(vn, iv)
                    idefs = scan_internal_defines(body)
                    for d in idefs: new_env.define(d, UNASSIGNED)
                    for form in body[:-1]: eval_expr(form, new_env, output)
                    expr = body[-1]; env = new_env; continue

            if hn == 'let*':
                rest = expr.cdr
                if rest is NIL: raise SchemeError("malformed let*")
                bindings = to_list(rest.car)
                body = to_list(rest.cdr)
                if len(body) == 0: raise SchemeError("malformed let*: empty body")
                new_env = Environment(env)
                for b in bindings:
                    if not isinstance(b, Pair) or not isinstance(b.car, Symbol): raise SchemeError("malformed let* binding")
                    if b.cdr is NIL: raise SchemeError("malformed let* binding: no init")
                    if not (isinstance(b.cdr, Pair) and b.cdr.cdr is NIL): raise SchemeError("malformed let* binding")
                    val = eval_expr(b.cdr.car, new_env, output)
                    new_env.define(b.car, val)
                idefs = scan_internal_defines(body)
                for d in idefs: new_env.define(d, UNASSIGNED)
                for form in body[:-1]: eval_expr(form, new_env, output)
                expr = body[-1]; env = new_env; continue

            if hn == 'letrec':
                rest = expr.cdr
                if rest is NIL: raise SchemeError("malformed letrec")
                bindings = to_list(rest.car)
                body = to_list(rest.cdr)
                if len(body) == 0: raise SchemeError("malformed letrec: empty body")
                new_env = Environment(env)
                for b in bindings:
                    if not isinstance(b, Pair) or not isinstance(b.car, Symbol): raise SchemeError("malformed letrec binding")
                    if b.cdr is NIL: raise SchemeError("malformed letrec binding: no init")
                    if not (isinstance(b.cdr, Pair) and b.cdr.cdr is NIL): raise SchemeError("malformed letrec binding")
                    new_env.define(b.car, UNASSIGNED)
                idefs = scan_internal_defines(body)
                for d in idefs: new_env.define(d, UNASSIGNED)
                for b in bindings:
                    val = eval_expr(b.cdr.car, new_env, output)
                    new_env.define(b.car, val)
                for form in body[:-1]: eval_expr(form, new_env, output)
                expr = body[-1]; env = new_env; continue

            if hn == 'apply':
                args = to_list(expr.cdr)
                if len(args) < 2: raise SchemeError("apply requires at least 2 arguments")
                f = eval_expr(args[0], env, output)
                rest_args = []
                for a in args[1:-1]: rest_args.append(eval_expr(a, env, output))
                lst = eval_expr(args[-1], env, output)
                if not is_proper_list(lst): raise SchemeError("apply: last argument must be a proper list")
                final_args = rest_args + list_to_python(lst)
                # Tail call
                if isinstance(f, Builtin): return f.fn(final_args)
                if isinstance(f, Closure):
                    call_env = Environment(f.env)
                    _bind_formals(f.formals, final_args, call_env)
                    idefs = scan_internal_defines(f.body)
                    for d in idefs: call_env.define(d, UNASSIGNED)
                    for form in f.body[:-1]: eval_expr(form, call_env, output)
                    expr = f.body[-1]; env = call_env; continue
                raise SchemeError("apply: not a procedure")

        # Application
        proc = eval_expr(head, env, output)
        args = []
        cur = expr.cdr
        while isinstance(cur, Pair):
            args.append(eval_expr(cur.car, env, output))
            cur = cur.cdr
        if cur is not NIL: raise SchemeError("dotted form used as application")

        if isinstance(proc, Builtin): return proc.fn(args)
        if isinstance(proc, Closure):
            call_env = Environment(proc.env)
            _bind_formals(proc.formals, args, call_env)
            idefs = scan_internal_defines(proc.body)
            for d in idefs: call_env.define(d, UNASSIGNED)
            for form in proc.body[:-1]: eval_expr(form, call_env, output)
            expr = proc.body[-1]; env = call_env; continue
        raise SchemeError("not a procedure")

def _bind_formals(formals, args, env):
    if isinstance(formals, Symbol):
        env.define(formals, python_to_list(args))
        return
    if formals is NIL:
        if len(args) != 0: raise SchemeError("wrong number of arguments")
        return
    # Pair chain, possibly dotted
    cur = formals; i = 0
    while isinstance(cur, Pair):
        if i >= len(args): raise SchemeError("too few arguments")
        env.define(cur.car, args[i]); i += 1
        cur = cur.cdr
    if isinstance(cur, Symbol):
        env.define(cur, python_to_list(args[i:]))
    elif cur is NIL:
        if i != len(args): raise SchemeError("too many arguments")
    else:
        raise SchemeError("malformed formals")

# === Builtins ===

def make_global_env(output):
    env = Environment()

    def check_ints(args):
        for a in args:
            if isinstance(a, bool) or not isinstance(a, int):
                raise SchemeError("expected integer")

    def b_plus(args):
        check_ints(args); return sum(args) if args else 0

    def b_mul(args):
        check_ints(args)
        r = 1
        for a in args: r *= a
        return r

    def b_sub(args):
        check_ints(args)
        if len(args) == 0: raise SchemeError("- requires at least 1 argument")
        if len(args) == 1: return -args[0]
        r = args[0]
        for a in args[1:]: r -= a
        return r

    def _quotient(a, b):
        if b == 0: raise SchemeError("division by zero")
        q = a // b
        if a % b != 0 and (a < 0) != (b < 0): q += 1
        return q

    def b_quotient(args):
        check_ints(args)
        if len(args) != 2: raise SchemeError("quotient requires 2 arguments")
        return _quotient(args[0], args[1])

    def b_remainder(args):
        check_ints(args)
        if len(args) != 2: raise SchemeError("remainder requires 2 arguments")
        if args[1] == 0: raise SchemeError("division by zero")
        return args[0] - args[1] * _quotient(args[0], args[1])

    def b_modulo(args):
        check_ints(args)
        if len(args) != 2: raise SchemeError("modulo requires 2 arguments")
        if args[1] == 0: raise SchemeError("division by zero")
        return args[0] % args[1]

    def _make_cmp(op):
        def fn(args):
            check_ints(args)
            if len(args) == 0: raise SchemeError("comparison requires at least 1 argument")
            for i in range(len(args) - 1):
                if not op(args[i], args[i+1]): return False
            return True
        return fn

    def b_cons(args):
        if len(args) != 2: raise SchemeError("cons requires 2 arguments")
        return Pair(args[0], args[1])

    def b_car(args):
        if len(args) != 1: raise SchemeError("car requires 1 argument")
        if not isinstance(args[0], Pair): raise SchemeError("car: not a pair")
        return args[0].car

    def b_cdr(args):
        if len(args) != 1: raise SchemeError("cdr requires 1 argument")
        if not isinstance(args[0], Pair): raise SchemeError("cdr: not a pair")
        return args[0].cdr

    def b_list(args): return python_to_list(args)

    def b_null(args):
        if len(args) != 1: raise SchemeError("null? requires 1 argument")
        return args[0] is NIL

    def b_pair(args):
        if len(args) != 1: raise SchemeError("pair? requires 1 argument")
        return isinstance(args[0], Pair)

    def b_list_p(args):
        if len(args) != 1: raise SchemeError("list? requires 1 argument")
        return is_proper_list(args[0])

    def b_length(args):
        if len(args) != 1: raise SchemeError("length requires 1 argument")
        n = 0; cur = args[0]
        while isinstance(cur, Pair): n += 1; cur = cur.cdr
        if cur is not NIL: raise SchemeError("length: not a proper list")
        return n

    def b_append(args):
        if len(args) == 0: return NIL
        if len(args) == 1: return args[0]
        result = args[-1]
        for i in range(len(args) - 2, -1, -1):
            cur = args[i]
            if not is_proper_list(cur): raise SchemeError("append: not a proper list")
            elems = []
            while isinstance(cur, Pair): elems.append(cur.car); cur = cur.cdr
            for e in reversed(elems): result = Pair(e, result)
        return result

    def b_reverse(args):
        if len(args) != 1: raise SchemeError("reverse requires 1 argument")
        result = NIL; cur = args[0]
        while isinstance(cur, Pair): result = Pair(cur.car, result); cur = cur.cdr
        if cur is not NIL: raise SchemeError("reverse: not a proper list")
        return result

    def b_apply(args):
        if len(args) < 2: raise SchemeError("apply requires at least 2 arguments")
        f = args[0]; lst = args[-1]
        if not is_proper_list(lst): raise SchemeError("apply: last argument must be a proper list")
        final = args[1:-1] + list_to_python(lst)
        if isinstance(f, Builtin): return f.fn(final)
        if isinstance(f, Closure):
            call_env = Environment(f.env)
            _bind_formals(f.formals, final, call_env)
            idefs = scan_internal_defines(f.body)
            for d in idefs: call_env.define(d, UNASSIGNED)
            r = UNSPECIFIED
            for form in f.body: r = eval_expr(form, call_env, output)
            return r
        raise SchemeError("apply: not a procedure")

    def b_eq(args):
        if len(args) != 2: raise SchemeError("eq? requires 2 arguments")
        a, b = args
        if isinstance(a, bool) or isinstance(b, bool): return a is b
        if isinstance(a, int) and isinstance(b, int): return a == b
        if isinstance(a, Symbol) and isinstance(b, Symbol): return a is b
        return a is b

    def b_equal(args):
        if len(args) != 2: raise SchemeError("equal? requires 2 arguments")
        return scheme_equal(args[0], args[1])

    def b_not(args):
        if len(args) != 1: raise SchemeError("not requires 1 argument")
        return args[0] is False

    def b_number_p(args):
        if len(args) != 1: raise SchemeError("number? requires 1 argument")
        return isinstance(args[0], int) and not isinstance(args[0], bool)

    def b_symbol_p(args):
        if len(args) != 1: raise SchemeError("symbol? requires 1 argument")
        return isinstance(args[0], Symbol)

    def b_string_p(args):
        if len(args) != 1: raise SchemeError("string? requires 1 argument")
        return isinstance(args[0], str)

    def b_procedure_p(args):
        if len(args) != 1: raise SchemeError("procedure? requires 1 argument")
        return isinstance(args[0], (Closure, Builtin))

    def b_string_append(args):
        for a in args:
            if not isinstance(a, str): raise SchemeError("string-append: not a string")
        return ''.join(args)

    def b_display(args):
        if len(args) != 1: raise SchemeError("display requires 1 argument")
        output.append(display_repr(args[0], False))
        return UNSPECIFIED

    def b_newline(args):
        if len(args) != 0: raise SchemeError("newline requires 0 arguments")
        output.append('\n')
        return UNSPECIFIED

    def b_error(args):
        if len(args) < 1: raise SchemeError("error requires at least 1 argument")
        msg = args[0]
        if not isinstance(msg, str): raise SchemeError("error: first argument must be a string")
        parts = [msg]
        for irr in args[1:]:
            parts.append(' '); parts.append(display_repr(irr, True))
        raise SchemeError(''.join(parts))

    def b_number_to_string(args):
        if len(args) < 1 or len(args) > 2: raise SchemeError("number->string: wrong arity")
        check_ints([args[0]])
        radix = 10
        if len(args) == 2:
            check_ints([args[1]])
            radix = args[1]
            if radix not in (2, 8, 10, 16): raise SchemeError("number->string: bad radix")
        return int_to_str(args[0], radix)

    builtins = [
        ('+', b_plus), ('*', b_mul), ('-', b_sub),
        ('quotient', b_quotient), ('remainder', b_remainder), ('modulo', b_modulo),
        ('=', _make_cmp(lambda a, b: a == b)),
        ('<', _make_cmp(lambda a, b: a < b)),
        ('>', _make_cmp(lambda a, b: a > b)),
        ('<=', _make_cmp(lambda a, b: a <= b)),
        ('>=', _make_cmp(lambda a, b: a >= b)),
        ('cons', b_cons), ('car', b_car), ('cdr', b_cdr), ('list', b_list),
        ('null?', b_null), ('pair?', b_pair), ('list?', b_list_p),
        ('length', b_length), ('append', b_append), ('reverse', b_reverse),
        ('apply', b_apply),
        ('eq?', b_eq), ('equal?', b_equal), ('not', b_not),
        ('number?', b_number_p), ('symbol?', b_symbol_p), ('string?', b_string_p),
        ('procedure?', b_procedure_p), ('string-append', b_string_append),
        ('display', b_display), ('newline', b_newline), ('error', b_error),
        ('number->string', b_number_to_string),
    ]
    for name, fn in builtins:
        env.define(intern(name), Builtin(name, fn))
    return env

# === Main API ===

def run(source):
    output = []
    try:
        forms = read_all(source)
        env = make_global_env(output)
        for form in forms:
            eval_expr(form, env, output)
    except SchemeError as e:
        e.output = ''.join(output)
        raise
    except RecursionError:
        raise SchemeError("stack overflow", ''.join(output))
    except Exception as e:
        raise SchemeError(str(e), ''.join(output))
    return ''.join(output)

def _run_in_thread(source):
    result = [None]
    def target():
        try:
            result[0] = ('ok', run(source))
        except SchemeError as e:
            result[0] = ('err', e)
        except Exception as e:
            result[0] = ('err', SchemeError(str(e), ''))
    t = threading.Thread(target=target)
    t.start()
    t.join()
    if result[0][0] == 'err':
        raise result[0][1]
    return result[0][1]

# Override run to use thread for larger stack
_run_impl = run
def run(source):
    old = sys.getrecursionlimit()
    sys.setrecursionlimit(200000)
    try:
        return _run_in_thread(source)
    finally:
        sys.setrecursionlimit(old)
