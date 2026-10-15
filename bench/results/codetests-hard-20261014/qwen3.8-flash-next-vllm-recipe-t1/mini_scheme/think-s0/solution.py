import sys
import re

sys.set_int_max_str_digits(0)
sys.setrecursionlimit(200000)

class SchemeError(Exception):
    def __init__(self, message, output=''):
        super().__init__(message)
        self.output = output

# ---------- Data types ----------

class Symbol:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name
    def __repr__(self):
        return f"Symbol({self.name})"
    def __eq__(self, other):
        return isinstance(other, Symbol) and self.name == other.name
    def __hash__(self):
        return hash(self.name)

class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, a, d):
        self.car = a
        self.cdr = d

class _Nil:
    __slots__ = ()
    def __repr__(self): return "()"
    def __bool__(self): return True
NIL = _Nil()

class _Unspecified:
    __slots__ = ()
    def __repr__(self): return "#<unspecified>"
UNSPECIFIED = _Unspecified()

class _Uninitialized:
    __slots__ = ()
UNINITIALIZED = _Uninitialized()

class Cell:
    __slots__ = ('value',)
    def __init__(self, value=UNINITIALIZED):
        self.value = value

class Frame:
    __slots__ = ('vars',)
    def __init__(self):
        self.vars = {}

class Env:
    __slots__ = ('frame', 'parent')
    def __init__(self, frame, parent):
        self.frame = frame
        self.parent = parent

class Closure:
    __slots__ = ('params', 'rest', 'body', 'env')
    def __init__(self, params, rest, body, env):
        self.params = params  # list of symbol names
        self.rest = rest      # symbol name or None
        self.body = body      # list of Scheme forms
        self.env = env

class Builtin:
    __slots__ = ('name', 'func')
    def __init__(self, name, func):
        self.name = name
        self.func = func

# ---------- Reader ----------

class Reader:
    def __init__(self, source):
        self.source = source
        self.pos = 0
        self.length = len(source)

    def skip_ws(self):
        s = self.source
        while self.pos < self.length:
            ch = s[self.pos]
            if ch in ' \t\n\r':
                self.pos += 1
            elif ch == ';':
                while self.pos < self.length and s[self.pos] != '\n':
                    self.pos += 1
            else:
                break

    def peek(self):
        self.skip_ws()
        if self.pos >= self.length:
            return None
        return self.source[self.pos]

    def read_all(self):
        forms = []
        while True:
            form = self.read_datum()
            if form is None:
                break
            forms.append(form)
        return forms

    def read_datum(self):
        self.skip_ws()
        if self.pos >= self.length:
            return None
        ch = self.source[self.pos]
        if ch == '(':
            self.pos += 1
            return self.read_list()
        elif ch == ')':
            raise SchemeError("unexpected )")
        elif ch == "'":
            self.pos += 1
            inner = self.read_datum()
            if inner is None:
                raise SchemeError("quote not followed by datum")
            return Pair(Symbol('quote'), Pair(inner, NIL))
        elif ch == '"':
            return self.read_string()
        else:
            return self.read_token()

    def read_list(self):
        elements = []
        while True:
            self.skip_ws()
            if self.pos >= self.length:
                raise SchemeError("unbalanced (")
            if self.source[self.pos] == ')':
                self.pos += 1
                result = NIL
                for elem in reversed(elements):
                    result = Pair(elem, result)
                return result
            item = self.read_datum()
            if item is None:
                raise SchemeError("unbalanced (")
            if isinstance(item, Symbol) and item.name == '.':
                if not elements:
                    raise SchemeError("dot at start of list")
                rest = self.read_datum()
                if rest is None:
                    raise SchemeError("dot not followed by datum")
                self.skip_ws()
                if self.pos >= self.length or self.source[self.pos] != ')':
                    raise SchemeError("expected ) after dotted rest")
                self.pos += 1
                result = rest
                for elem in reversed(elements):
                    result = Pair(elem, result)
                return result
            elements.append(item)

    def read_string(self):
        self.pos += 1
        chars = []
        while self.pos < self.length:
            ch = self.source[self.pos]
            if ch == '"':
                self.pos += 1
                return ''.join(chars)
            elif ch == '\\':
                self.pos += 1
                if self.pos >= self.length:
                    raise SchemeError("unterminated string")
                esc = self.source[self.pos]
                if esc == '"':
                    chars.append('"')
                elif esc == '\\':
                    chars.append('\\')
                elif esc == 'n':
                    chars.append('\n')
                else:
                    raise SchemeError("invalid escape")
                self.pos += 1
            else:
                chars.append(ch)
                self.pos += 1
        raise SchemeError("unterminated string")

    def read_token(self):
        start = self.pos
        while self.pos < self.length:
            ch = self.source[self.pos]
            if ch in ' \t\n\r()";\'':
                break
            self.pos += 1
        token = self.source[start:self.pos]
        if not token:
            raise SchemeError("read error")
        return self._parse_atom(token)

    def _parse_atom(self, token):
        if token.startswith('#'):
            if token == '#t':
                return True
            if token == '#f':
                return False
            raise SchemeError(f"invalid token: {token}")
        if re.fullmatch(r'[+-]?[0-9]+', token):
            return int(token)
        return Symbol(token)

# ---------- Utilities ----------

def is_true(v):
    return v is not False

def car(x):
    if isinstance(x, Pair):
        return x.car
    raise SchemeError("car: not a pair")

def cdr(x):
    if isinstance(x, Pair):
        return x.cdr
    raise SchemeError("cdr: not a pair")

def is_pair(x):
    return isinstance(x, Pair)

def is_proper_list(x):
    seen = set()
    while isinstance(x, Pair):
        if id(x) in seen:
            return False
        seen.add(id(x))
        x = x.cdr
    return x is NIL

def list_to_py(lst):
    result = []
    while isinstance(lst, Pair):
        result.append(lst.car)
        lst = lst.cdr
    return result

def py_to_list(items):
    result = NIL
    for item in reversed(items):
        result = Pair(item, result)
    return result

# ---------- Display / Write ----------

def format_value(val, write_mode=False):
    parts = []
    _format_iterative(val, parts, write_mode)
    return ''.join(parts)

def _format_iterative(val, parts, write_mode):
    if isinstance(val, bool):
        parts.append('#t' if val else '#f')
    elif isinstance(val, int):
        parts.append(str(val))
    elif isinstance(val, str):
        if write_mode:
            parts.append('"')
            for c in val:
                if c == '"':
                    parts.append('\\"')
                elif c == '\\':
                    parts.append('\\\\')
                elif c == '\n':
                    parts.append('\\n')
                else:
                    parts.append(c)
            parts.append('"')
        else:
            parts.append(val)
    elif isinstance(val, Symbol):
        parts.append(val.name)
    elif val is NIL:
        parts.append('()')
    elif isinstance(val, Pair):
        parts.append('(')
        first = True
        current = val
        while True:
            if not first:
                parts.append(' ')
            _format_iterative(current.car, parts, write_mode)
            rest = current.cdr
            if rest is NIL:
                break
            if not isinstance(rest, Pair):
                parts.append(' . ')
                _format_iterative(rest, parts, write_mode)
                break
            current = rest
            first = False
        parts.append(')')
    elif isinstance(val, (Closure, Builtin)):
        parts.append('#<procedure>')
    elif val is UNSPECIFIED:
        parts.append('')
    elif val is UNINITIALIZED:
        parts.append('')
    else:
        parts.append(str(val))

# ---------- Environment ----------

def make_global_env():
    env = Env(Frame(), None)
    _install_builtins(env)
    return env

def lookup(name, env):
    e = env
    while e is not None:
        if name in e.frame.vars:
            cell = e.frame.vars[name]
            if cell.value is UNINITIALIZED:
                raise SchemeError(f"unbound variable: {name}")
            return cell.value
        e = e.parent
    raise SchemeError(f"unbound variable: {name}")

def define_var(name, value, env):
    env.frame.vars[name] = Cell(value)

def set_var(name, value, env):
    e = env
    while e is not None:
        if name in e.frame.vars:
            cell = e.frame.vars[name]
            if cell.value is UNINITIALIZED:
                raise SchemeError(f"unbound variable: {name}")
            cell.value = value
            return
        e = e.parent
    raise SchemeError(f"unbound variable: {name}")

# ---------- Trampoline ----------

class _Value:
    __slots__ = ('v',)
    def __init__(self, v): self.v = v

class _Eval:
    __slots__ = ('expr', 'env')
    def __init__(self, expr, env): self.expr = expr; self.env = env

class _Apply:
    __slots__ = ('proc', 'args')
    def __init__(self, proc, args): self.proc = proc; self.args = args

def run_expr(expr, env, output):
    while True:
        r = _eval_step(expr, env, output)
        if isinstance(r, _Value):
            return r.v
        elif isinstance(r, _Eval):
            expr, env = r.expr, r.env
        elif isinstance(r, _Apply):
            proc, args = r.proc, r.args
            if isinstance(proc, Closure):
                expr, env = _setup_closure_call(proc, args)
            elif isinstance(proc, Builtin):
                return proc.func(args, output)
            else:
                raise SchemeError("not a procedure")

def _setup_closure_call(closure, args):
    n_fixed = len(closure.params)
    if closure.rest is not None:
        if len(args) < n_fixed:
            raise SchemeError(f"procedure called with too few arguments: expected at least {n_fixed}, got {len(args)}")
    else:
        if len(args) != n_fixed:
            raise SchemeError(f"procedure called with wrong number of arguments: expected {n_fixed}, got {len(args)}")
    frame = Frame()
    for i, name in enumerate(closure.params):
        frame.vars[name] = Cell(args[i])
    if closure.rest is not None:
        frame.vars[closure.rest] = Cell(py_to_list(args[n_fixed:]))
    env = Env(frame, closure.env)
    # Handle internal definitions in body
    body = closure.body
    body_env = _setup_body_env(body, env, frame)
    # Evaluate body: all but last are non-tail
    forms = body
    for i in range(len(forms) - 1):
        run_expr(forms[i], body_env, output)  # Wait, we don't have output here
    # Actually need to pass output... let me restructure
    # Return last form as tail
    return forms[-1], body_env

# Hmm, I need output for the non-tail body forms. Let me restructure.

# Actually let me redo this. The _setup_closure_call needs to set up the env
# and return the last body form + env for the trampoline. But non-tail body forms
# need to be evaluated. Let me make this work differently.

# Let me use a different approach: instead of separating setup from evaluation,
# I'll have the closure call setup create the env and put ALL body forms (with
# defines) into a sequence that the trampoline processes.

# Actually the simplest: make _setup_closure_call just return (expr, env) where
# expr is a synthesized begin or the first form, and the trampoline handles the rest.
# But that doesn't work for multi-form bodies.

# OK, I'll just pass output through. Let me restructure the trampoline.

def run_expr(expr, env, output):
    while True:
        r = _eval_step(expr, env, output)
        if isinstance(r, _Value):
            return r.v
        elif isinstance(r, _Eval):
            expr, env = r.expr, r.env
        elif isinstance(r, _Apply):
            proc, args = r.proc, r.args
            if isinstance(proc, Closure):
                expr, env = _setup_closure_call(proc, args, output)
            elif isinstance(proc, Builtin):
                return proc.func(args, output)
            else:
                raise SchemeError("not a procedure")

def _setup_body(forms, env, frame):
    """Set up letrec* semantics for internal definitions in a body.
    Returns new env (possibly same as env if no internal defines)."""
    define_names = []
    for form in forms:
        if _is_define(form):
            nm = _define_name(form)
            if nm is not None:
                define_names.append(nm)
    if not define_names:
        return env
    # Create new frame (or add to existing)
    new_env = Env(Frame(), env.parent) if frame is None else env
    # Actually we want the defines in the SAME frame as params if possible
    # Let's create a new env layer for defines if needed
    # The defines go in the same frame as the params (frame)
    if frame is not None:
        for nm in define_names:
            if nm not in frame.vars:
                frame.vars[nm] = Cell(UNINITIALIZED)
        return env
    else:
        # For let/let*/letrec: defines go in the binding frame
        for nm in define_names:
            if nm not in env.frame.vars:
                env.frame.vars[nm] = Cell(UNINITIALIZED)
        return env

def _setup_closure_call(closure, args, output):
    n_fixed = len(closure.params)
    if closure.rest is not None:
        if len(args) < n_fixed:
            raise SchemeError("too few arguments")
    else:
        if len(args) != n_fixed:
            raise SchemeError("wrong number of arguments")
    frame = Frame()
    for i, name in enumerate(closure.params):
        frame.vars[name] = Cell(args[i])
    if closure.rest is not None:
        frame.vars[closure.rest] = Cell(py_to_list(args[n_fixed:]))
    env = Env(frame, closure.env)
    body = closure.body
    _setup_body(body, env, frame)
    # Evaluate all but last form (non-tail), execute defines in place
    _exec_body_non_tail(body, env, output)
    # Return last form for tail evaluation
    return body[-1], env

def _exec_body_non_tail(forms, env, output):
    for i in range(len(forms) - 1):
        form = forms[i]
        if _is_define(form):
            _exec_define(form, env, output)
        else:
            run_expr(form, env, output)

def _is_define(form):
    return isinstance(form, Pair) and isinstance(form.car, Symbol) and form.car.name == 'define'

def _define_name(form):
    target = form.cdr.car
    if isinstance(target, Symbol):
        return target.name
    if isinstance(target, Pair) and isinstance(target.car, Symbol):
        return target.car.name
    return None

def _exec_define(form, env, output):
    target = form.cdr.car
    if isinstance(target, Symbol):
        val_expr = form.cdr.cdr.car
        val = run_expr(val_expr, env, output)
        name = target.name
        if name in env.frame.vars:
            env.frame.vars[name].value = val
        else:
            env.frame.vars[name] = Cell(val)
    elif isinstance(target, Pair):
        if not isinstance(target.car, Symbol):
            raise SchemeError("define: malformed")
        name = target.car.name
        formals = target.cdr
        body = list_to_py(form.cdr.cdr)
        if not body:
            raise SchemeError("define: empty body")
        params, rest = _parse_formals(formals)
        closure = Closure(params, rest, body, env)
        if name in env.frame.vars:
            env.frame.vars[name].value = closure
        else:
            env.frame.vars[name] = Cell(closure)
    else:
        raise SchemeError("define: malformed")

def _parse_formals(formals):
    if formals is NIL:
        return [], None
    if isinstance(formals, Symbol):
        return [], formals.name
    if not isinstance(formals, Pair):
        raise SchemeError("malformed formals")
    fixed = []
    current = formals
    while isinstance(current, Pair):
        if not isinstance(current.car, Symbol):
            raise SchemeError("malformed formals")
        fixed.append(current.car.name)
        current = current.cdr
    if current is NIL:
        return fixed, None
    elif isinstance(current, Symbol):
        return fixed, current.name
    else:
        raise SchemeError("malformed formals")

# ---------- Core evaluator ----------

SPECIAL_FORMS = {'quote','if','lambda','define','set!','begin','cond','and','or','let','let*','letrec','apply'}

def _eval_step(expr, env, output):
    # Self-evaluating
    if isinstance(expr, bool):
        return _Value(expr)
    if isinstance(expr, int):
        return _Value(expr)
    if isinstance(expr, str):
        return _Value(expr)
    if expr is NIL:
        raise SchemeError("cannot evaluate ()")
    if isinstance(expr, Symbol):
        return _Value(lookup(expr.name, env))
    if expr is UNSPECIFIED:
        return _Value(UNSPECIFIED)

    if not isinstance(expr, Pair):
        raise SchemeError("cannot evaluate")

    # List form
    head = expr.car
    if isinstance(head, Symbol):
        name = head.name
        if name in SPECIAL_FORMS:
            return _eval_special(name, expr, env, output)

    # Procedure application (non-special)
    # Evaluate operator
    proc = run_expr(head, env, output)
    # Evaluate operands left to right
    args = []
    current = expr.cdr
    while isinstance(current, Pair):
        args.append(run_expr(current.car, env, output))
        current = current.cdr
    if not (current is NIL):
        raise SchemeError("malformed application (dotted form)")
    # Check procedure
    if not isinstance(proc, (Closure, Builtin)):
        raise SchemeError("not a procedure")
    # Call: this is NOT in tail position, so use run_expr for non-tail
    # Actually in this code path, we ARE at whatever position the caller is.
    # The caller decides. We return an _Apply for the trampoline to handle.
    return _Apply(proc, args)

def _eval_special(name, expr, env, output):
    if name == 'quote':
        rest = expr.cdr
        if not isinstance(rest, Pair) or not isinstance(rest.cdr, _Nil):
            raise SchemeError("malformed quote")
        return _Value(rest.car)

    elif name == 'if':
        rest = expr.cdr
        if not isinstance(rest, Pair):
            raise SchemeError("malformed if")
        test_expr = rest.car
        then_part = rest.cdr
        if not isinstance(then_part, Pair):
            raise SchemeError("malformed if")
        then_expr = then_part.car
        else_part = then_part.cdr
        # Evaluate test (non-tail)
        test_val = run_expr(test_expr, env, output)
        if is_true(test_val):
            return _Eval(then_expr, env)
        else:
            if else_part is NIL:
                return _Value(UNSPECIFIED)
            if not isinstance(else_part, Pair):
                raise SchemeError("malformed if")
            else_expr = else_part.car
            if else_part.cdr is not NIL:
                # more than 3 args to if - ignore extras? or error?
                pass
            return _Eval(else_expr, env)

    elif name == 'lambda':
        rest = expr.cdr
        if not isinstance(rest, Pair):
            raise SchemeError("malformed lambda")
        formals = rest.car
        body = list_to_py(rest.cdr)
        if not body:
            raise SchemeError("lambda: empty body")
        params, param_rest = _parse_formals(formals)
        closure = Closure(params, param_rest, body, env)
        return _Value(closure)

    elif name == 'define':
        rest = expr.cdr
        if not isinstance(rest, Pair):
            raise SchemeError("malformed define")
        _exec_define(expr, env, output)
        return _Value(UNSPECIFIED)

    elif name == 'set!':
        rest = expr.cdr
        if not isinstance(rest, Pair):
            raise SchemeError("malformed set!")
        target = rest.car
        if not isinstance(target, Symbol):
            raise SchemeError("set!: not a variable")
        val_expr = rest.cdr
        if not isinstance(val_expr, Pair):
            raise SchemeError("malformed set!")
        val = run_expr(val_expr.car, env, output)
        set_var(target.name, val, env)
        return _Value(UNSPECIFIED)

    elif name == 'begin':
        forms = list_to_py(expr.cdr)
        if not forms:
            raise SchemeError("malformed begin")
        for i in range(len(forms) - 1):
            run_expr(forms[i], env, output)
        return _Eval(forms[-1], env)

    elif name == 'cond':
        clauses = list_to_py(expr.cdr)
        if not clauses:
            return _Value(UNSPECIFIED)
        return _eval_cond(clauses, env, output)

    elif name == 'and':
        items = list_to_py(expr.cdr)
        if not items:
            return _Value(True)
        for i in range(len(items) - 1):
            val = run_expr(items[i], env, output)
            if not is_true(val):
                return _Value(False)
        return _Eval(items[-1], env)

    elif name == 'or':
        items = list_to_py(expr.cdr)
        if not items:
            return _Value(False)
        for i in range(len(items) - 1):
            val = run_expr(items[i], env, output)
            if is_true(val):
                return _Value(val)
        return _Eval(items[-1], env)

    elif name == 'let':
        return _eval_let(expr, env, output, 'let')

    elif name == 'let*':
        return _eval_let(expr, env, output, 'let*')

    elif name == 'letrec':
        return _eval_let(expr, env, output, 'letrec')

    elif name == 'apply':
        return _eval_apply(expr, env, output)

    return None  # not a special form, shouldn't reach here

def _eval_cond(clauses, env, output):
    for i, clause in enumerate(clauses):
        if not isinstance(clause, Pair):
            raise SchemeError("malformed cond clause")
        test = clause.car
        # Check for else
        if isinstance(test, Symbol) and test.name == 'else':
            body = list_to_py(clause.cdr)
            if not body:
                return _Value(UNSPECIFIED)
            for j in range(len(body) - 1):
                run_expr(body[j], env, output)
            return _Eval(body[-1], env)
        # Evaluate test
        test_val = run_expr(test, env, output)
        if is_true(test_val):
            body = list_to_py(clause.cdr)
            if not body:
                return _Value(test_val)
            for j in range(len(body) - 1):
                run_expr(body[j], env, output)
            return _Eval(body[-1], env)
    return _Value(UNSPECIFIED)

def _eval_let(expr, env, output, kind):
    rest = expr.cdr
    if not isinstance(rest, Pair):
        raise SchemeError(f"malformed {kind}")
    first = rest.car
    # Check for named let: (let name ((v init)...) body...)
    if kind == 'let' and isinstance(first, Symbol):
        return _eval_named_let(expr, env, output)
    # bindings
    bindings = first
    body = list_to_py(rest.cdr)
    if not body:
        raise SchemeError("let: empty body")
    if not isinstance(bindings, (Pair, _Nil)):
        raise SchemeError(f"malformed {kind}")
    # Parse bindings
    bind_list = []
    b = bindings
    while isinstance(b, Pair):
        binding = b.car
        if not isinstance(binding, Pair) or not isinstance(binding.cdr, Pair):
            raise SchemeError(f"malformed {kind} binding")
        v = binding.car
        if not isinstance(v, Symbol):
            raise SchemeError(f"malformed {kind} binding variable")
        init = binding.cdr.car
        bind_list.append((v.name, init))
        b = b.cdr
    if not (b is NIL):
        raise SchemeError(f"malformed {kind} bindings")

    if kind == 'let':
        # Evaluate all inits in outer scope
        init_vals = []
        for name, init in bind_list:
            val = run_expr(init, env, output)
            init_vals.append((name, val))
        frame = Frame()
        for name, val in init_vals:
            frame.vars[name] = Cell(val)
        let_env = Env(frame, env)
        _setup_body(body, let_env, frame)
        _exec_body_non_tail(body, let_env, output)
        return _Eval(body[-1], let_env)

    elif kind == 'let*':
        # Sequential
        current_env = env
        frame = Frame()
        current_env = Env(frame, env)
        for name, init in bind_list:
            val = run_expr(init, current_env, output)
            frame.vars[name] = Cell(val)
        _setup_body(body, current_env, frame)
        _exec_body_non_tail(body, current_env, output)
        return _Eval(body[-1], current_env)

    elif kind == 'letrec':
        frame = Frame()
        for name, init in bind_list:
            frame.vars[name] = Cell(UNINITIALIZED)
        letrec_env = Env(frame, env)
        for name, init in bind_list:
            val = run_expr(init, letrec_env, output)
            frame.vars[name].value = val
        _setup_body(body, letrec_env, frame)
        _exec_body_non_tail(body, letrec_env, output)
        return _Eval(body[-1], letrec_env)

def _eval_named_let(expr, env, output):
    # (let name ((v init)...) body...)
    rest = expr.cdr
    name_sym = rest.car
    name = name_sym.name
    bindings = rest.cdr.car
    body = list_to_py(rest.cdr.cdr)
    if not isinstance(bindings, (Pair, _Nil)):
        raise SchemeError("malformed named let")
    if not body:
        raise SchemeError("named let: empty body")

    # Parse bindings
    param_names = []
    init_exprs = []
    b = bindings
    while isinstance(b, Pair):
        binding = b.car
        if not isinstance(binding, Pair) or not isinstance(binding.cdr, Pair):
            raise SchemeError("malformed named let binding")
        v = binding.car
        if not isinstance(v, Symbol):
            raise SchemeError("malformed named let binding variable")
        param_names.append(v.name)
        init_exprs.append(binding.cdr.car)
        b = b.cdr
    if not (b is NIL):
        raise SchemeError("malformed named let bindings")

    # Evaluate inits in outer scope
    init_vals = []
    for ie in init_exprs:
        init_vals.append(run_expr(ie, env, output))

    # Create letrec-like binding for the procedure
    frame = Frame()
    proc_cell = Cell(UNINITIALIZED)
    frame.vars[name] = proc_cell
    let_env = Env(frame, env)

    # Create the procedure
    proc_cell.value = Closure(param_names, None, body, let_env)

    # Call it with init_vals - this is a tail call
    n = len(param_names)
    if len(init_vals) != n:
        raise SchemeError("named let: wrong number of values")
    new_frame = Frame()
    for i, pname in enumerate(param_names):
        new_frame.vars[pname] = Cell(init_vals[i])
    _setup_body(body, Env(new_frame, let_env), new_frame)
    call_env = Env(new_frame, let_env)
    _setup_body(body, call_env, new_frame)
    _exec_body_non_tail(body, call_env, output)
    return _Eval(body[-1], call_env)

def _eval_apply(expr, env, output):
    # (apply f a ... lst)
    rest = expr.cdr
    if not isinstance(rest, Pair):
        raise SchemeError("apply: too few arguments")
    # Evaluate all arguments
    args = []
    current = rest
    while isinstance(current, Pair):
        args.append(run_expr(current.car, env, output))
        current = current.cdr
    if not (current is NIL):
        raise SchemeError("apply: malformed")
    if len(args) < 2:
        raise SchemeError("apply: too few arguments")
    f = args[0]
    # Last arg is the list to splice
    last = args[-1]
    if not is_proper_list(last):
        raise SchemeError("apply: last argument is not a proper list")
    final_args = args[1:-1] + list_to_py(last)
    if not isinstance(f, (Closure, Builtin)):
        raise SchemeError("apply: not a procedure")
    # Tail call
    return _Apply(f, final_args)

# ---------- Builtins ----------

def _install_builtins(env):
    g = env.frame.vars

    def reg(name, func):
        g[name] = Cell(Builtin(name, func))

    # Arithmetic
    reg('+', lambda args, out: _arith_add(args))
    reg('*', lambda args, out: _arith_mul(args))
    reg('-', lambda args, out: _arith_sub(args))
    reg('quotient', lambda args, out: _arith_quotient(args))
    reg('remainder', lambda args, out: _arith_remainder(args))
    reg('modulo', lambda args, out: _arith_modulo(args))

    reg('=', lambda args, out: _cmp_eq(args))
    reg('<', lambda args, out: _cmp_lt(args))
    reg('>', lambda args, out: _cmp_gt(args))
    reg('<=', lambda args, out: _cmp_le(args))
    reg('>=', lambda args, out: _cmp_ge(args))

    reg('number->string', lambda args, out: _number_to_string(args))

    # Lists and pairs
    reg('cons', lambda args, out: Pair(args[0], args[1]))
    reg('car', lambda args, out: car(args[0]))
    reg('cdr', lambda args, out: cdr(args[0]))
    reg('list', lambda args, out: py_to_list(args))
    reg('null?', lambda args, out: args[0] is NIL)
    reg('pair?', lambda args, out: isinstance(args[0], Pair))
    reg('list?', lambda args, out: is_proper_list(args[0]))
    reg('length', lambda args, out: _length(args[0]))
    reg('append', lambda args, out: _append(args))
    reg('reverse', lambda args, out: _reverse(args[0]))
    reg('apply', lambda args, out: _apply_builtin(args, out))

    # Equality and predicates
    reg('eq?', lambda args, out: _eq(args[0], args[1]))
    reg('equal?', lambda args, out: _equal(args[0], args[1]))
    reg('not', lambda args, out: args[0] is False)
    reg('number?', lambda args, out: isinstance(args[0], int) and not isinstance(args[0], bool))
    reg('symbol?', lambda args, out: isinstance(args[0], Symbol))
    reg('string?', lambda args, out: isinstance(args[0], str))
    reg('procedure?', lambda args, out: isinstance(args[0], (Closure, Builtin)))

    reg('string-append', lambda args, out: _string_append(args))

    # Output
    reg('display', lambda args, out: _display(args[0], out))
    reg('newline', lambda args, out: _newline(out))

    # Error
    reg('error', lambda args, out: _error_proc(args))

    # Check arities in wrappers
    # Redefine with arity checking
    def wrap(name, func, min_a, max_a):
        def wrapper(args, out):
            n = len(args)
            if n < min_a:
                raise SchemeError(f"{name}: too few arguments")
            if max_a is not None and n > max_a:
                raise SchemeError(f"{name}: too many arguments")
            return func(args, out)
        g[name] = Cell(Builtin(name, wrapper))

    wrap('+', _arith_add, 0, None)
    wrap('*', _arith_mul, 0, None)
    wrap('-', _arith_sub, 1, None)
    wrap('quotient', _arith_quotient, 2, 2)
    wrap('remainder', _arith_remainder, 2, 2)
    wrap('modulo', _arith_modulo, 2, 2)
    wrap('=', _cmp_eq, 1, None)
    wrap('<', _cmp_lt, 1, None)
    wrap('>', _cmp_gt, 1, None)
    wrap('<=', _cmp_le, 1, None)
    wrap('>=', _cmp_ge, 1, None)
    wrap('number->string', _number_to_string, 1, 2)

    wrap('cons', lambda a, o: Pair(a[0], a[1]), 2, 2)
    wrap('car', lambda a, o: car(a[0]), 1, 1)
    wrap('cdr', lambda a, o: cdr(a[0]), 1, 1)
    wrap('list', lambda a, o: py_to_list(a), 0, None)
    wrap('null?', lambda a, o: a[0] is NIL, 1, 1)
    wrap('pair?', lambda a, o: isinstance(a[0], Pair), 1, 1)
    wrap('list?', lambda a, o: is_proper_list(a[0]), 1, 1)
    wrap('length', lambda a, o: _length(a[0]), 1, 1)
    wrap('append', lambda a, o: _append(a), 0, None)
    wrap('reverse', lambda a, o: _reverse(a[0]), 1, 1)
    wrap('apply', lambda a, o: _apply_builtin(a, o), 2, None)

    wrap('eq?', lambda a, o: _eq(a[0], a[1]), 2, 2)
    wrap('equal?', lambda a, o: _equal(a[0], a[1]), 2, 2)
    wrap('not', lambda a, o: a[0] is False, 1, 1)
    wrap('number?', lambda a, o: isinstance(a[0], int) and not isinstance(a[0], bool), 1, 1)
    wrap('symbol?', lambda a, o: isinstance(a[0], Symbol), 1, 1)
    wrap('string?', lambda a, o: isinstance(a[0], str), 1, 1)
    wrap('procedure?', lambda a, o: isinstance(a[0], (Closure, Builtin)), 1, 1)

    wrap('string-append', lambda a, o: _string_append(a), 0, None)

    wrap('display', lambda a, o: _display(a[0], o), 1, 1)
    wrap('newline', lambda a, o: _newline(o), 0, 0)

    wrap('error', lambda a, o: _error_proc(a), 1, None)

def _check_ints(args):
    for a in args:
        if isinstance(a, bool) or not isinstance(a, int):
            raise SchemeError("not a number")

def _arith_add(args):
    _check_ints(args)
    s = 0
    for a in args:
        s += a
    return s

def _arith_mul(args):
    _check_ints(args)
    p = 1
    for a in args:
        p *= a
    return p

def _arith_sub(args):
    _check_ints(args)
    if len(args) == 1:
        return -args[0]
    r = args[0]
    for a in args[1:]:
        r -= a
    return r

def _arith_quotient(args):
    _check_ints(args)
    if args[1] == 0:
        raise SchemeError("division by zero")
    a, b = args[0], args[1]
    # Truncate toward zero
    q = abs(a) // abs(b)
    if (a < 0) ^ (b < 0):
        q = -q
    return q

def _arith_remainder(args):
    _check_ints(args)
    if args[1] == 0:
        raise SchemeError("division by zero")
    # Sign of dividend
    return args[0] % abs(args[1]) if args[0] >= 0 else -(abs(args[0]) % abs(args[1]))
    # Actually Python's % already has sign of dividend... no, Python % has sign of divisor.
    # Let me do it manually:
    # remainder = a - b * truncate(a/b)

def _arith_remainder(args):
    _check_ints(args)
    if args[1] == 0:
        raise SchemeError("division by zero")
    a, b = args[0], args[1]
    q = abs(a) // abs(b)
    if (a < 0) ^ (b < 0):
        q = -q
    return a - b * q

def _arith_modulo(args):
    _check_ints(args)
    if args[1] == 0:
        raise SchemeError("division by zero")
    a, b = args[0], args[1]
    # Python's % has sign of divisor, which matches modulo
    return a % b

def _cmp_eq(args):
    _check_ints(args)
    for i in range(len(args)-1):
        if args[i] != args[i+1]:
            return False
    return True

def _cmp_lt(args):
    _check_ints(args)
    for i in range(len(args)-1):
        if args[i] >= args[i+1]:
            return False
    return True

def _cmp_gt(args):
    _check_ints(args)
    for i in range(len(args)-1):
        if args[i] <= args[i+1]:
            return False
    return True

def _cmp_le(args):
    _check_ints(args)
    for i in range(len(args)-1):
        if args[i] > args[i+1]:
            return False
    return True

def _cmp_ge(args):
    _check_ints(args)
    for i in range(len(args)-1):
        if args[i] < args[i+1]:
            return False
    return True

def _number_to_string(args):
    if isinstance(args[0], bool) or not isinstance(args[0], int):
        raise SchemeError("number->string: not a number")
    n = args[0]
    radix = 10
    if len(args) >= 2:
        if isinstance(args[1], bool) or not isinstance(args[1], int):
            raise SchemeError("number->string: invalid radix")
        radix = args[1]
        if radix not in (2, 8, 10, 16):
            raise SchemeError("number->string: invalid radix")
    if n == 0:
        return '0'
    negative = n < 0
    n = abs(n)
    if radix == 10:
        s = str(n)
    else:
        digits = []
        while n:
            d = n % radix
            if radix == 16:
                if d < 10:
                    digits.append(chr(ord('0') + d))
                else:
                    digits.append(chr(ord('a') + d - 10))
            else:
                digits.append(chr(ord('0') + d))
            n //= radix
        s = ''.join(reversed(digits))
    if negative:
        s = '-' + s
    return s

def _length(l):
    if not is_proper_list(l):
        raise SchemeError("length: not a proper list")
    n = 0
    while isinstance(l, Pair):
        n += 1
        l = l.cdr
    return n

def _append(args):
    if not args:
        return NIL
    for i in range(len(args) - 1):
        if not is_proper_list(args[i]):
            raise SchemeError("append: argument is not a proper list")
    # Build result
    result = args[-1]
    for i in range(len(args) - 2, -1, -1):
        items = list_to_py(args[i])
        for item in reversed(items):
            result = Pair(item, result)
    return result

def _reverse(l):
    if not is_proper_list(l):
        raise SchemeError("reverse: not a proper list")
    result = NIL
    while isinstance(l, Pair):
        result = Pair(l.car, result)
        l = l.cdr
    return result

def _apply_builtin(args, out):
    if len(args) < 2:
        raise SchemeError("apply: too few arguments")
    f = args[0]
    last = args[-1]
    if not is_proper_list(last):
        raise SchemeError("apply: last argument is not a proper list")
    final_args = list(args[1:-1]) + list_to_py(last)
    if not isinstance(f, (Closure, Builtin)):
        raise SchemeError("apply: not a procedure")
    return run_expr(Pair(Symbol('##apply##'), py_to_list([f] + final_args)),
                    Env({}, None), out) if False else _call_proc(f, final_args, out)

def _call_proc(f, args, out):
    if isinstance(f, Builtin):
        return f.func(args, out)
    elif isinstance(f, Closure):
        # Use trampoline
        r = _setup_closure_call(f, args, out)
        return run_expr(r[0], r[1], out)
    else:
        raise SchemeError("not a procedure")

def _eq(a, b):
    if isinstance(a, bool) and isinstance(b, bool):
        return a is b
    if isinstance(a, bool) or isinstance(b, bool):
        return False
    if isinstance(a, int) and isinstance(b, int):
        return a == b
    if isinstance(a, bool) or isinstance(b, bool):
        return False
    if isinstance(a, Symbol) and isinstance(b, Symbol):
        return a is b or a.name == b.name
    if a is NIL and b is NIL:
        return True
    # Strings, pairs, procedures: identity
    return a is b

def _equal(a, b):
    if isinstance(a, bool) and isinstance(b, bool):
        return a is b
    if isinstance(a, bool) or isinstance(b, bool):
        return False
    if isinstance(a, int) and isinstance(b, int):
        return a == b
    if isinstance(a, int) or isinstance(b, int):
        return False
    if isinstance(a, Symbol) and isinstance(b, Symbol):
        return a.name == b.name
    if isinstance(a, str) and isinstance(b, str):
        return a == b
    if a is NIL and b is NIL:
        return True
    if isinstance(a, Pair) and isinstance(b, Pair):
        # Iterative to handle long lists
        while True:
            if not _equal(a.car, b.car):
                return False
            a, b = a.cdr, b.cdr
            if isinstance(a, _Nil) and isinstance(b, _Nil):
                return True
            if not (isinstance(a, Pair) and isinstance(b, Pair)):
                return _equal(a, b)
    return a is b

def _string_append(args):
    for a in args:
        if not isinstance(a, str):
            raise SchemeError("string-append: not a string")
    return ''.join(args)

def _display(x, out):
    out.append(format_value(x, write_mode=False))
    return UNSPECIFIED

def _newline(out):
    out.append('\n')
    return UNSPECIFIED

def _error_proc(args):
    msg = args[0]
    if not isinstance(msg, str):
        raise SchemeError("error: first argument is not a string")
    parts = [msg]
    for irr in args[1:]:
        parts.append(' ')
        parts.append(format_value(irr, write_mode=True))
    raise SchemeError(''.join(parts))

# ---------- run() ----------

def run(source: str) -> str:
    output = []
    try:
        # Read all forms first
        reader = Reader(source)
        forms = reader.read_all()
        # Create fresh global environment
        global_env = make_global_env()
        # Evaluate each top-level form
        for form in forms:
            run_expr(form, global_env, output)
    except SchemeError as e:
        e.output = ''.join(output)
        raise
    except Exception as e:
        exc = SchemeError(str(e))
        exc.output = ''.join(output)
        raise exc
    return ''.join(output)
