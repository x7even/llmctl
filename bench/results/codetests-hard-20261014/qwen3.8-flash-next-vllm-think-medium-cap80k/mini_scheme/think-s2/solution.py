import sys
import threading

sys.setrecursionlimit(500000)
try:
    sys.set_int_max_str_digits(0)
except (AttributeError, ValueError):
    pass

# ==================== Data Types ====================

class Symbol:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name
    def __repr__(self):
        return self.name
    def __eq__(self, other):
        return isinstance(other, Symbol) and self.name == other.name
    def __hash__(self):
        return hash(('Sym', self.name))

class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr

class _NilType:
    def __repr__(self):
        return '()'
    def __bool__(self):
        return True
NIL = _NilType()

class _UnspecifiedType:
    def __repr__(self):
        return '#<unspecified>'
UNSPECIFIED = _UnspecifiedType()

UNINITIALIZED = object()

class Env:
    __slots__ = ('vars', 'parent')
    def __init__(self, parent=None):
        self.vars = {}
        self.parent = parent

class Builtin:
    __slots__ = ('name', 'func', 'min_args', 'max_args')
    def __init__(self, name, func, min_args=0, max_args=None):
        self.name = name
        self.func = func
        self.min_args = min_args
        self.max_args = max_args

class Closure:
    __slots__ = ('params', 'rest', 'body', 'env')
    def __init__(self, params, rest, body, env):
        self.params = params
        self.rest = rest
        self.body = body
        self.env = env

class SchemeError(Exception):
    def __init__(self, message, output=''):
        super().__init__(message)
        self.output = output

# ==================== Reader ====================

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
            s = []
            while i < n and source[i] != '"':
                if source[i] == '\\':
                    i += 1
                    if i >= n:
                        raise SchemeError("unterminated string escape")
                    nc = source[i]
                    if nc == '"':
                        s.append('"')
                    elif nc == '\\':
                        s.append('\\')
                    elif nc == 'n':
                        s.append('\n')
                    else:
                        raise SchemeError("invalid escape: \\" + nc)
                    i += 1
                else:
                    s.append(source[i])
                    i += 1
            if i >= n:
                raise SchemeError("unterminated string")
            i += 1
            tokens.append(('string', ''.join(s)))
        else:
            start = i
            while i < n and source[i] not in ' \t\n\r()";\'':
                i += 1
            tokens.append(('atom', source[start:i]))
    return tokens

def _is_integer_token(tok):
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

def _parse_atom(tok):
    if tok == '#t':
        return True
    if tok == '#f':
        return False
    if tok.startswith('#'):
        raise SchemeError("invalid syntax: " + tok)
    if _is_integer_token(tok):
        return int(tok)
    return Symbol(tok)

def _read_all(source):
    tokens = _tokenize(source)
    forms = []
    pos = [0]
    while pos[0] < len(tokens):
        if tokens[pos[0]][0] == ')':
            raise SchemeError("unexpected )")
        forms.append(_parse_form(tokens, pos))
    return forms

def _parse_form(tokens, pos):
    if pos[0] >= len(tokens):
        raise SchemeError("unexpected end of input")
    kind, val = tokens[pos[0]]
    if kind == '(':
        pos[0] += 1
        return _parse_list(tokens, pos)
    elif kind == ')':
        raise SchemeError("unexpected )")
    elif kind == "'":
        pos[0] += 1
        datum = _parse_form(tokens, pos)
        return Pair(Symbol('quote'), Pair(datum, NIL))
    elif kind == 'string':
        pos[0] += 1
        return val
    elif kind == 'atom':
        pos[0] += 1
        return _parse_atom(val)
    else:
        raise SchemeError("unexpected token")

def _parse_list(tokens, pos):
    elements = []
    has_dot = False
    dot_rest = None
    while True:
        if pos[0] >= len(tokens):
            raise SchemeError("unbalanced (")
        kind, val = tokens[pos[0]]
        if kind == ')':
            pos[0] += 1
            break
        if kind == 'atom' and val == '.':
            if has_dot:
                raise SchemeError("multiple dots in list")
            if len(elements) == 0:
                raise SchemeError("dot at start of list")
            has_dot = True
            pos[0] += 1
            if pos[0] >= len(tokens):
                raise SchemeError("nothing after dot")
            if tokens[pos[0]][0] == ')':
                raise SchemeError("nothing after dot")
            dot_rest = _parse_form(tokens, pos)
            if pos[0] >= len(tokens) or tokens[pos[0]][0] != ')':
                raise SchemeError("expected ) after dotted rest")
            pos[0] += 1
            break
        elements.append(_parse_form(tokens, pos))
    if has_dot:
        result = dot_rest
        for elem in reversed(elements):
            result = Pair(elem, result)
        return result
    else:
        result = NIL
        for elem in reversed(elements):
            result = Pair(elem, result)
        return result

# ==================== Formatting ====================

def _int_to_str(n, radix=10):
    if n == 0:
        return "0"
    negative = n < 0
    n = abs(n)
    digits = "0123456789abcdef"
    parts = []
    while n > 0:
        parts.append(digits[n % radix])
        n //= radix
    if negative:
        parts.append('-')
    return ''.join(reversed(parts))

def _write_string(s):
    parts = ['"']
    for c in s:
        if c == '"':
            parts.append('\\"')
        elif c == '\\':
            parts.append('\\\\')
        elif c == '\n':
            parts.append('\\n')
        else:
            parts.append(c)
    parts.append('"')
    return ''.join(parts)

def _format(obj, write_mode):
    if type(obj) is bool:
        return '#t' if obj else '#f'
    if type(obj) is int:
        return _int_to_str(obj)
    if isinstance(obj, str):
        return _write_string(obj) if write_mode else obj
    if isinstance(obj, Symbol):
        return obj.name
    if obj is NIL:
        return '()'
    if isinstance(obj, Pair):
        parts = ['(']
        current = obj
        first = True
        while isinstance(current, Pair):
            if not first:
                parts.append(' ')
            parts.append(_format(current.car, write_mode))
            first = False
            current = current.cdr
        if current is not NIL:
            parts.append(' . ')
            parts.append(_format(current, write_mode))
        parts.append(')')
        return ''.join(parts)
    if isinstance(obj, (Builtin, Closure)):
        return '#<procedure>'
    if obj is UNSPECIFIED:
        return ''
    return str(obj)

def format_display(obj):
    return _format(obj, False)

def format_write(obj):
    return _format(obj, True)

# ==================== Helpers ====================

def _is_true(obj):
    return obj is not False

def _is_proper_list(obj):
    while isinstance(obj, Pair):
        obj = obj.cdr
    return obj is NIL

def _to_list(pair):
    result = []
    while isinstance(pair, Pair):
        result.append(pair.car)
        pair = pair.cdr
    return result

def _make_pair_list(items):
    result = NIL
    for item in reversed(items):
        result = Pair(item, result)
    return result

def _parse_formals(formals):
    if isinstance(formals, Symbol):
        return ([], formals)
    if formals is NIL:
        return ([], None)
    if not isinstance(formals, Pair):
        raise SchemeError("invalid formals")
    params = []
    current = formals
    while isinstance(current, Pair):
        if not isinstance(current.car, Symbol):
            raise SchemeError("invalid formals: non-symbol parameter")
        params.append(current.car)
        current = current.cdr
    if current is NIL:
        return (params, None)
    elif isinstance(current, Symbol):
        return (params, current)
    else:
        raise SchemeError("invalid formals")

def _equal_p(a, b):
    stack = [(a, b)]
    while stack:
        a, b = stack.pop()
        if a is b:
            continue
        ta = type(a)
        tb = type(b)
        if ta is int and tb is int:
            if a != b:
                return False
        elif ta is bool and tb is bool:
            if a != b:
                return False
        elif isinstance(a, str) and isinstance(b, str):
            if a != b:
                return False
        elif isinstance(a, Symbol) and isinstance(b, Symbol):
            if a.name != b.name:
                return False
        elif a is NIL and b is NIL:
            continue
        elif isinstance(a, Pair) and isinstance(b, Pair):
            stack.append((a.cdr, b.cdr))
            stack.append((a.car, b.car))
        else:
            return False
    return True

def _eq_p(a, b):
    if a is b:
        return True
    if type(a) is int and type(b) is int:
        return a == b
    if isinstance(a, Symbol) and isinstance(b, Symbol):
        return a.name == b.name
    return False

# ==================== Evaluator ====================

class Interpreter:
    def __init__(self, output):
        self.output = output
        self.global_env = Env()
        self._setup_globals()

    def _setup_globals(self):
        env = self.global_env
        out = self.output

        def def_builtin(name, func, min_args=0, max_args=None):
            env.vars[name] = Builtin(name, func, min_args, max_args)

        def check_int(x):
            if type(x) is not int:
                raise SchemeError("expected integer")

        # Arithmetic
        def b_plus(args):
            r = 0
            for a in args:
                check_int(a)
                r += a
            return r

        def b_mul(args):
            r = 1
            for a in args:
                check_int(a)
                r *= a
            return r

        def b_sub(args):
            check_int(args[0])
            r = args[0]
            for a in args[1:]:
                check_int(a)
                r -= a
            return r

        def b_quotient(args):
            a, b = args
            check_int(a); check_int(b)
            if b == 0:
                raise SchemeError("division by zero")
            q = abs(a) // abs(b)
            if (a < 0) != (b < 0):
                q = -q
            return q

        def b_remainder(args):
            a, b = args
            check_int(a); check_int(b)
            if b == 0:
                raise SchemeError("division by zero")
            r = abs(a) % abs(b)
            if a < 0:
                r = -r
            return r

        def b_modulo(args):
            a, b = args
            check_int(a); check_int(b)
            if b == 0:
                raise SchemeError("division by zero")
            return a % b

        def _make_cmp(op):
            def f(args):
                for a in args:
                    check_int(a)
                for i in range(len(args) - 1):
                    if not op(args[i], args[i + 1]):
                        return False
                return True
            return f

        def b_num_to_str(args):
            n = args[0]
            check_int(n)
            radix = 10
            if len(args) == 2:
                radix = args[1]
                check_int(radix)
                if radix not in (2, 8, 10, 16):
                    raise SchemeError("invalid radix")
            return _int_to_str(n, radix)

        def b_eq(args):
            return _eq_p(args[0], args[1])

        def b_equal(args):
            return _equal_p(args[0], args[1])

        def b_not(args):
            return not _is_true(args[0])

        def b_number_p(args):
            return type(args[0]) is int

        def b_symbol_p(args):
            return isinstance(args[0], Symbol)

        def b_string_p(args):
            return isinstance(args[0], str)

        def b_procedure_p(args):
            return isinstance(args[0], (Builtin, Closure))

        def b_cons(args):
            return Pair(args[0], args[1])

        def b_car(args):
            p = args[0]
            if not isinstance(p, Pair):
                raise SchemeError("car: not a pair")
            return p.car

        def b_cdr(args):
            p = args[0]
            if not isinstance(p, Pair):
                raise SchemeError("cdr: not a pair")
            return p.cdr

        def b_list(args):
            return _make_pair_list(args)

        def b_null_p(args):
            return args[0] is NIL

        def b_pair_p(args):
            return isinstance(args[0], Pair)

        def b_list_p(args):
            return _is_proper_list(args[0])

        def b_length(args):
            lst = args[0]
            count = 0
            while isinstance(lst, Pair):
                count += 1
                lst = lst.cdr
            if lst is not NIL:
                raise SchemeError("length: not a proper list")
            return count

        def b_append(args):
            if len(args) == 0:
                return NIL
            if len(args) == 1:
                return args[0]
            for i in range(len(args) - 1):
                if not _is_proper_list(args[i]):
                    raise SchemeError("append: not a proper list")
            last = args[-1]
            elements = []
            for i in range(len(args) - 1):
                lst = args[i]
                while isinstance(lst, Pair):
                    elements.append(lst.car)
                    lst = lst.cdr
            if not elements:
                return last
            result = NIL
            for elem in reversed(elements):
                result = Pair(elem, result)
            tail = result
            while isinstance(tail.cdr, Pair):
                tail = tail.cdr
            tail.cdr = last
            return result

        def b_reverse(args):
            lst = args[0]
            result = NIL
            while isinstance(lst, Pair):
                result = Pair(lst.car, result)
                lst = lst.cdr
            if lst is not NIL:
                raise SchemeError("reverse: not a proper list")
            return result

        def b_string_append(args):
            parts = []
            for a in args:
                if not isinstance(a, str):
                    raise SchemeError("string-append: not a string")
                parts.append(a)
            return ''.join(parts)

        def b_display(args):
            out.append(format_display(args[0]))
            return UNSPECIFIED

        def b_newline(args):
            out.append('\n')
            return UNSPECIFIED

        def b_error(args):
            if len(args) < 1:
                raise SchemeError("error: too few arguments")
            msg = args[0]
            if not isinstance(msg, str):
                raise SchemeError("error: first argument must be a string")
            parts = [msg]
            for irritant in args[1:]:
                parts.append(' ')
                parts.append(format_write(irritant))
            raise SchemeError(''.join(parts))

        def b_apply(args):
            # Handled as special form in evaluator; this is a fallback
            raise SchemeError("apply: should be handled as special form")

        def b_void(args):
            return UNSPECIFIED

        def b_values(args):
            return args[0] if args else UNSPECIFIED

        def b_boolean_p(args):
            return type(args[0]) is bool

        def b_zero_p(args):
            check_int(args[0])
            return args[0] == 0

        def b_abs(args):
            check_int(args[0])
            return abs(args[0])

        def b_min(args):
            for a in args:
                check_int(a)
            return min(args)

        def b_max(args):
            for a in args:
                check_int(a)
            return max(args)

        def b_exact_p(args):
            return type(args[0]) is int

        def b_assq(args):
            key, lst = args
            while isinstance(lst, Pair):
                if _eq_p(lst.car.car, key):
                    return lst.car
                lst = lst.cdr
            return False

        def b_assoc(args):
            key, lst = args
            while isinstance(lst, Pair):
                if _equal_p(lst.car.car, key):
                    return lst.car
                lst = lst.cdr
            return False

        def b_memq(args):
            key, lst = args
            while isinstance(lst, Pair):
                if _eq_p(lst.car, key):
                    return lst
                lst = lst.cdr
            return False

        def b_member(args):
            key, lst = args
            while isinstance(lst, Pair):
                if _equal_p(lst.car, key):
                    return lst
                lst = lst.cdr
            return False

        def b_list_to_string(args):
            lst = args[0]
            parts = []
            while isinstance(lst, Pair):
                if not isinstance(lst.car, str) or len(lst.car) != 1:
                    raise SchemeError("list->string: not a list of chars")
                parts.append(lst.car)
                lst = lst.cdr
            return ''.join(parts)

        def b_string_to_list(args):
            s = args[0]
            if not isinstance(s, str):
                raise SchemeError("string->list: not a string")
            return _make_pair_list(list(s))

        def b_char_to_integer(args):
            c = args[0]
            if not isinstance(c, str) or len(c) != 1:
                raise SchemeError("char->integer: not a char")
            return ord(c)

        def b_integer_to_char(args):
            n = args[0]
            check_int(n)
            return chr(n)

        def b_string_length(args):
            s = args[0]
            if not isinstance(s, str):
                raise SchemeError("string-length: not a string")
            return len(s)

        def b_string_ref(args):
            s, i = args
            if not isinstance(s, str):
                raise SchemeError("string-ref: not a string")
            check_int(i)
            if i < 0 or i >= len(s):
                raise SchemeError("string-ref: index out of range")
            return s[i]

        def b_substring(args):
            s = args[0]
            if not isinstance(s, str):
                raise SchemeError("substring: not a string")
            start = args[1]
            check_int(start)
            if len(args) == 3:
                end = args[2]
                check_int(end)
            else:
                end = len(s)
            return s[start:end]

        def b_string_p2(args):
            return isinstance(args[0], str) and isinstance(args[1], str) and args[0] == args[1]

        def b_symbol_to_string(args):
            s = args[0]
            if not isinstance(s, Symbol):
                raise SchemeError("symbol->string: not a symbol")
            return s.name

        def b_string_to_symbol(args):
            s = args[0]
            if not isinstance(s, str):
                raise SchemeError("string->symbol: not a string")
            return Symbol(s)

        def b_string_ci_eq(args):
            a, b = args
            if not isinstance(a, str) or not isinstance(b, str):
                raise SchemeError("string-ci=?: not strings")
            return a.lower() == b.lower()

        def b_gcd(args):
            import math
            r = 0
            for a in args:
                check_int(a)
                r = math.gcd(r, abs(a))
            return r

        def b_lcm(args):
            import math
            r = 1
            for a in args:
                check_int(a)
                if a == 0:
                    return 0
                r = abs(r * a) // math.gcd(r, abs(a))
            return r

        def b_expt(args):
            a, b = args
            check_int(a); check_int(b)
            if b < 0:
                raise SchemeError("expt: negative exponent")
            return a ** b

        def b_sqrt(args):
            a = args[0]
            check_int(a)
            if a < 0:
                raise SchemeError("sqrt: negative argument")
            r = int(a ** 0.5)
            while r * r > a:
                r -= 1
            while (r + 1) * (r + 1) <= a:
                r += 1
            if r * r == a:
                return r
            raise SchemeError("sqrt: not a perfect square")

        def b_even_p(args):
            check_int(args[0])
            return args[0] % 2 == 0

        def b_odd_p(args):
            check_int(args[0])
            return args[0] % 2 != 0

        def b_positive_p(args):
            check_int(args[0])
            return args[0] > 0

        def b_negative_p(args):
            check_int(args[0])
            return args[0] < 0

        def b_sort(args):
            # Not required but harmless
            raise SchemeError("sort: not supported")

        # Register builtins
        def_builtin('+', b_plus, 0)
        def_builtin('*', b_mul, 0)
        def_builtin('-', b_sub, 1)
        def_builtin('quotient', b_quotient, 2, 2)
        def_builtin('remainder', b_remainder, 2, 2)
        def_builtin('modulo', b_modulo, 2, 2)
        def_builtin('=', _make_cmp(lambda a, b: a == b), 1)
        def_builtin('<', _make_cmp(lambda a, b: a < b), 1)
        def_builtin('>', _make_cmp(lambda a, b: a > b), 1)
        def_builtin('<=', _make_cmp(lambda a, b: a <= b), 1)
        def_builtin('>=', _make_cmp(lambda a, b: a >= b), 1)
        def_builtin('number->string', b_num_to_str, 1, 2)
        def_builtin('eq?', b_eq, 2, 2)
        def_builtin('equal?', b_equal, 2, 2)
        def_builtin('not', b_not, 1, 1)
        def_builtin('number?', b_number_p, 1, 1)
        def_builtin('symbol?', b_symbol_p, 1, 1)
        def_builtin('string?', b_string_p, 1, 1)
        def_builtin('procedure?', b_procedure_p, 1, 1)
        def_builtin('cons', b_cons, 2, 2)
        def_builtin('car', b_car, 1, 1)
        def_builtin('cdr', b_cdr, 1, 1)
        def_builtin('list', b_list, 0)
        def_builtin('null?', b_null_p, 1, 1)
        def_builtin('pair?', b_pair_p, 1, 1)
        def_builtin('list?', b_list_p, 1, 1)
        def_builtin('length', b_length, 1, 1)
        def_builtin('append', b_append, 0)
        def_builtin('reverse', b_reverse, 1, 1)
        def_builtin('string-append', b_string_append, 0)
        def_builtin('display', b_display, 1, 1)
        def_builtin('newline', b_newline, 0, 0)
        def_builtin('error', b_error, 1)
        def_builtin('void', b_void, 0, 0)
        def_builtin('boolean?', b_boolean_p, 1, 1)
        def_builtin('zero?', b_zero_p, 1, 1)
        def_builtin('abs', b_abs, 1, 1)
        def_builtin('min', b_min, 1)
        def_builtin('max', b_max, 1)
        def_builtin('exact?', b_exact_p, 1, 1)
        def_builtin('assq', b_assq, 2, 2)
        def_builtin('assoc', b_assoc, 2, 2)
        def_builtin('memq', b_memq, 2, 2)
        def_builtin('member', b_member, 2, 2)
        def_builtin('string-length', b_string_length, 1, 1)
        def_builtin('string-ref', b_string_ref, 2, 2)
        def_builtin('substring', b_substring, 2, 3)
        def_builtin('string=?', b_string_p2, 2, 2)
        def_builtin('symbol->string', b_symbol_to_string, 1, 1)
        def_builtin('string->symbol', b_string_to_symbol, 1, 1)
        def_builtin('even?', b_even_p, 1, 1)
        def_builtin('odd?', b_odd_p, 1, 1)
        def_builtin('positive?', b_positive_p, 1, 1)
        def_builtin('negative?', b_negative_p, 1, 1)
        def_builtin('expt', b_expt, 2, 2)
        def_builtin('gcd', b_gcd, 0)
        def_builtin('lcm', b_lcm, 0)

    def _lookup(self, env, sym):
        name = sym.name
        e = env
        while e is not None:
            if name in e.vars:
                val = e.vars[name]
                if val is UNINITIALIZED:
                    raise SchemeError("uninitialized variable: " + name)
                return val
            e = e.parent
        raise SchemeError("unbound variable: " + name)

    def _set_var(self, env, sym, val):
        name = sym.name
        e = env
        while e is not None:
            if name in e.vars:
                e.vars[name] = val
                return
            e = e.parent
        raise SchemeError("set!: unbound variable: " + name)

    def _is_define_form(self, form):
        return (isinstance(form, Pair) and
                isinstance(form.car, Symbol) and
                form.car.name == 'define')

    def _define_name(self, form):
        target = form.cdr.car
        if isinstance(target, Symbol):
            return target.name
        elif isinstance(target, Pair):
            if isinstance(target.car, Symbol):
                return target.car.name
        raise SchemeError("malformed define")

    def _exec_define(self, form, env):
        if form.cdr is NIL:
            raise SchemeError("malformed define")
        target = form.cdr.car
        if isinstance(target, Symbol):
            if form.cdr.cdr is NIL:
                raise SchemeError("malformed define")
            val = self.eval_expr(form.cdr.cdr.car, env)
            env.vars[target.name] = val
        elif isinstance(target, Pair):
            if not isinstance(target.car, Symbol):
                raise SchemeError("malformed define")
            name = target.car
            formals = target.cdr
            body = _to_list(form.cdr.cdr)
            if len(body) == 0:
                raise SchemeError("empty body in define")
            params, r = _parse_formals(formals)
            closure = Closure(params, r, body, env)
            env.vars[name.name] = closure
        else:
            raise SchemeError("malformed define")

    def _prepare_body(self, body, env):
        frame = Env(env)
        for form in body:
            if self._is_define_form(form):
                name = self._define_name(form)
                frame.vars[name] = UNINITIALIZED
        return frame

    def _eval_body(self, body, env):
        """Evaluate body forms. Returns (last_expr, last_env) for tail eval, or (None, val)."""
        body_env = self._prepare_body(body, env)
        for f in body[:-1]:
            if self._is_define_form(f):
                self._exec_define(f, body_env)
            else:
                self.eval_expr(f, body_env)
        last = body[-1]
        if self._is_define_form(last):
            self._exec_define(last, body_env)
            return (None, UNSPECIFIED)
        return (last, body_env)

    def _make_call_env(self, proc, args):
        call_env = Env(proc.env)
        n = len(proc.params)
        if proc.rest is None:
            if len(args) != n:
                raise SchemeError("wrong number of arguments: expected %d, got %d" % (n, len(args)))
            for i, sym in enumerate(proc.params):
                call_env.vars[sym.name] = args[i]
        else:
            if len(args) < n:
                raise SchemeError("wrong number of arguments: expected at least %d, got %d" % (n, len(args)))
            for i, sym in enumerate(proc.params):
                call_env.vars[sym.name] = args[i]
            call_env.vars[proc.rest.name] = _make_pair_list(args[n:])
        return call_env

    def _call_proc(self, proc, args):
        """Call proc with args. Returns (expr, env) for tail call, or (None, value)."""
        if isinstance(proc, Closure):
            call_env = self._make_call_env(proc, args)
            return self._eval_body(proc.body, call_env)
        elif isinstance(proc, Builtin):
            if len(args) < proc.min_args:
                raise SchemeError("too few arguments to " + proc.name)
            if proc.max_args is not None and len(args) > proc.max_args:
                raise SchemeError("too many arguments to " + proc.name)
            return (None, proc.func(args))
        else:
            raise SchemeError("not a procedure")

    def eval_expr(self, expr, env):
        while True:
            if type(expr) is int or type(expr) is bool or isinstance(expr, str):
                return expr
            if isinstance(expr, Symbol):
                return self._lookup(env, expr)
            if expr is NIL:
                raise SchemeError("cannot evaluate ()")
            if not isinstance(expr, Pair):
                raise SchemeError("cannot evaluate")

            head = expr.car
            if isinstance(head, Symbol):
                name = head.name

                if name == 'quote':
                    if expr.cdr is NIL or expr.cdr.cdr is not NIL:
                        raise SchemeError("malformed quote")
                    return expr.cdr.car

                elif name == 'if':
                    rest = expr.cdr
                    if rest is NIL:
                        raise SchemeError("malformed if")
                    test_val = self.eval_expr(rest.car, env)
                    rest = rest.cdr
                    if rest is NIL:
                        raise SchemeError("malformed if")
                    if _is_true(test_val):
                        expr = rest.car
                        continue
                    rest = rest.cdr
                    if rest is NIL:
                        return UNSPECIFIED
                    expr = rest.car
                    continue

                elif name == 'define':
                    self._exec_define(expr, env)
                    return UNSPECIFIED

                elif name == 'set!':
                    rest = expr.cdr
                    if rest is NIL or not isinstance(rest.car, Symbol) or rest.cdr is NIL:
                        raise SchemeError("malformed set!")
                    val = self.eval_expr(rest.cdr.car, env)
                    self._set_var(env, rest.car, val)
                    return UNSPECIFIED

                elif name == 'begin':
                    forms = _to_list(expr.cdr)
                    if len(forms) == 0:
                        raise SchemeError("malformed begin")
                    for f in forms[:-1]:
                        self.eval_expr(f, env)
                    expr = forms[-1]
                    continue

                elif name == 'lambda':
                    rest = expr.cdr
                    if rest is NIL:
                        raise SchemeError("malformed lambda")
                    formals = rest.car
                    body = _to_list(rest.cdr)
                    if len(body) == 0:
                        raise SchemeError("empty body in lambda")
                    params, r = _parse_formals(formals)
                    return Closure(params, r, body, env)

                elif name == 'cond':
                    clauses = _to_list(expr.cdr)
                    if len(clauses) == 0:
                        raise SchemeError("malformed cond")
                    matched = False
                    for clause in clauses:
                        if not isinstance(clause, Pair):
                            raise SchemeError("malformed cond clause")
                        test = clause.car
                        body = _to_list(clause.cdr)
                        if isinstance(test, Symbol) and test.name == 'else':
                            if len(body) == 0:
                                return UNSPECIFIED
                            for f in body[:-1]:
                                self.eval_expr(f, env)
                            expr = body[-1]
                            matched = True
                            break
                        else:
                            test_val = self.eval_expr(test, env)
                            if _is_true(test_val):
                                if len(body) == 0:
                                    return test_val
                                for f in body[:-1]:
                                    self.eval_expr(f, env)
                                expr = body[-1]
                                matched = True
                                break
                    if not matched:
                        return UNSPECIFIED
                    continue

                elif name == 'and':
                    forms = _to_list(expr.cdr)
                    if len(forms) == 0:
                        return True
                    for f in forms[:-1]:
                        val = self.eval_expr(f, env)
                        if not _is_true(val):
                            return False
                    expr = forms[-1]
                    continue

                elif name == 'or':
                    forms = _to_list(expr.cdr)
                    if len(forms) == 0:
                        return False
                    for f in forms[:-1]:
                        val = self.eval_expr(f, env)
                        if _is_true(val):
                            return val
                    expr = forms[-1]
                    continue

                elif name == 'let':
                    rest = expr.cdr
                    if rest is NIL:
                        raise SchemeError("malformed let")
                    first = rest.car
                    if isinstance(first, Symbol):
                        # Named let
                        name_sym = first
                        bindings_list = rest.cdr
                        if bindings_list is NIL:
                            raise SchemeError("malformed named let")
                        bindings = _to_list(bindings_list.car)
                        body = _to_list(bindings_list.cdr)
                        if len(body) == 0:
                            raise SchemeError("empty body in named let")
                        # Evaluate inits in outer scope
                        init_vals = []
                        params = []
                        for b in bindings:
                            if not isinstance(b, Pair) or not isinstance(b.car, Symbol):
                                raise SchemeError("malformed named let binding")
                            if b.cdr is NIL:
                                raise SchemeError("malformed named let binding")
                            params.append(b.car)
                            init_vals.append(self.eval_expr(b.cdr.car, env))
                        # Create frame with name
                        frame = Env(env)
                        frame.vars[name_sym.name] = UNINITIALIZED
                        closure = Closure(params, None, body, frame)
                        frame.vars[name_sym.name] = closure
                        # Call closure with init_vals (tail position)
                        result = self._call_proc(closure, init_vals)
                        if result[0] is None:
                            return result[1]
                        expr, env = result
                        continue
                    else:
                        # Regular let
                        bindings = _to_list(first)
                        body = _to_list(rest.cdr)
                        if len(body) == 0:
                            raise SchemeError("empty body in let")
                        values = []
                        for b in bindings:
                            if not isinstance(b, Pair) or not isinstance(b.car, Symbol):
                                raise SchemeError("malformed let binding")
                            if b.cdr is NIL:
                                raise SchemeError("malformed let binding")
                            val = self.eval_expr(b.cdr.car, env)
                            values.append((b.car, val))
                        let_env = Env(env)
                        for sym, val in values:
                            let_env.vars[sym.name] = val
                        result = self._eval_body(body, let_env)
                        if result[0] is None:
                            return result[1]
                        expr, env = result
                        continue

                elif name == 'let*':
                    rest = expr.cdr
                    if rest is NIL:
                        raise SchemeError("malformed let*")
                    bindings = _to_list(rest.car)
                    body = _to_list(rest.cdr)
                    if len(body) == 0:
                        raise SchemeError("empty body in let*")
                    cur_env = env
                    for b in bindings:
                        if not isinstance(b, Pair) or not isinstance(b.car, Symbol):
                            raise SchemeError("malformed let* binding")
                        if b.cdr is NIL:
                            raise SchemeError("malformed let* binding")
                        val = self.eval_expr(b.cdr.car, cur_env)
                        new_env = Env(cur_env)
                        new_env.vars[b.car.name] = val
                        cur_env = new_env
                    result = self._eval_body(body, cur_env)
                    if result[0] is None:
                        return result[1]
                    expr, env = result
                    continue

                elif name == 'letrec':
                    rest = expr.cdr
                    if rest is NIL:
                        raise SchemeError("malformed letrec")
                    bindings = _to_list(rest.car)
                    body = _to_list(rest.cdr)
                    if len(body) == 0:
                        raise SchemeError("empty body in letrec")
                    new_env = Env(env)
                    for b in bindings:
                        if not isinstance(b, Pair) or not isinstance(b.car, Symbol):
                            raise SchemeError("malformed letrec binding")
                        if b.cdr is NIL:
                            raise SchemeError("malformed letrec binding")
                        new_env.vars[b.car.name] = UNINITIALIZED
                    for b in bindings:
                        val = self.eval_expr(b.cdr.car, new_env)
                        new_env.vars[b.car.name] = val
                    result = self._eval_body(body, new_env)
                    if result[0] is None:
                        return result[1]
                    expr, env = result
                    continue

                elif name == 'apply':
                    arg_forms = _to_list(expr.cdr)
                    if len(arg_forms) < 2:
                        raise SchemeError("apply: too few arguments")
                    proc = self.eval_expr(arg_forms[0], env)
                    eval_args = []
                    for af in arg_forms[1:]:
                        eval_args.append(self.eval_expr(af, env))
                    lst = eval_args[-1]
                    if not _is_proper_list(lst):
                        raise SchemeError("apply: last argument is not a proper list")
                    full_args = eval_args[:-1] + _to_list(lst)
                    result = self._call_proc(proc, full_args)
                    if result[0] is None:
                        return result[1]
                    expr, env = result
                    continue

            # Application
            proc = self.eval_expr(expr.car, env)
            args = []
            cur = expr.cdr
            while cur is not NIL:
                if not isinstance(cur, Pair):
                    raise SchemeError("improper list in application")
                args.append(self.eval_expr(cur.car, env))
                cur = cur.cdr
            result = self._call_proc(proc, args)
            if result[0] is None:
                return result[1]
            expr, env = result
            continue


# ==================== Public API ====================

def run(source):
    output = []
    result = [None]
    error = [None]

    def _run():
        try:
            forms = _read_all(source)
            interp = Interpreter(output)
            for form in forms:
                interp.eval_expr(form, interp.global_env)
            result[0] = ''.join(output)
        except SchemeError as e:
            e.output = ''.join(output)
            error[0] = e
        except Exception as e:
            err = SchemeError(str(e))
            err.output = ''.join(output)
            error[0] = err

    try:
        threading.stack_size(256 * 1024 * 1024)
    except (ValueError, RuntimeError, OSError):
        pass

    t = threading.Thread(target=_run)
    t.start()
    t.join()

    if error[0] is not None:
        raise error[0]
    return result[0]
