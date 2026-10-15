import sys

try:
    sys.set_int_max_str_digits(0)
except AttributeError:
    pass

sys.setrecursionlimit(500000)


class SchemeError(Exception):
    def __init__(self, msg, output=''):
        super().__init__(msg)
        self.output = output


# ---------- Data Types ----------

UNSPECIFIED = object()
UNASSIGNED = object()
EMPTY_LIST = object()


class Sym:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name

class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr

class Closure:
    __slots__ = ('formals', 'body', 'env')
    def __init__(self, formals, body, env):
        self.formals = formals
        self.body = body
        self.env = env

class Builtin:
    __slots__ = ('name', 'func')
    def __init__(self, name, func):
        self.name = name
        self.func = func


# ---------- Helpers ----------

def is_true(x):
    return x is not False

def is_proper_list(x):
    current = x
    while current is not EMPTY_LIST:
        if not isinstance(current, Pair):
            return False
        current = current.cdr
    return True

def is_procedure(x):
    return isinstance(x, (Closure, Builtin))

def list_of(scheme_list):
    result = []
    current = scheme_list
    while current is not EMPTY_LIST:
        if not isinstance(current, Pair):
            raise SchemeError("not a proper list")
        result.append(current.car)
        current = current.cdr
    return result

def to_scheme_list(py_list):
    result = EMPTY_LIST
    for item in reversed(py_list):
        result = Pair(item, result)
    return result

def all_but_last(scheme_list):
    result = []
    current = scheme_list
    while current is not EMPTY_LIST and current.cdr is not EMPTY_LIST:
        result.append(current.car)
        current = current.cdr
    return result

def last_of(scheme_list):
    current = scheme_list
    while current.cdr is not EMPTY_LIST:
        current = current.cdr
    return current.car


# ---------- Environment ----------

class Env:
    __slots__ = ('bindings', 'parent')
    def __init__(self, bindings=None, parent=None):
        self.bindings = bindings if bindings is not None else {}
        self.parent = parent

    def lookup(self, name):
        if name in self.bindings:
            val = self.bindings[name]
            if val is UNASSIGNED:
                raise SchemeError(f"unbound variable: {name}")
            return val
        if self.parent is not None:
            return self.parent.lookup(name)
        raise SchemeError(f"unbound variable: {name}")

    def set(self, name, value):
        if name in self.bindings:
            self.bindings[name] = value
        elif self.parent is not None:
            self.parent.set(name, value)
        else:
            raise SchemeError(f"unbound variable: {name}")

    def define(self, name, value):
        self.bindings[name] = value


# ---------- Reader ----------

class Reader:
    def __init__(self, source):
        self.src = source
        self.pos = 0
        self.n = len(source)

    def skip_ws(self):
        while self.pos < self.n:
            ch = self.src[self.pos]
            if ch in ' \t\n\r':
                self.pos += 1
            elif ch == ';':
                while self.pos < self.n and self.src[self.pos] != '\n':
                    self.pos += 1
            else:
                break

    def read_string(self):
        self.pos += 1  # skip opening "
        chars = []
        while self.pos < self.n:
            ch = self.src[self.pos]
            if ch == '"':
                self.pos += 1
                return ''.join(chars)
            elif ch == '\\':
                self.pos += 1
                if self.pos >= self.n:
                    raise SchemeError("unterminated string")
                esc = self.src[self.pos]
                if esc == '"':
                    chars.append('"')
                elif esc == '\\':
                    chars.append('\\')
                elif esc == 'n':
                    chars.append('\n')
                else:
                    raise SchemeError(f"invalid escape: \\{esc}")
                self.pos += 1
            else:
                chars.append(ch)
                self.pos += 1
        raise SchemeError("unterminated string")

    def read_token(self):
        start = self.pos
        while self.pos < self.n:
            ch = self.src[self.pos]
            if ch in ' \t\n\r()";\'':
                break
            self.pos += 1
        return self.src[start:self.pos]

    @staticmethod
    def is_integer(token):
        if not token:
            return False
        i = 0
        if token[0] in '+-':
            i = 1
        if i >= len(token):
            return False
        for c in token[i:]:
            if c < '0' or c > '9':
                return False
        return True

    def parse_atom(self, token):
        if token == '#t':
            return True
        elif token == '#f':
            return False
        elif token.startswith('#'):
            raise SchemeError(f"invalid token: {token}")
        if self.is_integer(token):
            return int(token)
        return Sym(token)

    def read_datum(self):
        self.skip_ws()
        if self.pos >= self.n:
            raise SchemeError("unexpected end of input")
        ch = self.src[self.pos]
        if ch == '(':
            return self.read_list()
        elif ch == ')':
            raise SchemeError("unexpected )")
        elif ch == "'":
            self.pos += 1
            datum = self.read_datum()
            return Pair(Sym('quote'), Pair(datum, EMPTY_LIST))
        elif ch == '"':
            return self.read_string()
        else:
            token = self.read_token()
            if not token:
                raise SchemeError("unexpected end of input")
            return self.parse_atom(token)

    def read_list(self):
        self.pos += 1  # skip (
        elements = []
        while True:
            self.skip_ws()
            if self.pos >= self.n:
                raise SchemeError("unbalanced (")
            ch = self.src[self.pos]
            if ch == ')':
                self.pos += 1
                return self._build_list(elements, EMPTY_LIST)
            if ch == '.' and (self.pos + 1 >= self.n or self.src[self.pos + 1] in ' \t\n\r()";\''):
                # Dot token
                if not elements:
                    raise SchemeError("dot must be preceded by at least one element")
                self.pos += 1  # consume .
                self.skip_ws()
                if self.pos >= self.n:
                    raise SchemeError("unexpected end of input in dotted list")
                last = self.read_datum()
                self.skip_ws()
                if self.pos >= self.n or self.src[self.pos] != ')':
                    raise SchemeError("expected ) after dotted list")
                self.pos += 1
                return self._build_list(elements, last)
            elem = self.read_datum()
            elements.append(elem)

    @staticmethod
    def _build_list(elements, tail):
        result = tail
        for elem in reversed(elements):
            result = Pair(elem, result)
        return result


# ---------- Display / Write ----------

def _int_to_str(n):
    return str(n)

def display_value(x):
    if type(x) is bool:
        return "#t" if x else "#f"
    if type(x) is int:
        return _int_to_str(x)
    if type(x) is str:
        return x
    if isinstance(x, Sym):
        return x.name
    if x is EMPTY_LIST:
        return "()"
    if isinstance(x, Pair):
        return _display_pair(x)
    if isinstance(x, (Closure, Builtin)):
        return "#<procedure>"
    if x is UNSPECIFIED:
        return ""
    return ""

def _display_pair(p):
    parts = []
    current = p
    while isinstance(current, Pair):
        parts.append(display_value(current.car))
        current = current.cdr
    if current is EMPTY_LIST:
        return "(" + " ".join(parts) + ")"
    else:
        return "(" + " ".join(parts) + " . " + display_value(current) + ")"

def write_value(x):
    if type(x) is bool:
        return "#t" if x else "#f"
    if type(x) is int:
        return _int_to_str(x)
    if type(x) is str:
        return '"' + x.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'
    if isinstance(x, Sym):
        return x.name
    if x is EMPTY_LIST:
        return "()"
    if isinstance(x, Pair):
        return _write_pair(x)
    if isinstance(x, (Closure, Builtin)):
        return "#<procedure>"
    if x is UNSPECIFIED:
        return ""
    return ""

def _write_pair(p):
    parts = []
    current = p
    while isinstance(current, Pair):
        parts.append(write_value(current.car))
        current = current.cdr
    if current is EMPTY_LIST:
        return "(" + " ".join(parts) + ")"
    else:
        return "(" + " ".join(parts) + " . " + write_value(current) + ")"


# ---------- Output ----------

class Output:
    __slots__ = ('text',)
    def __init__(self):
        self.text = ''
    def write(self, s):
        self.text += s


_current_output = None


# ---------- Formals normalization ----------

def normalize_formals(formals_list):
    """Normalize formals. formals_list is a Scheme list or a Sym (lone symbol)."""
    if isinstance(formals_list, Sym):
        return ('variadic', formals_list.name)
    if formals_list is EMPTY_LIST:
        return ('fixed', [])
    if not isinstance(formals_list, Pair):
        raise SchemeError("malformed formals")
    fixed = []
    current = formals_list
    while isinstance(current, Pair):
        if not isinstance(current.car, Sym):
            raise SchemeError("formal must be a symbol")
        fixed.append(current.car.name)
        current = current.cdr
    if current is EMPTY_LIST:
        return ('fixed', fixed)
    else:
        if not isinstance(current, Sym):
            raise SchemeError("rest formal must be a symbol")
        return ('dotted', fixed, current.name)


def make_closure(formals_list, body, env):
    formals = normalize_formals(formals_list)
    return Closure(formals, body, env)


def make_call_env(proc, args):
    if not isinstance(proc, Closure):
        return None
    formals = proc.formals
    kind = formals[0]
    if kind == 'fixed':
        names = formals[1]
        if len(args) != len(names):
            return None
        bindings = dict(zip(names, args))
        return Env(bindings, proc.env)
    elif kind == 'dotted':
        fixed_names = formals[1]
        rest_name = formals[2]
        if len(args) < len(fixed_names):
            return None
        bindings = dict(zip(fixed_names, args[:len(fixed_names)]))
        remaining = args[len(fixed_names):]
        bindings[rest_name] = to_scheme_list(remaining)
        return Env(bindings, proc.env)
    elif kind == 'variadic':
        name = formals[1]
        bindings = {name: to_scheme_list(args)}
        return Env(bindings, proc.env)
    return None


# ---------- Evaluator ----------

def _is_define_form(form):
    if not isinstance(form, Pair):
        return False
    if not isinstance(form.car, Sym):
        return False
    if form.car.name != 'define':
        return False
    return True

def _define_name(form):
    """Extract the name from a (define ...) form."""
    parts = form.cdr
    if parts is EMPTY_LIST:
        return None
    first = parts.car
    if isinstance(first, Sym):
        return first.name
    elif isinstance(first, Pair) and isinstance(first.car, Sym):
        return first.car.name
    return None

def _execute_define(form, env):
    parts = form.cdr
    if parts is EMPTY_LIST:
        raise SchemeError("malformed define")
    first = parts.car
    if isinstance(first, Sym):
        name = first.name
        if parts.cdr is EMPTY_LIST:
            raise SchemeError("malformed define")
        expr = parts.cdr.car
        if parts.cdr.cdr is not EMPTY_LIST:
            raise SchemeError("malformed define")
        val = _eval(expr, env)
        env.bindings[name] = val
    elif isinstance(first, Pair):
        if not isinstance(first.car, Sym):
            raise SchemeError("malformed define")
        fname = first.car.name
        formals = first.cdr
        body = parts.cdr
        if body is EMPTY_LIST:
            raise SchemeError("malformed define")
        closure = make_closure(formals, body, env)
        env.bindings[fname] = closure
    else:
        raise SchemeError("malformed define")


def _eval_body(body, env):
    body_list = list_of(body)
    if not body_list:
        raise SchemeError("empty body")

    # Pre-scan for internal definitions
    internal_names = []
    for form in body_list:
        if _is_define_form(form):
            nm = _define_name(form)
            if nm is not None:
                internal_names.append(nm)

    if internal_names:
        env = Env({n: UNASSIGNED for n in internal_names}, env)

    # Evaluate all but last
    for form in body_list[:-1]:
        if _is_define_form(form):
            _execute_define(form, env)
        else:
            _eval(form, env)

    # Last form in tail position
    last = body_list[-1]
    if _is_define_form(last):
        _execute_define(last, env)
        return UNSPECIFIED
    else:
        return _eval_tail(last, env)


def _eval(form, env):
    """Evaluate form in non-tail position."""
    if type(form) is int:
        return form
    if type(form) is bool:
        return form
    if type(form) is str:
        return form
    if form is EMPTY_LIST:
        return form
    if isinstance(form, Sym):
        return env.lookup(form.name)
    if not isinstance(form, Pair):
        return form

    if not is_proper_list(form):
        raise SchemeError("dotted form used as application")

    head = form.car
    args_list = form.cdr

    if isinstance(head, Sym):
        name = head.name

        if name == 'quote':
            if args_list is EMPTY_LIST or args_list.cdr is not EMPTY_LIST:
                raise SchemeError("malformed quote")
            return args_list.car

        if name == 'if':
            if args_list is EMPTY_LIST:
                raise SchemeError("malformed if")
            test = args_list.car
            rest = args_list.cdr
            if rest is EMPTY_LIST:
                raise SchemeError("malformed if")
            then = rest.car
            rest2 = rest.cdr
            test_val = _eval(test, env)
            if is_true(test_val):
                return _eval(then, env)
            else:
                if rest2 is not EMPTY_LIST:
                    return _eval(rest2.car, env)
                else:
                    return UNSPECIFIED

        if name == 'cond':
            clauses = args_list
            if clauses is EMPTY_LIST:
                raise SchemeError("malformed cond")
            current = clauses
            while current is not EMPTY_LIST:
                clause = current.car
                current = current.cdr
                if not isinstance(clause, Pair):
                    raise SchemeError("malformed cond clause")
                test = clause.car
                body = clause.cdr
                if isinstance(test, Sym) and test.name == 'else':
                    if current is not EMPTY_LIST:
                        raise SchemeError("else must be last clause")
                    if body is EMPTY_LIST:
                        raise SchemeError("malformed else clause")
                    for e in all_but_last(body):
                        _eval(e, env)
                    return _eval(last_of(body), env)
                else:
                    test_val = _eval(test, env)
                    if is_true(test_val):
                        if body is EMPTY_LIST:
                            return test_val
                        for e in all_but_last(body):
                            _eval(e, env)
                        return _eval(last_of(body), env)
            return UNSPECIFIED

        if name == 'and':
            exprs = args_list
            current = exprs
            while current is not EMPTY_LIST and current.cdr is not EMPTY_LIST:
                val = _eval(current.car, env)
                if val is False:
                    return False
                current = current.cdr
            if exprs is EMPTY_LIST:
                return True
            return _eval(current.car, env)

        if name == 'or':
            exprs = args_list
            current = exprs
            while current is not EMPTY_LIST and current.cdr is not EMPTY_LIST:
                val = _eval(current.car, env)
                if is_true(val):
                    return val
                current = current.cdr
            if exprs is EMPTY_LIST:
                return False
            return _eval(current.car, env)

        if name == 'begin':
            exprs = args_list
            if exprs is EMPTY_LIST:
                raise SchemeError("malformed begin")
            current = exprs
            while current.cdr is not EMPTY_LIST:
                _eval(current.car, env)
                current = current.cdr
            return _eval(current.car, env)

        if name == 'let':
            parts = args_list
            if parts is EMPTY_LIST:
                raise SchemeError("malformed let")
            first = parts.car
            if isinstance(first, Sym):
                # Named let
                let_name = first.name
                rest = parts.cdr
                if rest is EMPTY_LIST:
                    raise SchemeError("malformed named let")
                bindings = rest.car
                body = rest.cdr
                if body is EMPTY_LIST:
                    raise SchemeError("malformed named let")
                if not isinstance(bindings, Pair) and bindings is not EMPTY_LIST:
                    raise SchemeError("malformed let bindings")
                vars_list = []
                init_vals = []
                b = bindings
                while b is not EMPTY_LIST:
                    binding = b.car
                    if not isinstance(binding, Pair) or binding.cdr is EMPTY_LIST or binding.cdr.cdr is not EMPTY_LIST:
                        raise SchemeError("malformed let binding")
                    v = binding.car
                    init = binding.cdr.car
                    if not isinstance(v, Sym):
                        raise SchemeError("let binding variable must be a symbol")
                    vars_list.append(v.name)
                    init_vals.append(_eval(init, env))
                    b = b.cdr
                closure_env = Env({}, env)
                closure = Closure(('fixed', vars_list), body, closure_env)
                closure_env.bindings[let_name] = closure
                new_env = Env(dict(zip(vars_list, init_vals)), closure_env)
                return _eval_body(body, new_env)
            else:
                # Regular let
                bindings = first
                body = parts.cdr
                if body is EMPTY_LIST:
                    raise SchemeError("malformed let")
                if not isinstance(bindings, Pair) and bindings is not EMPTY_LIST:
                    raise SchemeError("malformed let bindings")
                new_bindings = {}
                b = bindings
                while b is not EMPTY_LIST:
                    binding = b.car
                    if not isinstance(binding, Pair) or binding.cdr is EMPTY_LIST or binding.cdr.cdr is not EMPTY_LIST:
                        raise SchemeError("malformed let binding")
                    v = binding.car
                    init = binding.cdr.car
                    if not isinstance(v, Sym):
                        raise SchemeError("let binding variable must be a symbol")
                    new_bindings[v.name] = _eval(init, env)
                    b = b.cdr
                new_env = Env(new_bindings, env)
                return _eval_body(body, new_env)

        if name == 'let*':
            parts = args_list
            if parts is EMPTY_LIST:
                raise SchemeError("malformed let*")
            bindings = parts.car
            body = parts.cdr
            if body is EMPTY_LIST:
                raise SchemeError("malformed let*")
            if not isinstance(bindings, Pair) and bindings is not EMPTY_LIST:
                raise SchemeError("malformed let* bindings")
            new_env = Env({}, env)
            b = bindings
            while b is not EMPTY_LIST:
                binding = b.car
                if not isinstance(binding, Pair) or binding.cdr is EMPTY_LIST or binding.cdr.cdr is not EMPTY_LIST:
                    raise SchemeError("malformed let* binding")
                v = binding.car
                init = binding.cdr.car
                if not isinstance(v, Sym):
                    raise SchemeError("let* binding variable must be a symbol")
                new_env.bindings[v.name] = _eval(init, new_env)
                b = b.cdr
            return _eval_body(body, new_env)

        if name == 'letrec':
            parts = args_list
            if parts is EMPTY_LIST:
                raise SchemeError("malformed letrec")
            bindings = parts.car
            body = parts.cdr
            if body is EMPTY_LIST:
                raise SchemeError("malformed letrec")
            if not isinstance(bindings, Pair) and bindings is not EMPTY_LIST:
                raise SchemeError("malformed letrec bindings")
            vars_list = []
            inits_list = []
            b = bindings
            while b is not EMPTY_LIST:
                binding = b.car
                if not isinstance(binding, Pair) or binding.cdr is EMPTY_LIST or binding.cdr.cdr is not EMPTY_LIST:
                    raise SchemeError("malformed letrec binding")
                v = binding.car
                init = binding.cdr.car
                if not isinstance(v, Sym):
                    raise SchemeError("letrec binding variable must be a symbol")
                vars_list.append(v.name)
                inits_list.append(init)
                b = b.cdr
            new_env = Env({v: UNASSIGNED for v in vars_list}, env)
            for v, init in zip(vars_list, inits_list):
                val = _eval(init, new_env)
                new_env.bindings[v] = val
            return _eval_body(body, new_env)

        if name == 'define':
            _execute_define(form, env)
            return UNSPECIFIED

        if name == 'set!':
            parts = form.cdr
            if parts is EMPTY_LIST or parts.cdr is EMPTY_LIST:
                raise SchemeError("malformed set!")
            name_sym = parts.car
            if not isinstance(name_sym, Sym):
                raise SchemeError("set! requires a symbol")
            val = _eval(parts.cdr.car, env)
            env.set(name_sym.name, val)
            return UNSPECIFIED

        if name == 'lambda':
            parts = form.cdr
            if parts is EMPTY_LIST:
                raise SchemeError("malformed lambda")
            formals = parts.car
            body = parts.cdr
            if body is EMPTY_LIST:
                raise SchemeError("malformed lambda")
            return make_closure(formals, body, env)

        # Not a special form: procedure call
        op = _eval(head, env)
        args = []
        a = args_list
        while a is not EMPTY_LIST:
            args.append(_eval(a.car, env))
            a = a.cdr
        if not is_procedure(op):
            raise SchemeError("not a procedure")
        new_env = make_call_env(op, args)
        if new_env is None:
            raise SchemeError("arity error")
        if isinstance(op, Closure):
            return _eval_body(op.body, new_env)
        else:
            return op.func(args)
    else:
        # Head is not a symbol: procedure call
        op = _eval(head, env)
        args = []
        a = args_list
        while a is not EMPTY_LIST:
            args.append(_eval(a.car, env))
            a = a.cdr
        if not is_procedure(op):
            raise SchemeError("not a procedure")
        new_env = make_call_env(op, args)
        if new_env is None:
            raise SchemeError("arity error")
        if isinstance(op, Closure):
            return _eval_body(op.body, new_env)
        else:
            return op.func(args)


def _eval_tail(form, env):
    """Evaluate form in tail position. Returns a value."""
    while True:
        # Handle body marker
        if isinstance(form, tuple) and len(form) == 2 and form[0] == '__body__':
            body = form[1]
            body_list = list_of(body)
            if not body_list:
                raise SchemeError("empty body")
            # Pre-scan for internal definitions
            internal_names = []
            for f in body_list:
                if _is_define_form(f):
                    nm = _define_name(f)
                    if nm is not None:
                        internal_names.append(nm)
            if internal_names:
                env = Env({n: UNASSIGNED for n in internal_names}, env)
            for f in body_list[:-1]:
                if _is_define_form(f):
                    _execute_define(f, env)
                else:
                    _eval(f, env)
            last = body_list[-1]
            if _is_define_form(last):
                _execute_define(last, env)
                return UNSPECIFIED
            form = last
            continue

        # Self-evaluating
        if type(form) is int:
            return form
        if type(form) is bool:
            return form
        if type(form) is str:
            return form
        if form is EMPTY_LIST:
            return form
        if isinstance(form, Sym):
            return env.lookup(form.name)
        if not isinstance(form, Pair):
            return form

        if not is_proper_list(form):
            raise SchemeError("dotted form used as application")

        head = form.car
        args_list = form.cdr

        if isinstance(head, Sym):
            name = head.name

            if name == 'quote':
                if args_list is EMPTY_LIST or args_list.cdr is not EMPTY_LIST:
                    raise SchemeError("malformed quote")
                return args_list.car

            if name == 'if':
                if args_list is EMPTY_LIST:
                    raise SchemeError("malformed if")
                test = args_list.car
                rest = args_list.cdr
                if rest is EMPTY_LIST:
                    raise SchemeError("malformed if")
                then = rest.car
                rest2 = rest.cdr
                test_val = _eval(test, env)
                if is_true(test_val):
                    form = then
                    continue
                else:
                    if rest2 is not EMPTY_LIST:
                        form = rest2.car
                        continue
                    else:
                        return UNSPECIFIED

            if name == 'cond':
                clauses = args_list
                if clauses is EMPTY_LIST:
                    raise SchemeError("malformed cond")
                found = False
                current = clauses
                while current is not EMPTY_LIST:
                    clause = current.car
                    current = current.cdr
                    if not isinstance(clause, Pair):
                        raise SchemeError("malformed cond clause")
                    test = clause.car
                    body = clause.cdr
                    if isinstance(test, Sym) and test.name == 'else':
                        if current is not EMPTY_LIST:
                            raise SchemeError("else must be last clause")
                        if body is EMPTY_LIST:
                            raise SchemeError("malformed else clause")
                        for e in all_but_last(body):
                            _eval(e, env)
                        form = last_of(body)
                        found = True
                        break
                    else:
                        test_val = _eval(test, env)
                        if is_true(test_val):
                            if body is EMPTY_LIST:
                                return test_val
                            for e in all_but_last(body):
                                _eval(e, env)
                            form = last_of(body)
                            found = True
                            break
                if not found:
                    return UNSPECIFIED
                continue

            if name == 'and':
                exprs = args_list
                current = exprs
                while current is not EMPTY_LIST and current.cdr is not EMPTY_LIST:
                    val = _eval(current.car, env)
                    if val is False:
                        return False
                    current = current.cdr
                if exprs is EMPTY_LIST:
                    return True
                form = current.car
                continue

            if name == 'or':
                exprs = args_list
                current = exprs
                while current is not EMPTY_LIST and current.cdr is not EMPTY_LIST:
                    val = _eval(current.car, env)
                    if is_true(val):
                        return val
                    current = current.cdr
                if exprs is EMPTY_LIST:
                    return False
                form = current.car
                continue

            if name == 'begin':
                exprs = args_list
                if exprs is EMPTY_LIST:
                    raise SchemeError("malformed begin")
                current = exprs
                while current.cdr is not EMPTY_LIST:
                    _eval(current.car, env)
                    current = current.cdr
                form = current.car
                continue

            if name == 'let':
                parts = args_list
                if parts is EMPTY_LIST:
                    raise SchemeError("malformed let")
                first = parts.car
                if isinstance(first, Sym):
                    # Named let
                    let_name = first.name
                    rest = parts.cdr
                    if rest is EMPTY_LIST:
                        raise SchemeError("malformed named let")
                    bindings = rest.car
                    body = rest.cdr
                    if body is EMPTY_LIST:
                        raise SchemeError("malformed named let")
                    if not isinstance(bindings, Pair) and bindings is not EMPTY_LIST:
                        raise SchemeError("malformed let bindings")
                    vars_list = []
                    init_vals = []
                    b = bindings
                    while b is not EMPTY_LIST:
                        binding = b.car
                        if not isinstance(binding, Pair) or binding.cdr is EMPTY_LIST or binding.cdr.cdr is not EMPTY_LIST:
                            raise SchemeError("malformed let binding")
                        v = binding.car
                        init = binding.cdr.car
                        if not isinstance(v, Sym):
                            raise SchemeError("let binding variable must be a symbol")
                        vars_list.append(v.name)
                        init_vals.append(_eval(init, env))
                        b = b.cdr
                    closure_env = Env({}, env)
                    closure = Closure(('fixed', vars_list), body, closure_env)
                    closure_env.bindings[let_name] = closure
                    new_env = Env(dict(zip(vars_list, init_vals)), closure_env)
                    form = ('__body__', body)
                    env = new_env
                    continue
                else:
                    bindings = first
                    body = parts.cdr
                    if body is EMPTY_LIST:
                        raise SchemeError("malformed let")
                    if not isinstance(bindings, Pair) and bindings is not EMPTY_LIST:
                        raise SchemeError("malformed let bindings")
                    new_bindings = {}
                    b = bindings
                    while b is not EMPTY_LIST:
                        binding = b.car
                        if not isinstance(binding, Pair) or binding.cdr is EMPTY_LIST or binding.cdr.cdr is not EMPTY_LIST:
                            raise SchemeError("malformed let binding")
                        v = binding.car
                        init = binding.cdr.car
                        if not isinstance(v, Sym):
                            raise SchemeError("let binding variable must be a symbol")
                        new_bindings[v.name] = _eval(init, env)
                        b = b.cdr
                    new_env = Env(new_bindings, env)
                    form = ('__body__', body)
                    env = new_env
                    continue

            if name == 'let*':
                parts = args_list
                if parts is EMPTY_LIST:
                    raise SchemeError("malformed let*")
                bindings = parts.car
                body = parts.cdr
                if body is EMPTY_LIST:
                    raise SchemeError("malformed let*")
                if not isinstance(bindings, Pair) and bindings is not EMPTY_LIST:
                    raise SchemeError("malformed let* bindings")
                new_env = Env({}, env)
                b = bindings
                while b is not EMPTY_LIST:
                    binding = b.car
                    if not isinstance(binding, Pair) or binding.cdr is EMPTY_LIST or binding.cdr.cdr is not EMPTY_LIST:
                        raise SchemeError("malformed let* binding")
                    v = binding.car
                    init = binding.cdr.car
                    if not isinstance(v, Sym):
                        raise SchemeError("let* binding variable must be a symbol")
                    new_env.bindings[v.name] = _eval(init, new_env)
                    b = b.cdr
                form = ('__body__', body)
                env = new_env
                continue

            if name == 'letrec':
                parts = args_list
                if parts is EMPTY_LIST:
                    raise SchemeError("malformed letrec")
                bindings = parts.car
                body = parts.cdr
                if body is EMPTY_LIST:
                    raise SchemeError("malformed letrec")
                if not isinstance(bindings, Pair) and bindings is not EMPTY_LIST:
                    raise SchemeError("malformed letrec bindings")
                vars_list = []
                inits_list = []
                b = bindings
                while b is not EMPTY_LIST:
                    binding = b.car
                    if not isinstance(binding, Pair) or binding.cdr is EMPTY_LIST or binding.cdr.cdr is not