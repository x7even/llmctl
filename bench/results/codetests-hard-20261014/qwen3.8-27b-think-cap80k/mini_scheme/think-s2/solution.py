import sys
import re

try:
    sys.set_int_max_str_digits(0)
except (AttributeError, ValueError):
    pass

sys.setrecursionlimit(500000)


class SchemeError(Exception):
    def __init__(self, msg=""):
        super().__init__(msg)
        self.output = ""


# ─── Data types ───────────────────────────────────────────────────────────────

class Symbol:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name
    def __eq__(self, other):
        return isinstance(other, Symbol) and self.name == other.name
    def __hash__(self):
        return hash(('sym', self.name))

class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr

class _EmptyList:
    pass

EMPTY_LIST = _EmptyList()

class _Unspecified:
    pass

UNSPECIFIED = _Unspecified()

class _Uninitialized:
    pass

UNINITIALIZED = _Uninitialized()

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


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_list(elems):
    r = EMPTY_LIST
    for e in reversed(elems):
        r = Pair(e, r)
    return r

def is_proper_list(x):
    while True:
        if x is EMPTY_LIST:
            return True
        if isinstance(x, Pair):
            x = x.cdr
        else:
            return False

def list_to_py(x):
    """Convert proper list to Python list. Raises if not proper."""
    result = []
    while x is not EMPTY_LIST:
        if not isinstance(x, Pair):
            raise SchemeError("not a proper list")
        result.append(x.car)
        x = x.cdr
    return result

def is_list_form(x):
    """Non-empty proper list."""
    if not isinstance(x, Pair):
        return False
    return is_proper_list(x)

def is_true(x):
    return x is not False

def int_to_str(n):
    if n == 0:
        return "0"
    neg = n < 0
    n = abs(n)
    digits = []
    while n > 0:
        n, r = divmod(n, 10)
        digits.append(chr(48 + r))
    if neg:
        digits.append('-')
    return ''.join(reversed(digits))

def int_to_str_radix(n, radix):
    if n == 0:
        return "0"
    neg = n < 0
    n = abs(n)
    digits = []
    while n > 0:
        n, r = divmod(n, radix)
        if r < 10:
            digits.append(chr(48 + r))
        else:
            digits.append(chr(97 + r - 10))
    if neg:
        digits.append('-')
    return ''.join(reversed(digits))


# ─── Display / Write ──────────────────────────────────────────────────────────

def _display_pair(x, repr_fn):
    parts = ['(']
    first = True
    while True:
        if x is EMPTY_LIST:
            parts.append(')')
            break
        if not isinstance(x, Pair):
            if not first:
                parts.append(' . ')
            else:
                parts.append(' . ')
            parts.append(repr_fn(x))
            parts.append(')')
            break
        if not first:
            parts.append(' ')
        first = False
        parts.append(repr_fn(x.car))
        x = x.cdr
    return ''.join(parts)

def display_repr(x):
    if isinstance(x, int):
        return int_to_str(x)
    if x is True:
        return "#t"
    if x is False:
        return "#f"
    if isinstance(x, str):
        return x
    if isinstance(x, Symbol):
        return x.name
    if x is EMPTY_LIST:
        return "()"
    if isinstance(x, (Closure, Builtin)):
        return "#<procedure>"
    if x is UNSPECIFIED:
        return ""
    if isinstance(x, Pair):
        return _display_pair(x, display_repr)
    return ""

def write_repr(x):
    if isinstance(x, str):
        s = x.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        return '"' + s + '"'
    if isinstance(x, int):
        return int_to_str(x)
    if x is True:
        return "#t"
    if x is False:
        return "#f"
    if isinstance(x, Symbol):
        return x.name
    if x is EMPTY_LIST:
        return "()"
    if isinstance(x, (Closure, Builtin)):
        return "#<procedure>"
    if x is UNSPECIFIED:
        return ""
    if isinstance(x, Pair):
        return _display_pair(x, write_repr)
    return ""


# ─── Reader ───────────────────────────────────────────────────────────────────

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
            tokens.append(('LPAREN', '('))
            i += 1
        elif c == ')':
            tokens.append(('RPAREN', ')'))
            i += 1
        elif c == '"':
            i += 1
            chars = []
            while i < n:
                if source[i] == '\\' and i + 1 < n:
                    nxt = source[i + 1]
                    if nxt == '"':
                        chars.append('"')
                        i += 2
                    elif nxt == '\\':
                        chars.append('\\')
                        i += 2
                    elif nxt == 'n':
                        chars.append('\n')
                        i += 2
                    else:
                        raise SchemeError("invalid escape in string")
                elif source[i] == '"':
                    i += 1
                    break
                else:
                    chars.append(source[i])
                    i += 1
            else:
                raise SchemeError("unterminated string")
            tokens.append(('STRING', ''.join(chars)))
        elif c == "'":
            tokens.append(('QUOTE', "'"))
            i += 1
        else:
            start = i
            while i < n and source[i] not in ' \t\n\r()";\'' :
                i += 1
            tokens.append(('ATOM', source[start:i]))
    return tokens

_INT_RE = re.compile(r'[+-]?[0-9]+\Z')

def parse_atom(token):
    if token == '#t':
        return True
    if token == '#f':
        return False
    if token.startswith('#'):
        raise SchemeError(f"invalid literal: {token}")
    if _INT_RE.match(token):
        return int(token)
    return Symbol(token)

def parse(tokens, pos):
    if pos >= len(tokens):
        raise SchemeError("unexpected end of input")
    kind, value = tokens[pos]
    if kind == 'LPAREN':
        return parse_list(tokens, pos + 1)
    if kind == 'RPAREN':
        raise SchemeError("unexpected )")
    if kind == 'QUOTE':
        datum, new_pos = parse(tokens, pos + 1)
        return make_list([Symbol('quote'), datum]), new_pos
    if kind == 'STRING':
        return value, pos + 1
    if kind == 'ATOM':
        return parse_atom(value), pos + 1
    raise SchemeError("unexpected token")

def parse_list(tokens, pos):
    if pos >= len(tokens):
        raise SchemeError("unbalanced (")
    kind, value = tokens[pos]
    if kind == 'RPAREN':
        return EMPTY_LIST, pos + 1

    elements = []
    while True:
        if pos >= len(tokens):
            raise SchemeError("unbalanced (")
        kind, value = tokens[pos]
        if kind == 'RPAREN':
            return make_list(elements), pos + 1
        if kind == 'ATOM' and value == '.' and elements:
            pos += 1
            if pos >= len(tokens):
                raise SchemeError("unbalanced (")
            tail, pos = parse(tokens, pos)
            if pos >= len(tokens) or tokens[pos][0] != 'RPAREN':
                raise SchemeError("invalid dotted list")
            pos += 1
            result = tail
            for elem in reversed(elements):
                result = Pair(elem, result)
            return result, pos
        elem, pos = parse(tokens, pos)
        elements.append(elem)


def read_all(source):
    tokens = tokenize(source)
    forms = []
    pos = 0
    while pos < len(tokens):
        form, pos = parse(tokens, pos)
        forms.append(form)
    return forms


# ─── Environment ──────────────────────────────────────────────────────────────

class Env:
    __slots__ = ('bindings', 'parent')
    def __init__(self, bindings, parent=None):
        self.bindings = bindings
        self.parent = parent

    def lookup(self, name):
        env = self
        while env is not None:
            if name in env.bindings:
                val = env.bindings[name]
                if val is UNINITIALIZED:
                    raise SchemeError(f"uninitialized variable: {name}")
                return val
            env = env.parent
        raise SchemeError(f"unbound variable: {name}")

    def set(self, name, value):
        env = self
        while env is not None:
            if name in env.bindings:
                env.bindings[name] = value
                return
            env = env.parent
        raise SchemeError(f"unbound variable: {name}")

    def define(self, name, value):
        self.bindings[name] = value


# ─── Evaluator ────────────────────────────────────────────────────────────────

_current_output = None

SPECIAL_FORMS = {'quote', 'if', 'define', 'set!', 'begin', 'cond',
                 'and', 'or', 'let', 'let*', 'letrec'}

class TailCall:
    __slots__ = ('form', 'env')
    def __init__(self, form, env):
        self.form = form
        self.env = env


def process_internal_defines(body, env):
    internal_names = []
    for form in body:
        if not is_list_form(form):
            continue
        head = form.car
        if not (isinstance(head, Symbol) and head.name == 'define'):
            continue
        rest = form.cdr
        if rest is EMPTY_LIST:
            raise SchemeError("malformed define")
        name_form = rest.car
        if isinstance(name_form, Symbol):
            internal_names.append(name_form.name)
        elif is_list_form(name_form):
            if isinstance(name_form.car, Symbol):
                internal_names.append(name_form.car.name)
            else:
                raise SchemeError("malformed define")
        else:
            raise SchemeError("malformed define")
    if not internal_names:
        return body, env
    new_bindings = {name: UNINITIALIZED for name in internal_names}
    new_env = Env(new_bindings, env)
    return body, new_env


def parse_formals(formals):
    if isinstance(formals, Symbol):
        return ('rest', formals)
    if formals is EMPTY_LIST:
        return ('fixed', [])
    if isinstance(formals, Pair):
        params = []
        p = formals
        while isinstance(p, Pair):
            if isinstance(p.cdr, Pair) or p.cdr is EMPTY_LIST:
                if not isinstance(p.car, Symbol):
                    raise SchemeError("formal must be a symbol")
                params.append(p.car)
                p = p.cdr
            else:
                if not isinstance(p.car, Symbol):
                    raise SchemeError("formal must be a symbol")
                params.append(p.car)
                if not isinstance(p.cdr, Symbol):
                    raise SchemeError("rest formal must be a symbol")
                return ('dotted', (params, p.cdr))
        return ('fixed', params)
    raise SchemeError("invalid formals")


def setup_call_env(proc, args):
    if isinstance(proc, Builtin):
        return None
    ftype, fparams = parse_formals(proc.formals)
    if ftype == 'fixed':
        if len(args) != len(fparams):
            raise SchemeError(f"arity mismatch: expected {len(fparams)}, got {len(args)}")
        bindings = {p.name: a for p, a in zip(fparams, args)}
    elif ftype == 'dotted':
        named, rest_sym = fparams
        if len(args) < len(named):
            raise SchemeError(f"arity mismatch: expected at least {len(named)}, got {len(args)}")
        bindings = {p.name: a for p, a in zip(named, args[:len(named)])}
        rest_args = args[len(named):]
        bindings[rest_sym.name] = make_list(rest_args)
    else:  # rest
        bindings = {fparams.name: make_list(args)}
    return Env(bindings, proc.env)


def enter_body(body, env):
    body, env = process_internal_defines(body, env)
    for f in body[:-1]:
        eval_form(f, env)
    return body[-1], env


def eval_form(form, env):
    if isinstance(form, int) or isinstance(form, str) or form is True or form is False:
        return form
    if isinstance(form, Symbol):
        return env.lookup(form.name)
    if form is EMPTY_LIST:
        raise SchemeError("invalid form: ()")
    if not isinstance(form, Pair):
        raise SchemeError("invalid form")
    if not is_proper_list(form):
        raise SchemeError("dotted form used as application")

    head = form.car
    if isinstance(head, Symbol) and head.name in SPECIAL_FORMS:
        return eval_special_form(head.name, form, env)

    # Application (non-tail)
    proc = eval_form(head, env)
    args = [eval_form(a, env) for a in list_to_py(form.cdr)]
    if not isinstance(proc, (Closure, Builtin)):
        raise SchemeError("not a procedure")
    if isinstance(proc, Builtin):
        return proc.func(args)
    new_env = setup_call_env(proc, args)
    body, new_env = process_internal_defines(proc.body, new_env)
    for f in body[:-1]:
        eval_form(f, new_env)
    return eval_tail(body[-1], new_env)


def eval_tail(form, env):
    while True:
        if isinstance(form, int) or isinstance(form, str) or form is True or form is False:
            return form
        if isinstance(form, Symbol):
            return env.lookup(form.name)
        if form is EMPTY_LIST:
            raise SchemeError("invalid form: ()")
        if not isinstance(form, Pair):
            raise SchemeError("invalid form")
        if not is_proper_list(form):
            raise SchemeError("dotted form used as application")

        head = form.car
        if isinstance(head, Symbol) and head.name in SPECIAL_FORMS:
            result = eval_special_form_tail(head.name, form, env)
            if isinstance(result, TailCall):
                form, env = result.form, result.env
                continue
            return result

        # Application in tail position
        proc = eval_form(head, env)
        args = [eval_form(a, env) for a in list_to_py(form.cdr)]
        if not isinstance(proc, (Closure, Builtin)):
            raise SchemeError("not a procedure")

        if isinstance(proc, Builtin):
            if proc is _apply_builtin:
                if len(args) < 2:
                    raise SchemeError("apply: at least 2 arguments")
                f = args[0]
                if not isinstance(f, (Closure, Builtin)):
                    raise SchemeError("apply: first argument must be a procedure")
                middle = args[1:-1]
                lst = args[-1]
                if not is_proper_list(lst):
                    raise SchemeError("apply: last argument must be a proper list")
                all_args = middle + list_to_py(lst)
                if isinstance(f, Builtin):
                    return f.func(all_args)
                new_env = setup_call_env(f, all_args)
                body, new_env = process_internal_defines(f.body, new_env)
                for bf in body[:-1]:
                    eval_form(bf, new_env)
                form, env = body[-1], new_env
                continue
            return proc.func(args)
        else:
            new_env = setup_call_env(proc, args)
            body, new_env = process_internal_defines(proc.body, new_env)
            for f in body[:-1]:
                eval_form(f, new_env)
            form, env = body[-1], new_env
            continue


def eval_special_form(name, form, env):
    rest = form.cdr
    if name == 'quote':
        if rest is EMPTY_LIST or rest.cdr is not EMPTY_LIST:
            raise SchemeError("malformed quote")
        return rest.car

    if name == 'if':
        elems = list_to_py(rest)
        if len(elems) not in (2, 3):
            raise SchemeError("malformed if")
        test = eval_form(elems[0], env)
        if is_true(test):
            return eval_form(elems[1], env)
        else:
            if len(elems) == 3:
                return eval_form(elems[2], env)
            return UNSPECIFIED

    if name == 'define':
        return _eval_define(form, env)

    if name == 'set!':
        elems = list_to_py(rest)
        if len(elems) != 2:
            raise SchemeError("malformed set!")
        name_form, expr = elems
        if not isinstance(name_form, Symbol):
            raise SchemeError("set! name must be a symbol")
        value = eval_form(expr, env)
        env.set(name_form.name, value)
        return UNSPECIFIED

    if name == 'begin':
        exprs = list_to_py(rest)
        if not exprs:
            raise SchemeError("empty begin")
        for e in exprs[:-1]:
            eval_form(e, env)
        return eval_form(exprs[-1], env)

    if name == 'cond':
        clauses = list_to_py(rest)
        if not clauses:
            raise SchemeError("empty cond")
        for i, clause in enumerate(clauses):
            if not is_list_form(clause):
                raise SchemeError("malformed cond clause")
            test = clause.car
            exprs = list_to_py(clause.cdr)
            is_else = isinstance(test, Symbol) and test.name == 'else'
            if is_else:
                if i != len(clauses) - 1:
                    raise SchemeError("else must be last cond clause")
                for e in exprs:
                    val = eval_form(e, env)
                if exprs:
                    return val
                return UNSPECIFIED
            else:
                test_val = eval_form(test, env)
                if is_true(test_val):
                    if not exprs:
                        return test_val
                    for e in exprs:
                        val = eval_form(e, env)
                    return val
        return UNSPECIFIED

    if name == 'and':
        exprs = list_to_py(rest)
        for e in exprs:
            val = eval_form(e, env)
            if val is False:
                return False
        return True if not exprs else val

    if name == 'or':
        exprs = list_to_py(rest)
        if not exprs:
            return False
        for i, e in enumerate(exprs):
            val = eval_form(e, env)
            if val is not False:
                return val
        return False

    if name == 'let':
        return _eval_let(rest, env, 'let')

    if name == 'let*':
        return _eval_let(rest, env, 'let*')

    if name == 'letrec':
        return _eval_let(rest, env, 'letrec')

    raise SchemeError(f"unknown special form: {name}")


def eval_special_form_tail(name, form, env):
    rest = form.cdr
    if name == 'quote':
        if rest is EMPTY_LIST or rest.cdr is not EMPTY_LIST:
            raise SchemeError("malformed quote")
        return rest.car

    if name == 'if':
        elems = list_to_py(rest)
        if len(elems) not in (2, 3):
            raise SchemeError("malformed if")
        test = eval_form(elems[0], env)
        if is_true(test):
            return TailCall(elems[1], env)
        else:
            if len(elems) == 3:
                return TailCall(elems[2], env)
            return UNSPECIFIED

    if name == 'define':
        return _eval_define(form, env)

    if name == 'set!':
        elems = list_to_py(rest)
        if len(elems) != 2:
            raise SchemeError("malformed set!")
        name_form, expr = elems
        if not isinstance(name_form, Symbol):
            raise SchemeError("set! name must be a symbol")
        value = eval_form(expr, env)
        env.set(name_form.name, value)
        return UNSPECIFIED

    if name == 'begin':
        exprs = list_to_py(rest)
        if not exprs:
            raise SchemeError("empty begin")
        for e in exprs[:-1]:
            eval_form(e, env)
        return TailCall(exprs[-1], env)

    if name == 'cond':
        clauses = list_to_py(rest)
        if not clauses:
            raise SchemeError("empty cond")
        for i, clause in enumerate(clauses):
            if not is_list_form(clause):
                raise SchemeError("malformed cond clause")
            test = clause.car
            exprs = list_to_py(clause.cdr)
            is_else = isinstance(test, Symbol) and test.name == 'else'
            if is_else:
                if i != len(clauses) - 1:
                    raise SchemeError("else must be last cond clause")
                for e in exprs[:-1]:
                    eval_form(e, env)
                if exprs:
                    return TailCall(exprs[-1], env)
                return UNSPECIFIED
            else:
                test_val = eval_form(test, env)
                if is_true(test_val):
                    if not exprs:
                        return test_val
                    for e in exprs[:-1]:
                        eval_form(e, env)
                    return TailCall(exprs[-1], env)
        return UNSPECIFIED

    if name == 'and':
        exprs = list_to_py(rest)
        if not exprs:
            return True
        for i, e in enumerate(exprs):
            if i == len(exprs) - 1:
                return TailCall(e, env)
            val = eval_form(e, env)
            if val is False:
                return False
        return True

    if name == 'or':
        exprs = list_to_py(rest)
        if not exprs:
            return False
        for i, e in enumerate(exprs):
            if i == len(exprs) - 1:
                return TailCall(e, env)
            val = eval_form(e, env)
            if val is not False:
                return val
        return False

    if name == 'let':
        return _eval_let_tail(rest, env, 'let')

    if name == 'let*':
        return _eval_let_tail(rest, env, 'let*')

    if name == 'letrec':
        return _eval_let_tail(rest, env, 'letrec')

    raise SchemeError(f"unknown special form: {name}")


def _eval_define(form, env):
    rest = form.cdr
    if rest is EMPTY_LIST:
        raise SchemeError("malformed define")
    name_form = rest.car
    if isinstance(name_form, Symbol):
        name = name_form.name
        exprs = list_to_py(rest.cdr)
        if len(exprs) != 1:
            raise SchemeError("malformed define")
        value = eval_form(exprs[0], env)
        env.define(name, value)
    elif is_list_form(name_form):
        fname = name_form.car
        if not isinstance(fname, Symbol):
            raise SchemeError("malformed define")
        formals = name_form.cdr
        body = list_to_py(rest.cdr)
        if not body:
            raise SchemeError("empty body in define")
        closure = Closure(formals, body, env)
        env.define(fname.name, closure)
    else:
        raise SchemeError("malformed define")
    return UNSPECIFIED


def _parse_let_bindings(bindings_form):
    if not is_proper_list(bindings_form):
        raise SchemeError("invalid let bindings")
    bindings_list = list_to_py(bindings_form)
    names = []
    inits = []
    for b in bindings_list:
        if not is_list_form(b):
            raise SchemeError("invalid let binding")
        bl = list_to_py(b)
        if len(bl) != 2:
            raise SchemeError("invalid let binding")
        name_form, init_form = bl
        if not isinstance(name_form, Symbol):
            raise SchemeError("let binding name must be a symbol")
        names.append(name_form)
        inits.append(init_form)
    return names, inits


def _eval_let(rest, env, kind):
    # rest is the cdr of the let form: ((v1 e1) ...) body...
    # Check for named let
    first = rest.car
    if isinstance(first, Symbol):
        # Named let: (let name ((v init) ...) body...)
        name_sym = first
        rest2 = rest.cdr
        if rest2 is EMPTY_LIST:
            raise SchemeError("malformed named let")
        bindings_form = rest2.car
        body = list_to_py(rest2.cdr)
        if not body:
            raise SchemeError("empty body")
        names, inits = _parse_let_bindings(bindings_form)
        # Evaluate inits in outer scope
        values = [eval_form(init, env) for init in inits]
        # Create closure for the name
        formals = make_list(names)
        # The body of the named-let procedure
        proc_body = body
        # Create a frame for the name
        # The closure's env should include the name binding
        # We need a frame that has the name -> closure, and parent = env
        # But the closure references itself, so we create the frame first
        name_frame = {}
        name_env = Env(name_frame, env)
        closure = Closure(formals, proc_body, name_env)
        name_frame[name_sym.name] = closure
        # Call the closure with the init values (non-tail)
        new_env = setup_call_env(closure, values)
        body2, new_env = process_internal_defines(closure.body, new_env)
        for f in body2[:-1]:
            eval_form(f, new_env)
        return eval_tail(body2[-1], new_env)

    # Regular let / let* / letrec
    bindings_form = first
    body = list_to_py(rest.cdr)
    if not body:
        raise SchemeError("empty body")
    names, inits = _parse_let_bindings(bindings_form)

    if kind == 'let':
        values = [eval_form(init, env) for init in inits]
        new_bindings = {n.name: v for n, v in zip(names, values)}
        new_env = Env(new_bindings, env)
        body2, new_env = process_internal_defines(body, new_env)
        for f in body2[:-1]:
            eval_form(f, new_env)
        return eval_tail(body2[-1], new_env)

    elif kind == 'let*':
        new_env = env
        for n, init in zip(names, inits):
            val = eval_form(init, new_env)
            new_env = Env({n.name: val}, new_env)
        body2, new_env = process_internal_defines(body, new_env)
        for f in body2[:-1]:
            eval_form(f, new_env)
        return eval_tail(body2[-1], new_env)

    elif kind == 'letrec':
        new_bindings = {n.name: UNINITIALIZED for n in names}
        new_env = Env(new_bindings, env)
        for n, init in zip(names, inits):
            val = eval_form(init, new_env)
            new_env.define(n.name, val)
        body2, new_env = process_internal_defines(body, new_env)
        for f in body2[:-1]:
            eval_form(f, new_env)
        return eval_tail(body2[-1], new_env)

    raise SchemeError("unknown let kind")


def _eval_let_tail(rest, env, kind):
    first = rest.car
    if isinstance(first, Symbol):
        # Named let in tail position
        name_sym = first
        rest2 = rest.cdr
        if rest2 is EMPTY_LIST:
            raise SchemeError("malformed named let")
        bindings_form = rest2.car
        body = list_to_py(rest2.cdr)
        if not body:
            raise SchemeError("empty body")
        names, inits = _parse_let_bindings(bindings_form)
        values = [eval_form(init, env) for init in inits]
        formals = make_list(names)
        name_frame = {}
        name_env = Env(name_frame, env)
        closure = Closure(formals, body, name_env)
        name_frame[name_sym.name] = closure
        new_env = setup_call_env(closure, values)
        body2, new_env = process_internal_defines(closure.body, new_env)
        for f in body2[:-1]:
            eval_form(f, new_env)
        return TailCall(body2[-1], new_env)

    bindings_form = first
    body = list_to_py(rest.cdr)
    if not body:
        raise SchemeError("empty body")
    names, inits = _parse_let_bindings(bindings_form)

    if kind == 'let':
        values = [eval_form(init, env) for init in inits]
        new_bindings = {n.name: v for n, v in zip(names, values)}
        new_env = Env(new_bindings, env)
        body2, new_env = process_internal_defines(body, new_env)
        for f in body2[:-1]:
            eval_form(f, new_env)
        return TailCall(body2[-1], new_env)

    elif kind == 'let*':
        new_env = env
        for n, init in zip(names, inits):
            val = eval_form(init, new_env)
            new_env = Env({n.name: val}, new_env)
        body2, new_env = process_internal_defines(body, new_env)
        for f in body2[:-1]:
            eval_form(f, new_env)
        return TailCall(body2[-1], new_env)

    elif kind == 'letrec':
        new_bindings = {n.name: UNINITIALIZED for n in names}
        new_env = Env(new_bindings, env)
        for n, init in zip(names, inits):
            val = eval_form(init, new_env)
            new_env.define(n.name, val)
        body2, new_env = process_internal_defines(body, new_env)
        for f in body2[:-1]:
            eval_form(f, new_env)
        return TailCall(body2[-1], new_env)

    raise SchemeError("unknown let kind")


# ─── Builtins ─────────────────────────────────────────────────────────────────

def _builtin_plus(args):
    for a in args:
        if not isinstance(a, int):
            raise SchemeError("+ : argument must be an integer")
    return sum(args)

def _builtin_mul(args):
    for a in args:
        if not isinstance(a, int):
            raise SchemeError("* : argument must be an integer")
    r = 1
    for a in args:
        r *= a
    return r

def _builtin_sub(args):
    if len(args) == 0:
        raise SchemeError("- : expected at least 1 argument")
    for a in args:
        if not isinstance(a, int):
            raise SchemeError("- : argument must be an integer")
    if len(args) == 1:
        return -args[0]
    r = args[0]
    for a in args[1:]:
        r -= a
    return r

def _builtin_quotient(args):
    if len(args) != 2:
        raise SchemeError("quotient: expected 2 arguments")
    a, b = args
    if not isinstance(a, int) or not isinstance(b, int):
        raise SchemeError("quotient: arguments must be integers")
    if b == 0:
        raise SchemeError("quotient: division by zero")
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        q = -q
    return q

def _builtin_remainder(args):
    if len(args) != 2:
        raise SchemeError("remainder: expected 2 arguments")
    a, b = args
    if not isinstance(a, int) or not isinstance(b, int):
        raise SchemeError("remainder: arguments must be integers")
    if b == 0:
        raise SchemeError("remainder: division by zero")
    r = abs(a) % abs(b)
    if a < 0:
        r = -r
    return r

def _builtin_modulo(args):
    if len(args) != 2:
        raise SchemeError("modulo: expected 2 arguments")
    a, b = args
    if not isinstance(a, int) or not isinstance(b, int):
        raise SchemeError("modulo: arguments must be integers")
    if b == 0:
        raise SchemeError("modulo: division by zero")
    r = abs(a) % abs(b)
    if b < 0:
        r = -r
    return r

def _builtin_compare(op_name, op_func):
    def _cmp(args):
        if len(args) == 0:
            raise SchemeError(f"{op_name}: expected at least 1 argument")
        for a in args:
            if not isinstance(a, int):
                raise SchemeError(f"{op_name}: argument must be an integer")
        for i in range(len(args) - 1):
            if not op_func(args[i], args[i + 1]):
                return False
        return True
    return _cmp

def _builtin_eq(args):
    if len(args) != 2:
        raise SchemeError("eq?: expected 2 arguments")
    a, b = args
    if isinstance(a, int) and isinstance(b, int):
        return a == b
    if isinstance(a, bool) and isinstance(b, bool):
        return a == b
    if isinstance(a, Symbol) and isinstance(b, Symbol):
        return a.name == b.name
    if a is EMPTY_LIST and b is EMPTY_LIST:
        return True
    if isinstance(a, (Closure, Builtin)) and isinstance(b, (Closure, Builtin)):
        return a is b
    return a is b

def _builtin_equal(args):
    if len(args) != 2:
        raise SchemeError("equal?: expected 2 arguments")
    return _scheme_equal(args[0], args[1])

def _scheme_equal(a, b):
    a_is_pair = isinstance(a, Pair) or a is EMPTY_LIST
    b_is_pair = isinstance(b, Pair) or b is EMPTY_LIST
    if a_is_pair or b_is_pair:
        if not (a_is_pair and b_is_pair):
            return False
        while True:
            if a is EMPTY_LIST and b is EMPTY_LIST:
                return True
            if a is EMPTY_LIST or b is EMPTY_LIST:
                return False
            if not isinstance(a, Pair) or not isinstance(b, Pair):
                return False
            if not _scheme_equal(a.car, b.car):
                return False
            a = a.cdr
            b = b.cdr
    if isinstance(a, int) and isinstance(b, int):
        return a == b
    if isinstance(a, bool) and isinstance(b, bool):
        return a == b
    if isinstance(a, str) and isinstance(b, str):
        return a == b
    if isinstance(a, Symbol) and isinstance(b, Symbol):
        return a.name == b.name
    if isinstance(a, (Closure, Builtin)) and isinstance(b, (Closure, Builtin)):
        return a is b
    if a is UNSPECIFIED and b is UNSPECIFIED:
        return True
    return False

def _builtin_not(args):
    if len(args) != 1:
        raise SchemeError("not: expected 1 argument")
    return args[0] is False

def _builtin_number_p(args):
    if len(args) != 1:
        raise SchemeError("number?: expected 1 argument")
    return isinstance(args[0], int)

def _builtin_symbol_p(args):
    if len(args) != 1:
        raise SchemeError("symbol?: expected 1 argument")
    return isinstance(args[0], Symbol)

def _builtin_string_p(args):
    if len(args) != 1:
        raise SchemeError("string?: expected 1 argument")
    return isinstance(args[0], str)

def _builtin_procedure_p(args):
    if len(args) != 1:
        raise SchemeError("procedure?: expected 1 argument")
    return isinstance(args[0], (Closure, Builtin))

def _builtin_cons(args):
    if len(args) != 2:
        raise SchemeError("cons: expected 2 arguments")
    return Pair(args[0], args[1])

def _builtin_car(args):
    if len(args) != 1:
        raise SchemeError("car: expected 1 argument")
    a = args[0]
    if not isinstance(a, Pair):
        raise SchemeError("car: argument must be a pair")
    return a.car

def _builtin_cdr(args):
    if len(args) != 1:
        raise SchemeError("cdr: expected 1 argument")
    a = args[0]
    if not isinstance(a, Pair):
        raise SchemeError("cdr: argument must be a pair")
    return a.cdr

def _builtin_list(args):
    return make_list(args)

def _builtin_null_p(args):
    if len(args) != 1:
        raise SchemeError("null?: expected 1 argument")
    return args[0] is EMPTY_LIST

def _builtin_pair_p(args):
    if len(args) != 1:
        raise SchemeError("pair?: expected 1 argument")
    return isinstance(args[0], Pair)

def _builtin_list_p(args):
    if len(args) != 1:
        raise SchemeError("list?: expected 1 argument")
    return is_proper_list(args[0])

def _builtin_length(args):
    if len(args) != 1:
        raise SchemeError("length: expected 1 argument")
    l = args[0]
    if not is_proper_list(l):
        raise SchemeError("length: argument must be a proper list")
    n = 0
    p = l
    while p is not EMPTY_LIST:
        n += 1
        p = p.cdr
    return n

def _builtin_append(args):
    if len(args) == 0:
        return EMPTY_LIST
    if len(args) == 1:
        return args[0]
    # All but last must be proper lists
    for a in args[:-1]:
        if not is_proper_list(a):
            raise SchemeError("append: all but last argument must be proper lists")
    last = args[-1]
    # Build result
    result = last
    for l in reversed(args[:-1]):
        # Prepend l to result
        # Collect elements of l
        elems = []
        p = l
        while p is not EMPTY_LIST:
            elems.append(p.car)
            p = p.cdr
        for e in reversed(elems):
            result = Pair(e, result)
    return result

def _builtin_reverse(args):
    if len(args) != 1:
        raise SchemeError("reverse: expected 1 argument")
    l = args[0]
    if not is_proper_list(l):
        raise SchemeError("reverse: argument must be a proper list")
    result = EMPTY_LIST
    p = l
    while p is not EMPTY_LIST:
        result = Pair(p.car, result)
        p = p.cdr
    return result

_apply_builtin = None  # Will be set after creation

def _builtin_apply(args):
    if len(args) < 2:
        raise SchemeError("apply: at least 2 arguments")
    f = args[0]
    if not isinstance(f, (Closure, Builtin)):
        raise SchemeError("apply: first argument must be a procedure")
    middle = args[1:-1]
    lst = args[-1]
    if not is_proper_list(lst):
        raise SchemeError("apply: last argument must be a proper list")
    all_args = middle + list_to_py(lst)
    if isinstance(f, Builtin):
        return f.func(all_args)
    new_env = setup_call_env(f, all_args)
    body, new_env = process_internal_defines(f.body, new_env)
    for bf in body[:-1]:
        eval_form(bf, new_env)
    return eval_tail(body[-1], new_env)

def _builtin_number_to_string(args):
    if len(args) not in (1, 2):
        raise SchemeError("number->string: expected 1 or 2 arguments")
    n = args[0]
    if not isinstance(n, int):
        raise SchemeError("number->string: first argument must be an integer")
    if len(args) == 1:
        return int_to_str(n)
    radix = args[1]
    if not isinstance(radix, int) or radix not in (2, 8, 10, 16):
        raise SchemeError("number->string: invalid radix")
    return int_to_str_radix(n, radix)

def _builtin_string_append(args):
    for a in args:
        if not isinstance(a, str):
            raise SchemeError("string-append: all arguments must be strings")
    return ''.join(args)

def _builtin_display(args):
    if len(args) != 1:
        raise SchemeError("display: expected 1 argument")
    _current_output.append(display_repr(args[0]))
    return UNSPECIFIED

def _builtin_newline(args):
    if len(args) != 0:
        raise SchemeError("newline: expected 0 arguments")
    _current_output.append("\n")
    return UNSPECIFIED

def _builtin_error(args):
    if len(args) < 1:
        raise SchemeError("error: expected at least 1 argument")
    msg = args[0]
    if not isinstance(msg, str):
        raise SchemeError("error: first argument must be a string")
    parts = [msg]
    for irritant in args[1:]:
        parts.append(' ')
        parts.append(write_repr(irritant))
    raise SchemeError(''.join(parts))


def create_global_bindings():
    globals_dict = {
        '+': Builtin('+', _builtin_plus),
        '*': Builtin('*', _builtin_mul),
        '-': Builtin('-', _builtin_sub),
        'quotient': Builtin('quotient', _builtin_quotient),
        'remainder': Builtin('remainder', _builtin_remainder),
        'modulo': Builtin('modulo', _builtin_modulo),
        '=': Builtin('=', _builtin_compare('=', lambda a, b: a == b)),
        '<': Builtin('<', _builtin_compare('<', lambda a, b: a < b)),
        '>': Builtin('>', _builtin_compare('>', lambda a, b: a > b)),
        '<=': Builtin('<=', _builtin_compare('<=', lambda a, b: a <= b)),
        '>=': Builtin('>=', _builtin_compare('>=', lambda a, b: a >= b)),
        'number->string': Builtin('number->string', _builtin_number_to_string),
        'cons': Builtin('cons', _builtin_cons),
        'car': Builtin('car', _builtin_car),
        'cdr': Builtin('cdr', _builtin_cdr),
        'list': Builtin('list', _builtin_list),
        'null?': Builtin('null?', _builtin_null_p),
        'pair?': Builtin('pair?', _builtin_pair_p),
        'list?': Builtin('list?', _builtin_list_p),
        'length': Builtin('length', _builtin_length),
        'append': Builtin('append', _builtin_append),
        'reverse': Builtin('reverse', _builtin_reverse),
        'apply': Builtin('apply', _builtin_apply),
        'eq?': Builtin('eq?', _builtin_eq),
        'equal?': Builtin('equal?', _builtin_equal),
        'not': Builtin('not', _builtin_not),
        'number?': Builtin('number?', _builtin_number_p),
        'symbol?': Builtin('symbol?', _builtin_symbol_p),
        'string?': Builtin('string?', _builtin_string_p),
        'procedure?': Builtin('procedure?', _builtin_procedure_p),
        'string-append': Builtin('string-append', _builtin_string_append),
        'display': Builtin('display', _builtin_display),
        'newline': Builtin('newline', _builtin_newline),
        'error': Builtin('error', _builtin_error),
    }
    return globals_dict


# Set the _apply_builtin reference
_apply_builtin = Builtin('apply', _builtin_apply)
# We need to set it after creation; let's use a different approach:
# Actually, let's just reference it by identity in the tail evaluator.
# We'll store a reference to the apply builtin.

# ─── Run ──────────────────────────────────────────────────────────────────────

def run(source):
    global _current_output, _apply_builtin
    _current_output = []

    try:
        try:
            sys.set_int_max_str_digits(0)
        except (AttributeError, ValueError):
            pass

        forms = read_all(source)
        global_env = Env(create_global_bindings(), None)

        # Set _apply_builtin to the actual builtin in this env
        _apply_builtin = global_env.bindings['apply']

        for form in forms:
            eval_form(form, global_env)

        return ''.join(_current_output)

    except SchemeError as e:
        e.output = ''.join(_current_output)
        raise
    except RecursionError:
        e = SchemeError("stack overflow")
        e.output = ''.join(_current_output)
        raise e
    except Exception as e:
        e = SchemeError(str(e))
        e.output = ''.join(_current_output)
        raise e