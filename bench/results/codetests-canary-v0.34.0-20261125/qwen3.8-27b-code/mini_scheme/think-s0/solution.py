import sys
import re

try:
    sys.set_int_max_str_digits(0)
except AttributeError:
    pass

sys.setrecursionlimit(200000)


class SchemeError(Exception):
    def __init__(self, message, output=''):
        super().__init__(message)
        self.output = output


class _Internal(Exception):
    pass


class Symbol:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name
    def __eq__(self, other):
        return isinstance(other, Symbol) and self.name == other.name
    def __hash__(self):
        return hash(('sym', self.name))
    def __repr__(self):
        return self.name


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


class _Unspecified:
    _inst = None
    def __new__(cls):
        if cls._inst is None:
            cls._inst = super().__new__(cls)
        return cls._inst
    def __repr__(self):
        return '#<unspecified>'

UNSPECIFIED = _Unspecified()
UNBOUND_INTERNAL = object()

# Symbol constants
SYM_QUOTE = Symbol('quote')
SYM_IF = Symbol('if')
SYM_DEFINE = Symbol('define')
SYM_SET_BANG = Symbol('set!')
SYM_BEGIN = Symbol('begin')
SYM_COND = Symbol('cond')
SYM_AND = Symbol('and')
SYM_OR = Symbol('or')
SYM_LET = Symbol('let')
SYM_LET_STAR = Symbol('let*')
SYM_LETREC = Symbol('letrec')
SYM_LAMBDA = Symbol('lambda')
SYM_ELSE = Symbol('else')
SYM_APPLY = Symbol('apply')

INT_RE = re.compile(r'^[+-]?[0-9]+$')


# ===================== READER =====================

def _skip_ws(source, pos, n):
    while pos < n:
        c = source[pos]
        if c in ' \t\n\r':
            pos += 1
        elif c == ';':
            while pos < n and source[pos] != '\n':
                pos += 1
        else:
            break
    return pos


def _read_string(source, pos, n):
    assert source[pos] == '"'
    pos += 1
    chars = []
    while pos < n:
        c = source[pos]
        if c == '"':
            return ''.join(chars), pos + 1
        elif c == '\\':
            pos += 1
            if pos >= n:
                raise _Internal("syntax error: unterminated string")
            ec = source[pos]
            if ec == '"':
                chars.append('"')
            elif ec == '\\':
                chars.append('\\')
            elif ec == 'n':
                chars.append('\n')
            else:
                raise _Internal(f"syntax error: invalid escape \\{ec}")
            pos += 1
        else:
            chars.append(c)
            pos += 1
    raise _Internal("syntax error: unterminated string")


def _parse_token(token):
    if token == '#t':
        return True
    if token == '#f':
        return False
    if token.startswith('#'):
        raise _Internal(f"syntax error: invalid token {token}")
    if INT_RE.match(token):
        return int(token)
    return Symbol(token)


def _read_form(source, pos, n):
    c = source[pos]
    if c == '(':
        return _read_list(source, pos, n)
    if c == "'":
        pos += 1
        pos = _skip_ws(source, pos, n)
        if pos >= n:
            raise _Internal("syntax error: ' not followed by datum")
        form, pos = _read_form(source, pos, n)
        return (SYM_QUOTE, (form, ())), pos
    if c == '"':
        return _read_string(source, pos, n)
    # Read a token
    start = pos
    while pos < n and source[pos] not in ' \t\n\r()";\'':
        pos += 1
    token = source[start:pos]
    if not token:
        raise _Internal("syntax error: unexpected character")
    return _parse_token(token), pos


def _read_list(source, pos, n):
    assert source[pos] == '('
    pos += 1
    elements = []
    while True:
        pos = _skip_ws(source, pos, n)
        if pos >= n:
            raise _Internal("syntax error: unbalanced (")
        c = source[pos]
        if c == ')':
            result = ()
            for e in reversed(elements):
                result = (e, result)
            return result, pos + 1
        if c == '.':
            nxt = pos + 1
            if nxt >= n or source[nxt] in ' \t\n\r()";\'':
                if not elements:
                    raise _Internal("syntax error: dot must be preceded by element")
                pos += 1
                pos = _skip_ws(source, pos, n)
                if pos >= n:
                    raise _Internal("syntax error: unbalanced (")
                tail, pos = _read_form(source, pos, n)
                pos = _skip_ws(source, pos, n)
                if pos >= n or source[pos] != ')':
                    raise _Internal("syntax error: dotted form must end with )")
                result = tail
                for e in reversed(elements):
                    result = (e, result)
                return result, pos + 1
        form, pos = _read_form(source, pos, n)
        elements.append(form)


def read_all(source):
    pos = 0
    n = len(source)
    forms = []
    while pos < n:
        pos = _skip_ws(source, pos, n)
        if pos >= n:
            break
        form, pos = _read_form(source, pos, n)
        forms.append(form)
    return forms


# ===================== LIST HELPERS =====================

def is_pair(x):
    return isinstance(x, tuple) and len(x) == 2


def is_proper_list(x):
    while x is not ():
        if not is_pair(x):
            return False
        x = x[1]
    return True


def list_to_pylist(x):
    result = []
    while x is not ():
        if not is_pair(x):
            raise _Internal("expected proper list")
        result.append(x[0])
        x = x[1]
    return result


def pylist_to_list(lst):
    result = ()
    for e in reversed(lst):
        result = (e, result)
    return result


def form_args(form):
    """Get elements after head as Python list. form must be a proper list pair."""
    return list_to_pylist(form[1])


# ===================== ENVIRONMENT =====================

class Env:
    __slots__ = ('frame', 'parent')
    def __init__(self, frame=None, parent=None):
        self.frame = frame if frame is not None else {}
        self.parent = parent


def env_lookup(env, name):
    while env is not None:
        if name in env.frame:
            val = env.frame[name]
            if val is UNBOUND_INTERNAL:
                raise _Internal(f"unbound variable: {name}")
            return val
        env = env.parent
    raise _Internal(f"unbound variable: {name}")


def env_set(env, name, value):
    while env is not None:
        if name in env.frame:
            if env.frame[name] is UNBOUND_INTERNAL:
                env.frame[name] = value
            else:
                env.frame[name] = value
            return
        env = env.parent
    raise _Internal(f"unbound variable: {name}")


# ===================== TEXT REPRESENTATION =====================

def display_value(x):
    if x is True:
        return "#t"
    if x is False:
        return "#f"
    if isinstance(x, int) and not isinstance(x, bool):
        return str(x)
    if isinstance(x, str):
        return x
    if isinstance(x, Symbol):
        return x.name
    if x is ():
        return "()"
    if isinstance(x, (Closure, Builtin)):
        return "#<procedure>"
    if x is UNSPECIFIED:
        return ""
    if is_pair(x):
        return _display_pair(x)
    raise _Internal(f"cannot display value")


def _display_pair(x):
    parts = []
    while x is not ():
        if not is_pair(x):
            break
        parts.append(display_value(x[0]))
        x = x[1]
    if x is ():
        return "(" + " ".join(parts) + ")"
    else:
        return "(" + " ".join(parts) + " . " + display_value(x) + ")"


def write_value(x):
    if x is True:
        return "#t"
    if x is False:
        return "#f"
    if isinstance(x, int) and not isinstance(x, bool):
        return str(x)
    if isinstance(x, str):
        return '"' + x.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'
    if isinstance(x, Symbol):
        return x.name
    if x is ():
        return "()"
    if isinstance(x, (Closure, Builtin)):
        return "#<procedure>"
    if x is UNSPECIFIED:
        return ""
    if is_pair(x):
        return _write_pair(x)
    raise _Internal(f"cannot write value")


def _write_pair(x):
    parts = []
    while x is not ():
        if not is_pair(x):
            break
        parts.append(write_value(x[0]))
        x = x[1]
    if x is ():
        return "(" + " ".join(parts) + ")"
    else:
        return "(" + " ".join(parts) + " . " + write_value(x) + ")"


# ===================== EQUALITY =====================

def scheme_eq(a, b):
    if isinstance(a, Symbol) and isinstance(b, Symbol):
        return a.name == b.name
    if isinstance(a, int) and not isinstance(a, bool):
        if isinstance(b, int) and not isinstance(b, bool):
            return a == b
        return False
    if a is True or a is False:
        return a is b
    if a is () and b is ():
        return True
    return a is b


def scheme_equal(a, b):
    stack = [(a, b)]
    while stack:
        a, b = stack.pop()
        if a is b:
            continue
        a_bool = a is True or a is False
        b_bool = b is True or b is False
        a_int = isinstance(a, int) and not isinstance(a, bool)
        b_int = isinstance(b, int) and not isinstance(b, bool)
        a_str = isinstance(a, str)
        b_str = isinstance(b, str)
        a_sym = isinstance(a, Symbol)
        b_sym = isinstance(b, Symbol)
        a_empty = a is ()
        b_empty = b is ()
        a_pair = is_pair(a)
        b_pair = is_pair(b)

        if a_int and b_int:
            if a != b:
                return False
            continue
        if a_bool and b_bool:
            if a is not b:
                return False
            continue
        if a_str and b_str:
            if a != b:
                return False
            continue
        if a_sym and b_sym:
            if a.name != b.name:
                return False
            continue
        if a_empty and b_empty:
            continue
        if a_pair and b_pair:
            stack.append((a[1], b[1]))
            stack.append((a[0], b[0]))
            continue
        return False
    return True


# ===================== FORMALS HANDLING =====================

def _parse_formals(formals_list):
    """Parse the formals from a lambda/define form.
    Returns: ('fixed', [symbols]) or ('dotted', [symbols], sym) or ('rest', sym)
    """
    if isinstance(formals_list, Symbol):
        return ('rest', formals_list)
    if formals_list is ():
        return ('fixed', [])
    if not is_pair(formals_list):
        raise _Internal("malformed formals")
    # Check if dotted
    if not is_proper_list(formals_list):
        # Dotted: (a b . rest)
        names = []
        x = formals_list
        while is_pair(x) and is_pair(x[1]):
            if not isinstance(x[0], Symbol):
                raise _Internal("formal must be a symbol")
            names.append(x[0])
            x = x[1]
        # x is now (rest, tail) where tail is not a pair (or is ())
        if not isinstance(x[0], Symbol):
            raise _Internal("formal must be a symbol")
        if not is_proper_list(x[1]):
            raise _Internal("malformed dotted formals")
        rest_sym = x[0]
        return ('dotted', names, rest_sym)
    else:
        # Proper list of symbols
        names = []
        for s in list_to_pylist(formals_list):
            if not isinstance(s, Symbol):
                raise _Internal("formal must be a symbol")
            names.append(s)
        return ('fixed', names)


def bind_formals(formals_info, args, env):
    kind = formals_info[0]
    if kind == 'fixed':
        names = formals_info[1]
        if len(args) != len(names):
            raise _Internal(f"wrong number of arguments: expected {len(names)}, got {len(args)}")
        frame = {n.name: a for n, a in zip(names, args)}
        return Env(frame, env)
    elif kind == 'dotted':
        names = formals_info[1]
        rest_sym = formals_info[2]
        if len(args) < len(names):
            raise _Internal(f"wrong number of arguments: expected at least {len(names)}, got {len(args)}")
        frame = {n.name: a for n, a in zip(names, args[:len(names)])}
        frame[rest_sym.name] = pylist_to_list(args[len(names):])
        return Env(frame, env)
    elif kind == 'rest':
        sym = formals_info[1]
        frame = {sym.name: pylist_to_list(args)}
        return Env(frame, env)
    raise _Internal("invalid formals")


# ===================== BUILTIN PROCEDURES =====================

def _check_int(x, ctx=""):
    if isinstance(x, bool) or not isinstance(x, int):
        raise _Internal(f"expected integer{': ' + ctx if ctx else ''}")


def _check_str(x, ctx=""):
    if not isinstance(x, str):
        raise _Internal(f"expected string{': ' + ctx if ctx else ''}")


def _check_proper_list(x, ctx=""):
    if not is_proper_list(x):
        raise _Internal(f"expected proper list{': ' + ctx if ctx else ''}")


def _check_pair(x, ctx=""):
    if not is_pair(x):
        raise _Internal(f"expected pair{': ' + ctx if ctx else ''}")


def _builtin_plus(args):
    for a in args:
        _check_int(a, "for +")
    return sum(args)


def _builtin_star(args):
    for a in args:
        _check_int(a, "for *")
    result = 1
    for a in args:
        result *= a
    return result


def _builtin_minus(args):
    if len(args) < 1:
        raise _Internal("-: expected at least 1 argument")
    for a in args:
        _check_int(a, "for -")
    if len(args) == 1:
        return -args[0]
    result = args[0]
    for a in args[1:]:
        result -= a
    return result


def _builtin_quotient(args):
    if len(args) != 2:
        raise _Internal("quotient: expected 2 arguments")
    a, b = args
    _check_int(a, "for quotient")
    _check_int(b, "for quotient")
    if b == 0:
        raise _Internal("division by zero")
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        q = -q
    return q


def _builtin_remainder(args):
    if len(args) != 2:
        raise _Internal("remainder: expected 2 arguments")
    a, b = args
    _check_int(a, "for remainder")
    _check_int(b, "for remainder")
    if b == 0:
        raise _Internal("division by zero")
    if a == 0:
        return 0
    r = abs(a) % abs(b)
    if a < 0:
        r = -r
    return r


def _builtin_modulo(args):
    if len(args) != 2:
        raise _Internal("modulo: expected 2 arguments")
    a, b = args
    _check_int(a, "for modulo")
    _check_int(b, "for modulo")
    if b == 0:
        raise _Internal("division by zero")
    # Python's % already gives sign of divisor
    return a % b


def _make_compare(op):
    def _cmp(args):
        if len(args) < 1:
            raise _Internal(f"comparison: expected at least 1 argument")
        for a in args:
            _check_int(a, "for comparison")
        for i in range(len(args) - 1):
            if not op(args[i], args[i + 1]):
                return False
        return True
    return _cmp


def _builtin_number_to_string(args):
    if len(args) not in (1, 2):
        raise _Internal("number->string: expected 1 or 2 arguments")
    n = args[0]
    _check_int(n, "for number->string")
    if len(args) == 1:
        radix = 10
    else:
        radix = args[1]
        _check_int(radix, "for number->string radix")
        if radix not in (2, 8, 10, 16):
            raise _Internal("number->string: invalid radix")
    if radix == 10:
        return str(n)
    neg = n < 0
    an = abs(n)
    digits = "0123456789abcdef"
    if an == 0:
        s = "0"
    else:
        s = ""
        while an > 0:
            s = digits[an % radix] + s
            an //= radix
    if neg:
        s = "-" + s
    return s


def _builtin_cons(args):
    if len(args) != 2:
        raise _Internal("cons: expected 2 arguments")
    return (args[0], args[1])


def _builtin_car(args):
    if len(args) != 1:
        raise _Internal("car: expected 1 argument")
    _check_pair(args[0], "for car")
    return args[0][0]


def _builtin_cdr(args):
    if len(args) != 1:
        raise _Internal("cdr: expected 1 argument")
    _check_pair(args[0], "for cdr")
    return args[0][1]


def _builtin_list(args):
    return pylist_to_list(args)


def _builtin_null_p(args):
    if len(args) != 1:
        raise _Internal("null?: expected 1 argument")
    return args[0] is ()


def _builtin_pair_p(args):
    if len(args) != 1:
        raise _Internal("pair?: expected 1 argument")
    return is_pair(args[0])


def _builtin_list_p(args):
    if len(args) != 1:
        raise _Internal("list?: expected 1 argument")
    return is_proper_list(args[0])


def _builtin_length(args):
    if len(args) != 1:
        raise _Internal("length: expected 1 argument")
    l = args[0]
    n = 0
    while l is not ():
        if not is_pair(l):
            raise _Internal("length: not a proper list")
        l = l[1]
        n += 1
    return n


def _builtin_append(args):
    if len(args) == 0:
        return ()
    result = ()
    for l in args[:-1]:
        _check_proper_list(l, "for append")
        # Prepend l to result
        # Actually, append builds from left to right
        # Let me collect all elements
    # Better approach:
    elements = []
    for l in args[:-1]:
        _check_proper_list(l, "for append")
        x = l
        while x is not ():
            elements.append(x[0])
            x = x[1]
    last = args[-1]
    result = last
    for e in reversed(elements):
        result = (e, result)
    return result


def _builtin_reverse(args):
    if len(args) != 1:
        raise _Internal("reverse: expected 1 argument")
    l = args[0]
    _check_proper_list(l, "for reverse")
    result = ()
    while l is not ():
        result = (l[0], result)
        l = l[1]
    return result


def _builtin_apply(args):
    if len(args) < 2:
        raise _Internal("apply: expected at least 2 arguments")
    proc = args[0]
    extra = args[1:-1]
    lst = args[-1]
    _check_proper_list(lst, "for apply")
    all_args = extra + list_to_pylist(lst)
    if isinstance(proc, Closure):
        return _call_closure_tail(proc, all_args)
    elif isinstance(proc, Builtin):
        return proc.func(all_args)
    else:
        raise _Internal("apply: first argument is not a procedure")


def _builtin_eq(args):
    if len(args) != 2:
        raise _Internal("eq?: expected 2 arguments")
    return scheme_eq(args[0], args[1])


def _builtin_equal(args):
    if len(args) != 2:
        raise _Internal("equal?: expected 2 arguments")
    return scheme_equal(args[0], args[1])


def _builtin_not(args):
    if len(args) != 1:
        raise _Internal("not: expected 1 argument")
    return args[0] is False


def _builtin_number_p(args):
    if len(args) != 1:
        raise _Internal("number?: expected 1 argument")
    return isinstance(args[0], int) and not isinstance(args[0], bool)


def _builtin_symbol_p(args):
    if len(args) != 1:
        raise _Internal("symbol?: expected 1 argument")
    return isinstance(args[0], Symbol)


def _builtin_string_p(args):
    if len(args) != 1:
        raise _Internal("string?: expected 1 argument")
    return isinstance(args[0], str)


def _builtin_procedure_p(args):
    if len(args) != 1:
        raise _Internal("procedure?: expected 1 argument")
    return isinstance(args[0], (Closure, Builtin))


def _builtin_string_append(args):
    for a in args:
        _check_str(a, "for string-append")
    return ''.join(args)


def _builtin_display(args):
    if len(args) != 1:
        raise _Internal("display: expected 1 argument")
    return display_value(args[0])


def _builtin_newline(args):
    if len(args) != 0:
        raise _Internal("newline: expected 0 arguments")
    return "\n"


def _builtin_error(args):
    if len(args) < 1:
        raise _Internal("error: expected at least 1 argument")
    msg = args[0]
    if not isinstance(msg, str):
        raise _Internal("error: first argument must be a string")
    full = msg
    for irritant in args[1:]:
        full += " " + write_value(irritant)
    raise _Internal(full)


# ===================== GLOBAL ENVIRONMENT =====================

def make_global_env():
    frame = {}
    frame['+'] = Builtin('+', _builtin_plus)
    frame['*'] = Builtin('*', _builtin_star)
    frame['-'] = Builtin('-', _builtin_minus)
    frame['quotient'] = Builtin('quotient', _builtin_quotient)
    frame['remainder'] = Builtin('remainder', _builtin_remainder)
    frame['modulo'] = Builtin('modulo', _builtin_modulo)
    frame['='] = Builtin('=', _make_compare(lambda a, b: a == b))
    frame['<'] = Builtin('<', _make_compare(lambda a, b: a < b))
    frame['>'] = Builtin('>', _make_compare(lambda a, b: a > b))
    frame['<='] = Builtin('<=', _make_compare(lambda a, b: a <= b))
    frame['>='] = Builtin('>=', _make_compare(lambda a, b: a >= b))
    frame['number->string'] = Builtin('number->string', _builtin_number_to_string)
    frame['cons'] = Builtin('cons', _builtin_cons)
    frame['car'] = Builtin('car', _builtin_car)
    frame['cdr'] = Builtin('cdr', _builtin_cdr)
    frame['list'] = Builtin('list', _builtin_list)
    frame['null?'] = Builtin('null?', _builtin_null_p)
    frame['pair?'] = Builtin('pair?', _builtin_pair_p)
    frame['list?'] = Builtin('list?', _builtin_list_p)
    frame['length'] = Builtin('length', _builtin_length)
    frame['append'] = Builtin('append', _builtin_append)
    frame['reverse'] = Builtin('reverse', _builtin_reverse)
    frame['apply'] = Builtin('apply', _builtin_apply)
    frame['eq?'] = Builtin('eq?', _builtin_eq)
    frame['equal?'] = Builtin('equal?', _builtin_equal)
    frame['not'] = Builtin('not', _builtin_not)
    frame['number?'] = Builtin('number?', _builtin_number_p)
    frame['symbol?'] = Builtin('symbol?', _builtin_symbol_p)
    frame['string?'] = Builtin('string?', _builtin_string_p)
    frame['procedure?'] = Builtin('procedure?', _builtin_procedure_p)
    frame['string-append'] = Builtin('string-append', _builtin_string_append)
    frame['display'] = Builtin('display', _builtin_display)
    frame['newline'] = Builtin('newline', _builtin_newline)
    frame['error'] = Builtin('error', _builtin_error)
    return Env(frame, None)


# ===================== EVALUATOR =====================

def _call_closure_tail(closure, args):
    """Call a closure. The body's last form is in tail position."""
    env = bind_formals(closure.formals, args, closure.env)
    return _eval_body(closure.body, env)


def _eval_body(body, env):
    """Evaluate a body (Python list of forms) with internal definitions.
    The last form is in tail position."""
    # Scan for internal defines
    internal_names = []
    for form in body:
        if is_pair(form) and is_proper_list(form) and form[0] == SYM_DEFINE:
            name = _extract_define_name(form)
            if name is not None:
                internal_names.append(name)

    if internal_names:
        frame = {n.name: UNBOUND_INTERNAL for n in internal_names}
        env = Env(frame, env)

    for i, form in enumerate(body):
        if i < len(body) - 1:
            _eval(form, env)
        else:
            _eval_tail(form, env)


def _extract_define_name(form):
    """Extract the name from a define form. Returns Symbol or None."""
    # (define name expr) or (define (name . formals) body...)
    rest = form[1]
    if not is_pair(rest):
        return None
    first = rest[0]
    if isinstance(first, Symbol):
        return first
    if is_pair(first) and is_proper_list(first):
        # (name . formals)
        return first[0]
    if is_pair(first) and not is_proper_list(first):
        # (name . formals) dotted
        return first[0]
    return None


def _eval(form, env):
    """Evaluate form in non-tail position. Returns value."""
    # Literals
    if form is True or form is False:
        return form
    if isinstance(form, int) and not isinstance(form, bool):
        return form
    if isinstance(form, str):
        return form
    if isinstance(form, Symbol):
        return env_lookup(env, form.name)
    if form is ():
        raise _Internal("invalid application: empty list")
    if not is_pair(form):
        raise _Internal(f"invalid form")
    if not is_proper_list(form):
        raise _Internal("dotted form used as application")

    head = form[0]
    args = form[1]  # rest as list of pairs

    if head == SYM_QUOTE:
        if not is_pair(args) or args[1] is not ():
            raise _Internal("malformed quote")
        return args[0]

    if head == SYM_IF:
        if not is_pair(args) or not is_pair(args[1]):
            raise _Internal("malformed if")
        test = _eval(args[0], env)
        if test is not False:
            return _eval(args[1][0], env)
        else:
            if is_pair(args[1][1]) and args[1][1][1] is not ():
                return _eval(args[1][1][0], env)
            else:
                return UNSPECIFIED

    if head == SYM_COND:
        clauses = args
        while is_pair(clauses):
            clause = clauses[0]
            if not is_pair(clause):
                raise _Internal("malformed cond clause")
            test = clause[0]
            if test == SYM_ELSE:
                exprs = clause[1]
                if exprs is ():
                    raise _Internal("malformed cond: else requires expressions")
                return _eval_cond_exprs(exprs, env)
            val = _eval(test, env)
            if val is not False:
                exprs = clause[1]
                if exprs is ():
                    return val
                return _eval_cond_exprs(exprs, env)
            clauses = clause[1]
        return UNSPECIFIED

    if head == SYM_AND:
        exprs = args
        while is_pair(exprs) and is_pair(exprs[1]):
            val = _eval(exprs[0], env)
            if val is False:
                return False
            exprs = exprs[1]
        if is_pair(exprs):
            return _eval(exprs[0], env)
        return True

    if head == SYM_OR:
        exprs = args
        while is_pair(exprs) and is_pair(exprs[1]):
            val = _eval(exprs[0], env)
            if val is not False:
                return val
            exprs = exprs[1]
        if is_pair(exprs):
            return _eval(exprs[0], env)
        return False

    if head == SYM_BEGIN:
        exprs = args
        while is_pair(exprs) and is_pair(exprs[1]):
            _eval(exprs[0], env)
            exprs = exprs[1]
        if is_pair(exprs):
            return _eval(exprs[0], env)
        return UNSPECIFIED

    if head == SYM_LET:
        return _eval_let(args, env, False)

    if head == SYM_LET_STAR:
        return _eval_let(args, env, True)

    if head == SYM_LETREC:
        return _eval_letrec(args, env)

    if head == SYM_LAMBDA:
        if not is_pair(args):
            raise _Internal("malformed lambda")
        formals = args[0]
        body = list_to_pylist(args[1])
        if not body:
            raise _Internal("lambda body must be non-empty")
        formals_info = _parse_formals(formals)
        return Closure(formals_info, body, env)

    if head == SYM_DEFINE:
        return _eval_define(form, env)

    if head == SYM_SET_BANG:
        if not is_pair(args) or not is_pair(args[1]) or args[1][1] is not ():
            raise _Internal("malformed set!")
        name = args[0]
        if not isinstance(name, Symbol):
            raise _Internal("set!: variable must be a symbol")
        val = _eval(args[1][0], env)
        env_set(env, name.name, val)
        return UNSPECIFIED

    # Procedure application (non-tail)
    op = _eval(head, env)
    arg_vals = []
    a = args
    while is_pair(a):
        arg_vals.append(_eval(a[0], env))
        a = a[1]
    return _call(op, arg_vals)


def _eval_cond_exprs(exprs, env):
    """Evaluate a sequence of expressions (as a pair list), return value of last."""
    while is_pair(exprs) and is_pair(exprs[1]):
        _eval(exprs[0], env)
        exprs = exprs[1]
    return _eval(exprs[0], env)


def _eval_let(args, env, sequential):
    """Evaluate let or let*."""
    # args = (bindings, body1, body2, ...)
    if not is_pair(args):
        raise _Internal("malformed let")
    bindings = args[0]
    body = args[1]

    # Check if named let
    if isinstance(bindings, Symbol):
        # Named let: (let name ((v init) ...) body...)
        name = bindings
        real_bindings = body[0]
        real_body = body[1]
        return _eval_named_let(name, real_bindings, real_body, env)

    # Parse bindings
    names = []
    inits = []
    b = bindings
    while b is not ():
        if not is_pair(b) or not is_pair(b[1]) or b[1][1] is not ():
            raise _Internal("malformed let binding")
        v = b[0]
        init = b[1][0]
        if not isinstance(v, Symbol):
            raise _Internal("let: variable must be a symbol")
        names.append(v)
        inits.append(init)
        b = b[1]

    body_forms = list_to_pylist(body)
    if not body_forms:
        raise _Internal("let body must be non-empty")

    if sequential:
        # let*
        for name, init in zip(names, inits):
            val = _eval(init, env)
            env = Env({name.name: val}, env)
    else:
        # let
        values = [_eval(init, env) for init in inits]
        frame = {n.name: v for n, v in zip(names, values)}
        env = Env(frame, env)

    return _eval_body(body_forms, env)


def _eval_named_let(name, bindings, body, env):
    """Evaluate named let."""
    # Parse bindings
    names = []
    inits = []
    b = bindings
    while b is not ():
        if not is_pair(b) or not is_pair(b[1]) or b[1][1] is not ():
            raise _Internal("malformed named let binding")
        v = b[0]
        init = b[1][0]
        if not isinstance(v, Symbol):
            raise _Internal("named let: variable must be a symbol")
        names.append(v)
        inits.append(init)
        b = b[1]

    body_forms = list_to_pylist(body)
    if not body_forms:
        raise _Internal("named let body must be non-empty")

    # Evaluate inits in outer scope
    values = [_eval(init, env) for init in inits]

    # Create closure
    formals_info = ('fixed', names)
    closure = Closure(formals_info, body_forms, None)  # env will be set below

    # Create env with name bound to closure (letrec-like)
    frame = {name.name: UNBOUND_INTERNAL}
    letrec_env = Env(frame, env)
    closure.env = letrec_env
    frame[name.name] = closure

    # Call the closure
    return _call_closure_tail(closure, values)


def _eval_letrec(args, env):
    """Evaluate letrec."""
    if not is_pair(args):
        raise _Internal("malformed letrec")
    bindings = args[0]
    body = args[1]

    names = []
    inits = []
    b = bindings
    while b is not ():
        if not is_pair(b) or not is_pair(b[1]) or b[1][1] is not ():
            raise _Internal("malformed letrec binding")
        v = b[0]
        init = b[1][0]
        if not isinstance(v, Symbol):
            raise _Internal("letrec: variable must be a symbol")
        names.append(v)
        inits.append(init)
        b = b[1]

    body_forms = list_to_pylist(body)
    if not body_forms:
        raise _Internal("letrec body must be non-empty")

    # Create frame with all names bound to UNBOUND_INTERNAL
    frame = {n.name: UNBOUND_INTERNAL for n in names}
    letrec_env = Env(frame, env)

    # Evaluate inits in order
    for name, init in zip(names, inits):
        val = _eval(init, letrec_env)
        frame[name.name] = val

    return _eval_body(body_forms, letrec_env)


def _eval_define(form, env):
    """Evaluate a define form (internal definition)."""
    # (define name expr) or (define (name . formals) body...)
    rest = form[1]
    if not is_pair(rest):
        raise _Internal("malformed define")

    first = rest[0]
    if isinstance(first, Symbol):
        # (define name expr)
        name = first
        if not is_pair(rest[1]) or rest[1][1] is not ():
            raise _Internal("malformed define")
        val = _eval(rest[1][0], env)
        env_set(env, name.name, val)
    else:
        # (define (name . formals) body...)
        if not is_pair(first):
            raise _Internal("malformed define")
        fname = first[0]
        if not isinstance(fname, Symbol):
            raise _Internal("define: name must be a symbol")
        formals = first[1]
        body = rest[1]
        body_forms = list_to_pylist(body)
        if not body_forms:
            raise _Internal("define body must be non-empty")
        formals_info = _parse_formals(formals)
        val = Closure(formals_info, body_forms, env)
        env_set(env, fname.name, val)
    return UNSPECIFIED


def _eval_tail(form, env):
    """Evaluate form in tail position. Returns value. Uses loop for tail calls."""
    while True:
        # Literals
        if form is True or form is False:
            return form
        if isinstance(form, int) and not isinstance(form, bool):
            return form
        if isinstance(form, str):
            return form
        if isinstance(form, Symbol):
            return env_lookup(env, form.name)
        if form is ():
            raise _Internal("invalid application: empty list")
        if not is_pair(form):
            raise _Internal(f"invalid form")
        if not is_proper_list(form):
            raise _Internal("dotted form used as application")

        head = form[0]
        args = form[1]

        if head == SYM_QUOTE:
            if not is_pair(args) or args[1] is not ():
                raise _Internal("malformed quote")
            return args[0]

        if head == SYM_IF:
            if not is_pair(args) or not is_pair(args[1]):
                raise _Internal("malformed if")
            test = _eval(args[0], env)
            if test is not False:
                form = args[1][0]
            else:
                if is_pair(args[1][1]) and args[1][1][1] is not ():
                    form = args[1][1][0]
                else:
                    return UNSPECIFIED
            continue

        if head == SYM_COND:
            clauses = args
            found = False
            while is_pair(clauses):
                clause = clauses[0]
                if not is_pair(clause):
                    raise _Internal("malformed cond clause")
                test = clause[0]
                if test == SYM_ELSE:
                    exprs = clause[1]
                    if exprs is ():
                        raise _Internal("malformed cond: else requires expressions")
                    # Evaluate all but last
                    e = exprs
                    while is_pair(e) and is_pair(e[1]):
                        _eval(e[0], env)
                        e = e[1]
                    form = e[0]
                    found = True
                    break
                val = _eval(test, env)
                if val is not False:
                    exprs = clause[1]
                    if exprs is ():
                        return val
                    e = exprs
                    while is_pair(e) and is_pair(e[1]):
                        _eval(e[0], env)
                        e = e[1]
                    form = e[0]
                    found = True
                    break
                clauses = clause[1]
            if not found:
                return UNSPECIFIED
            continue

        if head == SYM_AND:
            exprs = args
            while is_pair(exprs) and is_pair(exprs[1]):
                val = _eval(exprs[0], env)
                if val is False:
                    return False
                exprs = exprs[1]
            if is_pair(exprs):
                form = exprs[0]
            else:
                return True
            continue

        if head == SYM_OR:
            exprs = args
            while is_pair(exprs) and is_pair(exprs[1]):
                val = _eval(exprs[0], env)
                if val is not False:
                    return val
                exprs = exprs[1]
            if is_pair(exprs):
                form = exprs[0]
            else:
                return False
            continue

        if head == SYM_BEGIN:
            exprs = args
            while is_pair(exprs) and is_pair(exprs[1]):
                _eval(exprs[0], env)
                exprs = exprs[1]
            if is_pair(exprs):
                form = exprs[0]
            else:
                return UNSPECIFIED
            continue

        if head == SYM_LET:
            if not is_pair(args):
                raise _Internal("malformed let")
            bindings = args[0]
            body = args[1]
            if isinstance(bindings, Symbol):
                name = bindings
                real_bindings = body[0]
                real_body = body[1]
                env = _setup_named_let(name, real_bindings, real_body, env)
                body_forms = list_to_pylist(real_body)
                if not body_forms:
                    raise _Internal("named let body must be non-empty")
                env2, body_forms2 = _handle_internal_defs(body_forms, env)
                for e in body_forms2[:-1]:
                    _eval(e, env2)
                form = body_forms2[-1]
                env = env2
                continue
            # Regular let
            names = []
            inits = []
            b = bindings
            while b is not ():
                if not is_pair(b) or not is_pair(b[1]) or b[1][1] is not ():
                    raise _Internal("malformed let binding")
                v = b[0]
                init = b[1][0]
                if not isinstance(v, Symbol):
                    raise _Internal("let: variable must be a symbol")
                names.append(v)
                inits.append(init)
                b = b[1]
            values = [_eval(init, env) for init in inits]
            frame = {n.name: v for n, v in zip(names, values)}
            env = Env(frame, env)
            body_forms = list_to_pylist(body)
            if not body_forms:
                raise _Internal("let body must be non-empty")
            env, body_forms = _handle_internal_defs(body_forms, env)
            for e in body_forms[:-1]:
                _eval(e, env)
            form = body_forms[-1]
            continue

        if head == SYM_LET_STAR:
            if not is_pair(args):
                raise _Internal("malformed let*")
            bindings = args[0]
            body = args[1]
            names = []
            inits = []
            b = bindings
            while b is not ():
                if not is_pair(b) or not is_pair(b[1]) or b[1][1] is not ():
                    raise _Internal("malformed let* binding")
                v = b[0]
                init = b[1][0]
                if not isinstance(v, Symbol):
                    raise _Internal("let*: variable must be a symbol")
                names.append(v)
                inits.append(init)
                b = b[1]
            for name, init in zip(names, inits):
                val = _eval(init, env)
                env = Env({name.name: val}, env)
            body_forms = list_to_pylist(body)
            if not body_forms:
                raise _Internal("let* body must be non-empty")
            env, body_forms = _handle_internal_defs(body_forms, env)
            for e in body_forms[:-1]:
                _eval(e, env)
            form = body_forms[-1]
            continue

        if head == SYM_LETREC:
            if not is_pair(args):
                raise _Internal("malformed letrec")
            bindings = args[0]
            body = args[1]
            names = []
            inits = []
            b = bindings
            while b is not ():
                if not is_pair(b) or not is_pair(b[1]) or b[1][1] is not ():
                    raise _Internal("malformed letrec binding")
                v = b[0]
                init = b[1][0]
                if not isinstance(v, Symbol):
                    raise _Internal("letrec: variable must be a symbol")
                names.append(v)
                inits.append(init)
                b = b[1]
            frame = {n.name: UNBOUND_INTERNAL for n in names}
            letrec_env = Env(frame, env)
            for name, init in zip(names, inits):
                val = _eval(init, letrec_env)
                frame[name.name] = val
            env = letrec_env
            body_forms = list_to_pylist(body)
            if not body_forms:
                raise _Internal("letrec body must be non-empty")
            env, body_forms = _handle_internal_defs(body_forms, env)
            for e in body_forms[:-1]:
                _eval(e, env)
            form = body_forms[-1]
            continue

        if head == SYM_LAMBDA:
            if not is_pair(args):
                raise _Internal("malformed lambda")
            formals = args[0]
            body = list_to_pylist(args[1])
            if not body:
                raise _Internal("lambda body must be non-empty")
            formals_info = _parse_formals(formals)
            return Closure(formals_info, body, env)

        if head == SYM_DEFINE:
            _eval_define(form, env)
            return UNSPECIFIED

        if head == SYM_SET_BANG:
            if not is_pair(args) or not is_pair(args[1]) or args[1][1] is not ():
                raise _Internal("malformed set!")
            name = args[0]
            if not isinstance(name, Symbol):
                raise _Internal("set!: variable must be a symbol")
            val = _eval(args[1][0], env)
            env_set(env, name.name, val)
            return UNSPECIFIED

        # Procedure application in tail position
        op = _eval(head, env)
        arg_vals = []
        a = args
        while is_pair(a):
            arg_vals.append(_eval(a[0], env))
            a = a[1]

        # Check for apply in tail position
        if isinstance(op, Builtin) and op.name == 'apply':
            if len(arg_vals) < 2:
                raise _Internal("apply: expected at least 2 arguments")
            actual_proc = arg_vals[0]
            actual_args = arg_vals[1:-1] + list_to_pylist(arg_vals[-1])
            if isinstance(actual_proc, Closure):
                env = bind_formals(actual_proc.formals, actual_args, actual_proc.env)
                body_forms = actual_proc.body
                env, body_forms = _handle_internal_defs(body_forms, env)
                for e in body_forms[:-1]:
                    _eval(e, env)
                form = body_forms[-1]
                continue
            elif isinstance(actual_proc, Builtin):
                return actual_proc.func(actual_args)
            else:
                raise _Internal("apply: first argument is not a procedure")

        if isinstance(op, Closure):
            env = bind_formals(op.formals, arg_vals, op.env)
            body_forms = op.body
            env, body_forms = _handle_internal_defs(body_forms, env)
            for e in body_forms[:-1]:
                _eval(e, env)
            form = body_forms[-1]
            continue
        elif isinstance(op, Builtin):
            return op.func(arg_vals)
        else:
            raise _Internal("attempt to apply non-procedure")


def _handle_internal_defs(body_forms, env):
    """Scan body for internal defines, set up frame, return (env, body_forms)."""
    internal_names = []
    for form in body_forms:
        if is_pair(form) and is_proper_list(form) and form[0] == SYM_DEFINE:
            name = _extract_define_name(form)
            if name is not None:
                internal_names.append(name)
    if internal_names:
        frame = {n.name: UNBOUND_INTERNAL for n in internal_names}
        env = Env(frame, env)
    return env, body_forms


def _setup_named_let(name, bindings, body, env):
    """Set up named let for tail position. Returns env with name bound."""
    names = []
    inits = []
    b = bindings
    while b is not ():
        if not is_pair(b) or not is_pair(b[1]) or b[1][1] is not ():
            raise _Internal("malformed named let binding")
        v = b[0]
        init = b[1][0]
        if not isinstance(v, Symbol):
            raise _Internal("named let: variable must be a symbol")
        names.append(v)
        inits.append(init)
        b = b[1]

    values = [_eval(init, env) for init in inits]
    body_forms = list_to_pylist(body)
    if not body_forms:
        raise _Internal("named let body must be non-empty")

    formals_info = ('fixed', names)
    closure = Closure(formals_info, body_forms, None)

    frame = {name.name: UNBOUND_INTERNAL}
    letrec_env = Env(frame, env)
    closure.env = letrec_env
    frame[name.name] = closure

    # Call the closure: bind formals to values
    new_env = bind_formals(formals_info, values, letrec_env)
    return new_env


def _call(op, args):
    """Call a procedure (non-tail)."""
    if isinstance(op, Closure):
        return _call_closure_tail(op, args)
    elif isinstance(op, Builtin):
        return op.func(args)
    else:
        raise _Internal("attempt to apply non-procedure")


# ===================== TOP-LEVEL EVALUATION =====================

def _eval_top(form, env, output):
    """Evaluate a top-level form."""
    if is_pair(form) and is_proper_list(form):
        head = form[0]
        if head == SYM_DEFINE:
            _eval_top_define(form, env)
            return
        if head == SYM_BEGIN:
            args = form[1]
            while is_pair(args):
                _eval_top(args[0], env, output)
                args = args[1]
            return
    # Regular evaluation
    val = _eval(form, env)
    # Top-level value is discarded
    # But we need to capture display/newline output
    # Actually, display and newline are builtins that return strings.
    # We need a different approach for output.


# Actually, I need to rethink the output mechanism.
# display and newline should append to the output buffer.
# Let me use a mutable output list that's passed around or use a global.

# Let me use a simpler approach: the builtins for display/newline
# will raise a special signal, or I'll use a closure-based output.

# Actually, the cleanest way: make display and newline append to a shared
# output list. Since run() creates a fresh environment each time, I can
# store the output list in the global env or pass it via closure.

# Let me use a different approach: display and newline are builtins that
# return their string, and I intercept them at the top level.
# No, that won't work because they can be called from within expressions.

# Best approach: use a mutable container for output, stored in the global env
# as a special key, or just use a module-level variable that run() sets.

# Let me use a simple approach: a list that the builtins append to.

_output = []

def _builtin_display2(args):
    if len(args) != 1:
        raise _Internal("display: expected 1 argument")
    _output.append(display_value(args[0]))
    return UNSPECIFIED

def _builtin_newline2(args):
    if len(args) != 0:
        raise _Internal("newline: expected 0 arguments")
    _output.append("\n")
    return UNSPECIFIED


def make_global_env2():
    frame = {}
    frame['+'] = Builtin('+', _builtin_plus)
    frame['*'] = Builtin('*', _builtin_star)
    frame['-'] = Builtin('-', _builtin_minus)
    frame['quotient'] = Builtin('quotient', _builtin_quotient)
    frame['remainder'] = Builtin('remainder', _builtin_remainder)
    frame['modulo'] = Builtin('modulo', _builtin_modulo)
    frame['='] = Builtin('=', _make_compare(lambda a, b: a == b))
    frame['<'] = Builtin('<', _make_compare(lambda a, b: a < b))
    frame['>'] = Builtin('>', _make_compare(lambda a, b: a > b))
    frame['<='] = Builtin('<=', _make_compare(lambda a, b: a <= b))
    frame['>='] = Builtin('>=', _make_compare(lambda a, b: a >= b))
    frame['number->string'] = Builtin('number->string', _builtin_number_to_string)
    frame['cons'] = Builtin('cons', _builtin_cons)
    frame['car'] = Builtin('car', _builtin_car)
    frame['cdr'] = Builtin('cdr', _builtin_cdr)
    frame['list'] = Builtin('list', _builtin_list)
    frame['null?'] = Builtin('null?', _builtin_null_p)
    frame['pair?'] = Builtin('pair?', _builtin_pair_p)
    frame['list?'] = Builtin('list?', _builtin_list_p)
    frame['length'] = Builtin('length', _builtin_length)
    frame['append'] = Builtin('append', _builtin_append)
    frame['reverse'] = Builtin('reverse', _builtin_reverse)
    frame['apply'] = Builtin('apply', _builtin_apply)
    frame['eq?'] = Builtin('eq?', _builtin_eq)
    frame['equal?'] = Builtin('equal?', _builtin_equal)
    frame['not'] = Builtin('not', _builtin_not)
    frame['number?'] = Builtin('number?', _builtin_number_p)
    frame['symbol?'] = Builtin('symbol?', _builtin_symbol_p)
    frame['string?'] = Builtin('string?', _builtin_string_p)
    frame['procedure?'] = Builtin('procedure?', _builtin_procedure_p)
    frame['string-append'] = Builtin('string-append', _builtin_string_append)
    frame['display'] = Builtin('display', _builtin_display2)
    frame['newline'] = Builtin('newline', _builtin_newline2)
    frame['error'] = Builtin('error', _builtin_error)
    return Env(frame, None)


def _eval_top_define(form, env):
    """Evaluate a top-level define."""
    rest = form[1]
    if not is_pair(rest):
        raise _Internal("malformed define")
    first = rest[0]
    if isinstance(first, Symbol):
        name = first
        if not is_pair(rest[1]) or rest[1][1] is not ():
            raise _Internal("malformed define")
        val = _eval(rest[1][0], env)
        env.frame[name.name] = val
    else:
        if not is_pair(first):
            raise _Internal("malformed define")
        fname = first[0]
        if not isinstance(fname, Symbol):
            raise _Internal("define: name must be a symbol")
        formals = first[1]
        body = rest[1]
        body_forms = list_to_pylist(body)
        if not body_forms:
            raise _Internal("define body must be non-empty")
        formals_info = _parse_formals(formals)
        val = Closure(formals_info, body_forms, env)
        env.frame[fname.name] = val


def _eval_top(form, env):
    """Evaluate a top-level form."""
    if is_pair(form) and is_proper_list(form):
        head = form[0]
        if head == SYM_DEFINE:
            _eval_top_define(form, env)
            return
        if head == SYM_BEGIN:
            args = form[1]
            while is_pair(args):
                _eval_top(args[0], env)
                args = args[1]
            return
    _eval(form, env)


# ===================== MAIN ENTRY POINT =====================

def run(source):
    global _output
    _output = []
    try:
        forms = read_all(source)
        env = make_global_env2()
        for form in forms:
            _eval_top(form, env)
        return ''.join(_output)
    except _Internal as e:
        raise SchemeError(str(e), ''.join(_output))
    except RecursionError:
        raise SchemeError("stack overflow", ''.join(_output))
    except Exception as e:
        raise SchemeError(str(e), ''.join(_output))