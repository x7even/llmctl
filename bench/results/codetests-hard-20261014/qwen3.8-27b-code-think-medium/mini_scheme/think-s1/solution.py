import sys
import re

try:
    sys.set_int_max_str_digits(0)
except AttributeError:
    pass

sys.setrecursionlimit(500000)


class SchemeError(Exception):
    def __init__(self, msg=''):
        super().__init__(msg)
        self.output = ''


class Sym:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name
    def __eq__(self, other):
        return isinstance(other, Sym) and self.name == other.name
    def __hash__(self):
        return hash(('Sym', self.name))
    def __repr__(self):
        return f"Sym({self.name!r})"


class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr
    def __repr__(self):
        return f"Pair({self.car!r}, {self.cdr!r})"


class NIL:
    _instance = None
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    def __repr__(self):
        return "()"


NIL = NIL()


class _Uninitialized:
    pass
UNINITIALIZED = _Uninitialized()


class _Unspecified:
    pass
UNSPECIFIED = _Unspecified()


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
    def __repr__(self):
        return f"#<builtin {self.name}>"


class TailCall:
    __slots__ = ('expr', 'env')
    def __init__(self, expr, env):
        self.expr = expr
        self.env = env


class Env:
    __slots__ = ('bindings', 'parent')
    def __init__(self, bindings, parent=None):
        self.bindings = bindings
        self.parent = parent


# ---------- Helper functions ----------

def is_pair(x):
    return isinstance(x, Pair)

def is_nil(x):
    return x is NIL

def is_proper_list(x):
    while True:
        if x is NIL:
            return True
        if not isinstance(x, Pair):
            return False
        x = x.cdr

def list_to_py(x):
    result = []
    while x is not NIL:
        if not isinstance(x, Pair):
            raise SchemeError("expected proper list")
        result.append(x.car)
        x = x.cdr
    return result

def make_list(elems):
    result = NIL
    for e in reversed(elems):
        result = Pair(e, result)
    return result

def is_procedure(x):
    return isinstance(x, Closure) or isinstance(x, Builtin)

def is_integer(x):
    return isinstance(x, int) and not isinstance(x, bool)

def is_bool(x):
    return isinstance(x, bool)

def is_string(x):
    return isinstance(x, str)

def is_sym(x):
    return isinstance(x, Sym)

def is_number(x):
    return is_integer(x)


# ---------- Reader ----------

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
            tokens.append(('LPAREN',))
            i += 1
        elif c == ')':
            tokens.append(('RPAREN',))
            i += 1
        elif c == "'":
            tokens.append(('QUOTE',))
            i += 1
        elif c == '"':
            i += 1
            chars = []
            while i < n:
                if source[i] == '"':
                    i += 1
                    break
                elif source[i] == '\\':
                    if i + 1 >= n:
                        raise SchemeError("unterminated string escape")
                    esc = source[i + 1]
                    if esc == '"':
                        chars.append('"')
                        i += 2
                    elif esc == '\\':
                        chars.append('\\')
                        i += 2
                    elif esc == 'n':
                        chars.append('\n')
                        i += 2
                    else:
                        raise SchemeError(f"invalid escape: \\{esc}")
                else:
                    chars.append(source[i])
                    i += 1
            else:
                raise SchemeError("unterminated string")
            tokens.append(('STRING', ''.join(chars)))
        else:
            start = i
            while i < n and source[i] not in ' \t\n\r()";\'':
                i += 1
            word = source[start:i]
            if not word:
                raise SchemeError("empty token")
            if re.fullmatch(r'[+-]?[0-9]+', word):
                tokens.append(('INT', int(word)))
            elif word == '#t':
                tokens.append(('BOOL', True))
            elif word == '#f':
                tokens.append(('BOOL', False))
            elif word.startswith('#'):
                raise SchemeError(f"invalid token: {word}")
            else:
                tokens.append(('SYM', word))
    return tokens


def parse_sexpr(tokens, pos):
    if pos >= len(tokens):
        raise SchemeError("unexpected end of input")
    tok = tokens[pos]
    kind = tok[0]
    if kind == 'LPAREN':
        return parse_list(tokens, pos + 1)
    elif kind == 'RPAREN':
        raise SchemeError("unbalanced )")
    elif kind == 'QUOTE':
        if pos + 1 >= len(tokens):
            raise SchemeError("quote without datum")
        datum, pos = parse_sexpr(tokens, pos + 1)
        return (Pair(Sym('quote'), Pair(datum, NIL)), pos)
    elif kind == 'INT':
        return (tok[1], pos + 1)
    elif kind == 'BOOL':
        return (tok[1], pos + 1)
    elif kind == 'STRING':
        return (tok[1], pos + 1)
    elif kind == 'SYM':
        return (Sym(tok[1]), pos + 1)
    raise SchemeError(f"unexpected token: {tok}")


def parse_list(tokens, pos):
    elements = []
    while True:
        if pos >= len(tokens):
            raise SchemeError("unbalanced (")
        tok = tokens[pos]
        kind = tok[0]
        if kind == 'RPAREN':
            pos += 1
            result = NIL
            for elem in reversed(elements):
                result = Pair(elem, result)
            return result, pos
        elif kind == 'SYM' and tok[1] == '.':
            if not elements:
                raise SchemeError("dot must be preceded by at least one element")
            pos += 1
            if pos >= len(tokens):
                raise SchemeError("unterminated dotted list")
            last, pos = parse_sexpr(tokens, pos)
            if pos >= len(tokens) or tokens[pos][0] != 'RPAREN':
                raise SchemeError("dotted list must end with )")
            pos += 1
            result = last
            for elem in reversed(elements):
                result = Pair(elem, result)
            return result, pos
        else:
            elem, pos = parse_sexpr(tokens, pos)
            elements.append(elem)


def read_all(source):
    tokens = tokenize(source)
    forms = []
    pos = 0
    while pos < len(tokens):
        form, pos = parse_sexpr(tokens, pos)
        forms.append(form)
    return forms


# ---------- Display / Write ----------

def display_repr(x):
    if is_integer(x):
        return str(x)
    if x is True:
        return "#t"
    if x is False:
        return "#f"
    if is_string(x):
        return x
    if is_sym(x):
        return x.name
    if x is NIL:
        return "()"
    if is_procedure(x):
        return "#<procedure>"
    if x is UNSPECIFIED:
        return ""
    if isinstance(x, Pair):
        parts = []
        current = x
        while isinstance(current, Pair):
            parts.append(display_repr(current.car))
            current = current.cdr
        if current is NIL:
            return "(" + " ".join(parts) + ")"
        else:
            return "(" + " ".join(parts) + " . " + display_repr(current) + ")"
    return ""


def write_repr(x):
    if is_string(x):
        escaped = x.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        return '"' + escaped + '"'
    if isinstance(x, Pair):
        parts = []
        current = x
        while isinstance(current, Pair):
            parts.append(write_repr(current.car))
            current = current.cdr
        if current is NIL:
            return "(" + " ".join(parts) + ")"
        else:
            return "(" + " ".join(parts) + " . " + write_repr(current) + ")"
    return display_repr(x)


# ---------- Environment ----------

def lookup(env, name):
    e = env
    while e is not None:
        if name in e.bindings:
            val = e.bindings[name]
            if val is UNINITIALIZED:
                raise SchemeError(f"uninitialized variable: {name.name}")
            return val
        e = e.parent
    raise SchemeError(f"unbound variable: {name.name}")


def lookup_or_none(env, name):
    e = env
    while e is not None:
        if name in e.bindings:
            val = e.bindings[name]
            if val is UNINITIALIZED:
                return None
            return val
        e = e.parent
    return None


# ---------- Evaluator ----------

def evaluate(expr, env):
    while True:
        result = eval_expr(expr, env)
        if isinstance(result, TailCall):
            expr, env = result.expr, result.env
        else:
            return result


def eval_expr(expr, env):
    if is_integer(expr):
        return expr
    if is_bool(expr):
        return expr
    if is_string(expr):
        return expr
    if is_sym(expr):
        return lookup(env, expr)
    if x_is_nil(expr):
        raise SchemeError("cannot apply the empty list")
    if isinstance(expr, Pair):
        if not is_proper_list(expr):
            raise SchemeError("dotted form cannot be used as an application")
        head = expr.car
        if is_sym(head):
            name = head.name
            if name == 'quote':
                return eval_quote(expr)
            elif name == 'if':
                return eval_if(expr, env)
            elif name == 'define':
                return eval_define(expr, env)
            elif name == 'set!':
                return eval_set(expr, env)
            elif name == 'begin':
                return eval_begin(expr, env)
            elif name == 'cond':
                return eval_cond(expr, env)
            elif name == 'and':
                return eval_and(expr, env)
            elif name == 'or':
                return eval_or(expr, env)
            elif name == 'let':
                return eval_let(expr, env)
            elif name == 'let*':
                return eval_letstar(expr, env)
            elif name == 'letrec':
                return eval_letrec(expr, env)
            elif name == 'lambda':
                return eval_lambda(expr, env)
        return eval_application(expr, env)
    raise SchemeError(f"invalid form")


def x_is_nil(x):
    return x is NIL


def eval_quote(form):
    elems = list_to_py(form)
    if len(elems) != 2:
        raise SchemeError("quote: expected exactly one datum")
    return elems[1]


def eval_if(form, env):
    elems = list_to_py(form)
    if len(elems) not in (3, 4):
        raise SchemeError("if: expected (if test then) or (if test then else)")
    test_val = evaluate(elems[1], env)
    if test_val is not False:
        return evaluate(elems[2], env)
    elif len(elems) == 4:
        return evaluate(elems[3], env)
    else:
        return UNSPECIFIED


def eval_define(form, env):
    elems = list_to_py(form)
    if len(elems) < 2:
        raise SchemeError("define: malformed")
    if is_sym(elems[1]):
        if len(elems) != 3:
            raise SchemeError("define: expected (define name expr)")
        name = elems[1]
        val = evaluate(elems[2], env)
        env.bindings[name] = val
        return UNSPECIFIED
    elif isinstance(elems[1], Pair):
        if len(elems) < 3:
            raise SchemeError("define: expected (define (name . formals) body...)")
        name = elems[1].car
        if not is_sym(name):
            raise SchemeError("define: name must be a symbol")
        formals = elems[1].cdr
        body = form.cdr.cdr
        if body is NIL:
            raise SchemeError("define: empty body")
        val = make_closure(formals, body, env)
        env.bindings[name] = val
        return UNSPECIFIED
    else:
        raise SchemeError("define: malformed")


def eval_set(form, env):
    elems = list_to_py(form)
    if len(elems) != 3:
        raise SchemeError("set!: expected (set! name expr)")
    name = elems[1]
    if not is_sym(name):
        raise SchemeError("set!: name must be a symbol")
    val = evaluate(elems[2], env)
    e = env
    while e is not None:
        if name in e.bindings:
            e.bindings[name] = val
            return UNSPECIFIED
        e = e.parent
    raise SchemeError(f"set!: unbound variable: {name.name}")


def eval_begin(form, env):
    body = form.cdr
    if body is NIL:
        raise SchemeError("begin: empty")
    return eval_body(body, env)


def eval_cond(form, env):
    clauses = form.cdr
    if clauses is NIL:
        raise SchemeError("cond: no clauses")
    for clause in list_to_py(clauses):
        if not isinstance(clause, Pair):
            raise SchemeError("cond: clause must be a list")
        test = clause.car
        rest = clause.cdr
        if is_sym(test) and test.name == 'else':
            if rest is NIL:
                raise SchemeError("cond: else clause needs expressions")
            return eval_body(rest, env)
        else:
            val = evaluate(test, env)
            if val is not False:
                if rest is NIL:
                    return val
                else:
                    return eval_body(rest, env)
    return UNSPECIFIED


def eval_and(form, env):
    rest = form.cdr
    if rest is NIL:
        return True
    while rest.cdr is not NIL:
        val = evaluate(rest.car, env)
        if val is False:
            return False
        rest = rest.cdr
    return evaluate(rest.car, env)


def eval_or(form, env):
    rest = form.cdr
    if rest is NIL:
        return False
    while rest.cdr is not NIL:
        val = evaluate(rest.car, env)
        if val is not False:
            return val
        rest = rest.cdr
    return evaluate(rest.car, env)


def eval_let(form, env):
    # (let ((v1 init1) ...) body...) or (let name ((v1 init1) ...) body...)
    second = form.cdr.car
    if is_sym(second):
        return eval_named_let(form, env)
    # Regular let
    bindings_spec = second
    body = form.cdr.cdr
    if body is NIL:
        raise SchemeError("let: empty body")
    if not is_proper_list(bindings_spec):
        raise SchemeError("let: bindings must be a proper list")
    # Evaluate inits in outer scope
    names = []
    values = []
    for binding in list_to_py(bindings_spec):
        if not isinstance(binding, Pair) or binding.cdr is NIL or binding.cdr.cdr is not NIL:
            raise SchemeError("let: malformed binding")
        v = binding.car
        if not is_sym(v):
            raise SchemeError("let: binding variable must be a symbol")
        names.append(v)
        values.append(evaluate(binding.cdr.car, env))
    new_env = Env({}, env)
    for n, v in zip(names, values):
        new_env.bindings[n] = v
    return eval_body(body, new_env)


def eval_named_let(form, env):
    name = form.cdr.car
    bindings_spec = form.cdr.cdr.car
    body = form.cdr.cdr.cdr
    if body is NIL:
        raise SchemeError("named let: empty body")
    if not is_proper_list(bindings_spec):
        raise SchemeError("named let: bindings must be a proper list")
    # Evaluate inits in outer scope
    names = []
    values = []
    for binding in list_to_py(bindings_spec):
        if not isinstance(binding, Pair) or binding.cdr is NIL or binding.cdr.cdr is not NIL:
            raise SchemeError("named let: malformed binding")
        v = binding.car
        if not is_sym(v):
            raise SchemeError("named let: binding variable must be a symbol")
        names.append(v)
        values.append(evaluate(binding.cdr.car, env))
    # Create closure
    new_env = Env({name: None}, env)
    closure = Closure(('fixed', names), body, new_env)
    new_env.bindings[name] = closure
    return call_procedure_tail(closure, values)


def eval_letstar(form, env):
    bindings_spec = form.cdr.car
    body = form.cdr.cdr
    if body is NIL:
        raise SchemeError("let*: empty body")
    if not is_proper_list(bindings_spec):
        raise SchemeError("let*: bindings must be a proper list")
    current_env = env
    for binding in list_to_py(bindings_spec):
        if not isinstance(binding, Pair) or binding.cdr is NIL or binding.cdr.cdr is not NIL:
            raise SchemeError("let*: malformed binding")
        v = binding.car
        if not is_sym(v):
            raise SchemeError("let*: binding variable must be a symbol")
        val = evaluate(binding.cdr.car, current_env)
        current_env = Env({v: val}, current_env)
    return eval_body(body, current_env)


def eval_letrec(form, env):
    bindings_spec = form.cdr.car
    body = form.cdr.cdr
    if body is NIL:
        raise SchemeError("letrec: empty body")
    if not is_proper_list(bindings_spec):
        raise SchemeError("letrec: bindings must be a proper list")
    new_env = Env({}, env)
    names = []
    inits = []
    for binding in list_to_py(bindings_spec):
        if not isinstance(binding, Pair) or binding.cdr is NIL or binding.cdr.cdr is not NIL:
            raise SchemeError("letrec: malformed binding")
        v = binding.car
        if not is_sym(v):
            raise SchemeError("letrec: binding variable must be a symbol")
        names.append(v)
        inits.append(binding.cdr.car)
        new_env.bindings[v] = UNINITIALIZED
    for v, init in zip(names, inits):
        new_env.bindings[v] = evaluate(init, new_env)
    return eval_body(body, new_env)


def eval_lambda(form, env):
    elems = list_to_py(form)
    if len(elems) < 3:
        raise SchemeError("lambda: expected (lambda formals body...)")
    formals = elems[1]
    body = form.cdr.cdr
    if body is NIL:
        raise SchemeError("lambda: empty body")
    return Closure(formals, body, env)


def make_closure(formals, body, env):
    return Closure(formals, body, env)


def eval_application(form, env):
    op = evaluate(form.car, env)
    args = []
    rest = form.cdr
    while rest is not NIL:
        args.append(evaluate(rest.car, env))
        rest = rest.cdr
    if not is_procedure(op):
        raise SchemeError(f"attempt to apply non-procedure: {display_repr(op)}")
    # Special case: apply in tail position
    if isinstance(op, Builtin) and op.name == 'apply':
        if len(args) < 2:
            raise SchemeError("apply: expected at least 2 arguments")
        f = args[0]
        extra = args[1:-1]
        lst = args[-1]
        if not is_proper_list(lst):
            raise SchemeError("apply: last argument must be a proper list")
        if not is_procedure(f):
            raise SchemeError("apply: first argument must be a procedure")
        all_args = extra + list_to_py(lst)
        return call_procedure_tail(f, all_args)
    return call_procedure_tail(op, args)


def call_procedure_tail(proc, args):
    if isinstance(proc, Builtin):
        return proc.func(args)
    elif isinstance(proc, Closure):
        new_env = bind_args(proc.formals, args, proc.env)
        return TailCall(proc.body, new_env)
    raise SchemeError("not a procedure")


def bind_args(formals, args, outer_env):
    if is_sym(formals):
        # Rest: all args collected into a list
        return Env({formals: make_list(args)}, outer_env)
    if isinstance(formals, Pair):
        elements, tail = decompose(formals)
        if tail is NIL:
            # Fixed arity
            if len(args) != len(elements):
                raise SchemeError(f"wrong number of arguments: expected {len(elements)}, got {len(args)}")
            bindings = {}
            for i, v in enumerate(elements):
                if not is_sym(v):
                    raise SchemeError("formal must be a symbol")
                bindings[v] = args[i]
            return Env(bindings, outer_env)
        else:
            # Dotted: (a b . rest)
            if not is_sym(tail):
                raise SchemeError("rest parameter must be a symbol")
            if len(args) < len(elements):
                raise SchemeError(f"wrong number of arguments: expected at least {len(elements)}, got {len(args)}")
            bindings = {}
            for i, v in enumerate(elements):
                if not is_sym(v):
                    raise SchemeError("formal must be a symbol")
                bindings[v] = args[i]
            bindings[tail] = make_list(args[len(elements):])
            return Env(bindings, outer_env)
    raise SchemeError("invalid formals")


def decompose(x):
    """Decompose a list/dotted-list into (elements, tail)."""
    elements = []
    current = x
    while isinstance(current, Pair):
        elements.append(current.car)
        current = current.cdr
    return elements, current


# ---------- Body evaluation with internal definitions ----------

def eval_body(forms, env):
    if forms is NIL:
        raise SchemeError("empty body")
    # Check for internal definitions
    names = []
    for form in list_to_py(forms):
        if not isinstance(form, Pair):
            continue
        if not is_proper_list(form):
            continue
        elems = list_to_py(form)
        if len(elems) < 2:
            continue
        if not (is_sym(elems[0]) and elems[0].name == 'define'):
            continue
        if is_sym(elems[1]):
            names.append(elems[1])
        elif isinstance(elems[1], Pair):
            if isinstance(elems[1].car, Sym):
                names.append(elems[1].car)
    if names:
        new_env = Env({}, env)
        for n in names:
            new_env.bindings[n] = UNINITIALIZED
        return eval_body_with_defs(forms, new_env)
    else:
        return eval_body_simple(forms, env)


def eval_body_simple(forms, env):
    rest = forms
    while rest.cdr is not NIL:
        evaluate(rest.car, env)
        rest = rest.cdr
    return evaluate(rest.car, env)


def eval_body_with_defs(forms, env):
    rest = forms
    while rest is not NIL:
        form = rest.car
        is_last = rest.cdr is NIL
        # Check if this is an internal define
        if isinstance(form, Pair) and is_proper_list(form):
            elems = list_to_py(form)
            if len(elems) >= 2 and is_sym(elems[0]) and elems[0].name == 'define':
                eval_internal_define(form, env)
                if is_last:
                    return UNSPECIFIED
                rest = rest.cdr
                continue
        if is_last:
            return evaluate(form, env)
        else:
            evaluate(form, env)
            rest = rest.cdr
    return UNSPECIFIED


def eval_internal_define(form, env):
    elems = list_to_py(form)
    if len(elems) < 2:
        raise SchemeError("define: malformed")
    if is_sym(elems[1]):
        if len(elems) != 3:
            raise SchemeError("define: expected (define name expr)")
        name = elems[1]
        val = evaluate(elems[2], env)
        env.bindings[name] = val
    elif isinstance(elems[1], Pair):
        if len(elems) < 3:
            raise SchemeError("define: expected (define (name . formals) body...)")
        name = elems[1].car
        if not is_sym(name):
            raise SchemeError("define: name must be a symbol")
        formals = elems[1].cdr
        body = form.cdr.cdr
        if body is NIL:
            raise SchemeError("define: empty body")
        val = make_closure(formals, body, env)
        env.bindings[name] = val
    else:
        raise SchemeError("define: malformed")


# ---------- Builtins ----------

def make_global_env(out):
    env = Env({})

    def builtin_plus(args):
        for a in args:
            if not is_integer(a):
                raise SchemeError("+: all arguments must be integers")
        return sum(args)

    def builtin_star(args):
        for a in args:
            if not is_integer(a):
                raise SchemeError("*: all arguments must be integers")
        result = 1
        for a in args:
            result *= a
        return result

    def builtin_minus(args):
        for a in args:
            if not is_integer(a):
                raise SchemeError("-: all arguments must be integers")
        if len(args) == 1:
            return -args[0]
        result = args[0]
        for a in args[1:]:
            result -= a
        return result

    def builtin_quotient(args):
        a, b = args
        if not is_integer(a) or not is_integer(b):
            raise SchemeError("quotient: arguments must be integers")
        if b == 0:
            raise SchemeError("quotient: division by zero")
        q = abs(a) // abs(b)
        if (a < 0) != (b < 0):
            q = -q
        return q

    def builtin_remainder(args):
        a, b = args
        if not is_integer(a) or not is_integer(b):
            raise SchemeError("remainder: arguments must be integers")
        if b == 0:
            raise SchemeError("remainder: division by zero")
        r = abs(a) % abs(b)
        if a < 0:
            r = -r
        return r

    def builtin_modulo(args):
        a, b = args
        if not is_integer(a) or not is_integer(b):
            raise SchemeError("modulo: arguments must be integers")
        if b == 0:
            raise SchemeError("modulo: division by zero")
        return a % b

    def make_compare(op_func):
        def cmp(args):
            for a in args:
                if not is_integer(a):
                    raise SchemeError("comparison: all arguments must be integers")
            for i in range(len(args) - 1):
                if not op_func(args[i], args[i + 1]):
                    return False
            return True
        return cmp

    def builtin_number_to_string(args):
        n = args[0]
        if not is_integer(n):
            raise SchemeError("number->string: first argument must be an integer")
        if len(args) == 1:
            return str(n)
        radix = args[1]
        if not is_integer(radix) or radix not in (2, 8, 10, 16):
            raise SchemeError("number->string: radix must be 2, 8, 10, or 16")
        if radix == 10:
            return str(n)
        if n == 0:
            return "0"
        negative = n < 0
        n = abs(n)
        digits = []
        while n > 0:
            d = n % radix
            if d < 10:
                digits.append(str(d))
            else:
                digits.append(chr(ord('a') + d - 10))
            n //= radix
        result = ''.join(reversed(digits))
        return ('-' if negative else '') + result

    def builtin_cons(args):
        return Pair(args[0], args[1])

    def builtin_car(args):
        if not is_pair(args[0]):
            raise SchemeError("car: argument must be a pair")
        return args[0].car

    def builtin_cdr(args):
        if not is_pair(args[0]):
            raise SchemeError("cdr: argument must be a pair")
        return args[0].cdr

    def builtin_list(args):
        return make_list(args)

    def builtin_null_p(args):
        return args[0] is NIL

    def builtin_pair_p(args):
        return is_pair(args[0])

    def builtin_list_p(args):
        return is_proper_list(args[0])

    def builtin_length(args):
        x = args[0]
        if not is_proper_list(x):
            raise SchemeError("length: argument must be a proper list")
        count = 0
        while x is not NIL:
            count += 1
            x = x.cdr
        return count

    def builtin_append(args):
        if not args:
            return NIL
        result = NIL
        # Build the result list
        # All but last must be proper lists
        for i in range(len(args) - 1):
            if not is_proper_list(args[i]):
                raise SchemeError("append: argument must be a proper list")
        last = args[-1]
        # Build result by collecting all elements from all but last, then append last
        elems = []
        for i in range(len(args) - 1):
            x = args[i]
            while x is not NIL:
                elems.append(x.car)
                x = x.cdr
        # Now append last
        if is_proper_list(last):
            x = last
            while x is not NIL:
                elems.append(x.car)
                x = x.cdr
            return make_list(elems)
        else:
            result = last
            for e in reversed(elems):
                result = Pair(e, result)
            return result

    def builtin_reverse(args):
        x = args[0]
        if not is_proper_list(x):
            raise SchemeError("reverse: argument must be a proper list")
        result = NIL
        while x is not NIL:
            result = Pair(x.car, result)
            x = x.cdr
        return result

    def builtin_apply(args):
        # This is handled specially in eval_application, but also works as a builtin
        if len(args) < 2:
            raise SchemeError("apply: expected at least 2 arguments")
        f = args[0]
        extra = args[1:-1]
        lst = args[-1]
        if not is_proper_list(lst):
            raise SchemeError("apply: last argument must be a proper list")
        if not is_procedure(f):
            raise SchemeError("apply: first argument must be a procedure")
        all_args = extra + list_to_py(lst)
        if isinstance(f, Builtin):
            return f.func(all_args)
        else:
            new_env = bind_args(f.formals, all_args, f.env)
            return evaluate(f.body, new_env)

    def builtin_eq(args):
        a, b = args
        if is_integer(a) and is_integer(b):
            return a == b
        if is_bool(a) and is_bool(b):
            return a == b
        if a is NIL and b is NIL:
            return True
        if is_sym(a) and is_sym(b):
            return a.name == b.name
        return a is b

    def builtin_equal(args):
        return _equal(args[0], args[1])

    def _equal(a, b):
        if is_integer(a) and is_integer(b):
            return a == b
        if is_bool(a) and is_bool(b):
            return a == b
        if is_bool(a) or is_bool(b):
            return False
        if is_integer(a) or is_integer(b):
            return False
        if is_sym(a) and is_sym(b):
            return a.name == b.name
        if is_sym(a) or is_sym(b):
            return False
        if is_string(a) and is_string(b):
            return a == b
        if is_string(a) or is_string(b):
            return False
        if a is NIL and b is NIL:
            return True
        if a is NIL or b is NIL:
            return False
        if is_procedure(a) and is_procedure(b):
            return a is b
        if is_procedure(a) or is_procedure(b):
            return False
        if isinstance(a, Pair) and isinstance(b, Pair):
            return _equal(a.car, b.car) and _equal(a.cdr, b.cdr)
        if isinstance(a, Pair) or isinstance(b, Pair):
            return False
        return a is b

    def builtin_not(args):
        return args[0] is False

    def builtin_number_p(args):
        return is_integer(args[0])

    def builtin_symbol_p(args):
        return is_sym(args[0])

    def builtin_string_p(args):
        return is_string(args[0])

    def builtin_procedure_p(args):
        return is_procedure(args[0])

    def builtin_string_append(args):
        for a in args:
            if not is_string(a):
                raise SchemeError("string-append: all arguments must be strings")
        return ''.join(args)

    def builtin_display(args):
        out.append(display_repr(args[0]))
        return UNSPECIFIED

    def builtin_newline(args):
        out.append("\n")
        return UNSPECIFIED

    def builtin_error(args):
        msg = args[0]
        if not is_string(msg):
            raise SchemeError("error: first argument must be a string")
        full_msg = msg
        for irritant in args[1:]:
            full_msg += " " + write_repr(irritant)
        raise SchemeError(full_msg)

    builtins = {
        '+': Builtin('+', builtin_plus, 0, None),
        '*': Builtin('*', builtin_star, 0, None),
        '-': Builtin('-', builtin_minus, 1, None),
        'quotient': Builtin('quotient', builtin_quotient, 2, 2),
        'remainder': Builtin('remainder', builtin_remainder, 2, 2),
        'modulo': Builtin('modulo', builtin_modulo, 2, 2),
        '=': Builtin('=', make_compare(lambda a, b: a == b), 1, None),
        '<': Builtin('<', make_compare(lambda a, b: a < b), 1, None),
        '>': Builtin('>', make_compare(lambda a, b: a > b), 1, None),
        '<=': Builtin('<=', make_compare(lambda a, b: a <= b), 1, None),
        '>=': Builtin('>=', make_compare(lambda a, b: a >= b), 1, None),
        'number->string': Builtin('number->string', builtin_number_to_string, 1, 2),
        'cons': Builtin('cons', builtin_cons, 2, 2),
        'car': Builtin('car', builtin_car, 1, 1),
        'cdr': Builtin('cdr', builtin_cdr, 1, 1),
        'list': Builtin('list', builtin_list, 0, None),
        'null?': Builtin('null?', builtin_null_p, 1, 1),
        'pair?': Builtin('pair?', builtin_pair_p, 1, 1),
        'list?': Builtin('list?', builtin_list_p, 1, 1),
        'length': Builtin('length', builtin_length, 1, 1),
        'append': Builtin('append', builtin_append, 0, None),
        'reverse': Builtin('reverse', builtin_reverse, 1, 1),
        'apply': Builtin('apply', builtin_apply, 2, None),
        'eq?': Builtin('eq?', builtin_eq, 2, 2),
        'equal?': Builtin('equal?', builtin_equal, 2, 2),
        'not': Builtin('not', builtin_not, 1, 1),
        'number?': Builtin('number?', builtin_number_p, 1, 1),
        'symbol?': Builtin('symbol?', builtin_symbol_p, 1, 1),
        'string?': Builtin('string?', builtin_string_p, 1, 1),
        'procedure?': Builtin('procedure?', builtin_procedure_p, 1, 1),
        'string-append': Builtin('string-append', builtin_string_append, 0, None),
        'display': Builtin('display', builtin_display, 1, 1),
        'newline': Builtin('newline', builtin_newline, 0, 0),
        'error': Builtin('error', builtin_error, 1, None),
    }

    for name, proc in builtins.items():
        env.bindings[Sym(name)] = proc

    return env


# ---------- Main entry point ----------

def run(source):
    # Read all forms
    try:
        forms = read_all(source)
    except SchemeError as e:
        e.output = ''
        raise
    except RecursionError:
        err = SchemeError("stack overflow during reading")
        err.output = ''
        raise err
    except Exception as e:
        err = SchemeError(str(e))
        err.output = ''
        raise err

    # Evaluate
    out = []
    global_env = make_global_env(out)
    try:
        for form in forms:
            evaluate(form, global_env)
    except SchemeError as e:
        e.output = ''.join(out)
        raise
    except RecursionError:
        err = SchemeError("stack overflow")
        err.output = ''.join(out)
        raise err
    except Exception as e:
        err = SchemeError(str(e))
        err.output = ''.join(out)
        raise err

    return ''.join(out)
