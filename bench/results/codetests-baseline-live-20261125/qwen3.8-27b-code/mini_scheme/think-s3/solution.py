import sys
import re
import threading

try:
    sys.set_int_max_str_digits(0)
except AttributeError:
    pass


class SchemeError(Exception):
    def __init__(self, msg, output=''):
        super().__init__(msg)
        self.output = output


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


class _Sentinel:
    __slots__ = ('_name',)
    def __init__(self, name):
        self._name = name
    def __repr__(self):
        return self._name


EMPTY_LIST = _Sentinel("()")
UNSPECIFIED = _Sentinel("unspecified")
UNINITIALIZED = _Sentinel("uninitialized")


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


class Environment:
    __slots__ = ('frame', 'parent')
    def __init__(self, frame, parent=None):
        self.frame = frame
        self.parent = parent

    def lookup(self, name):
        if name in self.frame:
            val = self.frame[name]
            if val is UNINITIALIZED:
                raise SchemeError(f"uninitialized variable: {name.name}")
            return val
        if self.parent:
            return self.parent.lookup(name)
        raise SchemeError(f"unbound variable: {name.name}")

    def set(self, name, value):
        if name in self.frame:
            self.frame[name] = value
            return
        if self.parent:
            self.parent.set(name, value)
            return
        raise SchemeError(f"unbound variable: {name.name}")

    def get_global(self):
        e = self
        while e.parent:
            e = e.parent
        return e


def make_list(elems):
    result = EMPTY_LIST
    for elem in reversed(elems):
        result = Pair(elem, result)
    return result


def to_list(pair):
    result = []
    current = pair
    while isinstance(current, Pair):
        result.append(current.car)
        current = current.cdr
    if current is not EMPTY_LIST:
        raise SchemeError("not a proper list")
    return result


def is_proper_list(x):
    while isinstance(x, Pair):
        x = x.cdr
    return x is EMPTY_LIST


def display_repr(x, display_mode):
    if x is EMPTY_LIST:
        return "()"
    if type(x) is bool:
        return "#t" if x else "#f"
    if type(x) is int:
        return str(x)
    if isinstance(x, str):
        if display_mode:
            return x
        else:
            s = x.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
            return '"' + s + '"'
    if isinstance(x, Symbol):
        return x.name
    if isinstance(x, (Closure, Builtin)):
        return "#<procedure>"
    if x is UNSPECIFIED:
        return ""
    if isinstance(x, Pair):
        parts = []
        current = x
        while isinstance(current, Pair):
            parts.append(display_repr(current.car, display_mode))
            current = current.cdr
        if current is EMPTY_LIST:
            return "(" + " ".join(parts) + ")"
        else:
            if parts:
                return "(" + " ".join(parts) + " . " + display_repr(current, display_mode) + ")"
            else:
                return "(" + display_repr(x.car, display_mode) + " . " + display_repr(x.cdr, display_mode) + ")"
    return ""


# --- Tokenizer ---

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
            tokens.append('(')
            i += 1
        elif c == ')':
            tokens.append(')')
            i += 1
        elif c == "'":
            tokens.append("'")
            i += 1
        elif c == '"':
            i += 1
            buf = []
            terminated = False
            while i < n:
                if source[i] == '\\':
                    if i + 1 >= n:
                        raise SchemeError("unterminated string escape")
                    esc = source[i + 1]
                    if esc == '"':
                        buf.append('"')
                        i += 2
                    elif esc == '\\':
                        buf.append('\\')
                        i += 2
                    elif esc == 'n':
                        buf.append('\n')
                        i += 2
                    else:
                        raise SchemeError(f"invalid escape: \\{esc}")
                elif source[i] == '"':
                    i += 1
                    terminated = True
                    break
                else:
                    buf.append(source[i])
                    i += 1
            if not terminated:
                raise SchemeError("unterminated string")
            tokens.append(('string', ''.join(buf)))
        elif c == '#':
            start = i
            while i < n and source[i] not in ' \t\n\r()"\'':
                i += 1
            tok = source[start:i]
            if tok == '#t':
                tokens.append(('bool', True))
            elif tok == '#f':
                tokens.append(('bool', False))
            else:
                raise SchemeError(f"invalid token: {tok}")
        else:
            start = i
            while i < n and source[i] not in ' \t\n\r()"\'':
                i += 1
            tok = source[start:i]
            if re.fullmatch(r'[+-]?[0-9]+', tok):
                tokens.append(('int', int(tok)))
            else:
                tokens.append(('sym', tok))
    return tokens


# --- Parser ---

def parse(tokens, pos):
    if pos >= len(tokens):
        raise SchemeError("unexpected end of input")

    tok = tokens[pos]

    if tok == '(':
        pos += 1
        elements = []
        dotted = None
        while True:
            if pos >= len(tokens):
                raise SchemeError("unbalanced parenthesis")
            if tokens[pos] == ')':
                pos += 1
                break
            if tokens[pos] == '.':
                if not elements:
                    raise SchemeError("dot must be preceded by at least one element")
                pos += 1
                if pos >= len(tokens):
                    raise SchemeError("expected datum after dot")
                dotted, pos = parse(tokens, pos)
                if pos >= len(tokens) or tokens[pos] != ')':
                    raise SchemeError("expected ) after dotted list")
                pos += 1
                break
            elem, pos = parse(tokens, pos)
            elements.append(elem)

        result = EMPTY_LIST
        if dotted is not None:
            result = Pair(elements[-1], dotted)
            for elem in reversed(elements[:-1]):
                result = Pair(elem, result)
        else:
            for elem in reversed(elements):
                result = Pair(elem, result)
        return result, pos

    elif tok == ')':
        raise SchemeError("unexpected )")

    elif tok == "'":
        pos += 1
        if pos >= len(tokens):
            raise SchemeError("' not followed by a datum")
        datum, pos = parse(tokens, pos)
        quote_sym = Symbol('quote')
        return Pair(quote_sym, Pair(datum, EMPTY_LIST)), pos

    elif isinstance(tok, tuple):
        pos += 1
        kind = tok[0]
        if kind == 'int':
            return tok[1], pos
        elif kind == 'bool':
            return tok[1], pos
        elif kind == 'string':
            return tok[1], pos
        elif kind == 'sym':
            return Symbol(tok[1]), pos

    raise SchemeError(f"unexpected token")


# --- Builtins ---

def _check_ints(args):
    for a in args:
        if type(a) is not int:
            raise SchemeError("expected integer argument")


def make_global_frame(output_buf):
    frame = {}

    def _plus(args):
        _check_ints(args)
        return sum(args)

    def _times(args):
        _check_ints(args)
        r = 1
        for a in args:
            r *= a
        return r

    def _minus(args):
        _check_ints(args)
        if len(args) == 1:
            return -args[0]
        r = args[0]
        for a in args[1:]:
            r -= a
        return r

    def _quotient(args):
        if len(args) != 2:
            raise SchemeError("quotient: expected 2 arguments")
        a, b = args
        _check_ints(args)
        if b == 0:
            raise SchemeError("division by zero")
        q = abs(a) // abs(b)
        if (a < 0) != (b < 0):
            q = -q
        return q

    def _remainder(args):
        if len(args) != 2:
            raise SchemeError("remainder: expected 2 arguments")
        a, b = args
        _check_ints(args)
        if b == 0:
            raise SchemeError("division by zero")
        r = abs(a) % abs(b)
        if a < 0:
            r = -r
        return r

    def _modulo(args):
        if len(args) != 2:
            raise SchemeError("modulo: expected 2 arguments")
        a, b = args
        _check_ints(args)
        if b == 0:
            raise SchemeError("division by zero")
        r = abs(a) % abs(b)
        if b < 0:
            r = -r
        return r

    def _compare(op_name):
        def _cmp(args):
            if len(args) == 0:
                raise SchemeError(f"{op_name}: expected at least 1 argument")
            _check_ints(args)
            for i in range(len(args) - 1):
                if op_name == '=' and not (args[i] == args[i+1]):
                    return False
                if op_name == '<' and not (args[i] < args[i+1]):
                    return False
                if op_name == '>' and not (args[i] > args[i+1]):
                    return False
                if op_name == '<=' and not (args[i] <= args[i+1]):
                    return False
                if op_name == '>=' and not (args[i] >= args[i+1]):
                    return False
            return True
        return _cmp

    def _number_to_string(args):
        if len(args) not in (1, 2):
            raise SchemeError("number->string: expected 1 or 2 arguments")
        n = args[0]
        if type(n) is not int:
            raise SchemeError("number->string: expected integer")
        radix = 10
        if len(args) == 2:
            radix = args[1]
            if type(radix) is not int or radix not in (2, 8, 10, 16):
                raise SchemeError("number->string: invalid radix")
        if n == 0:
            return "0"
        negative = n < 0
        n = abs(n)
        digits = "0123456789abcdef"
        result = []
        while n > 0:
            result.append(digits[n % radix])
            n //= radix
        result.reverse()
        s = ''.join(result)
        return "-" + s if negative else s

    def _cons(args):
        if len(args) != 2:
            raise SchemeError("cons: expected 2 arguments")
        return Pair(args[0], args[1])

    def _car(args):
        if len(args) != 1:
            raise SchemeError("car: expected 1 argument")
        if not isinstance(args[0], Pair):
            raise SchemeError("car: expected a pair")
        return args[0].car

    def _cdr(args):
        if len(args) != 1:
            raise SchemeError("cdr: expected 1 argument")
        if not isinstance(args[0], Pair):
            raise SchemeError("cdr: expected a pair")
        return args[0].cdr

    def _list(args):
        return make_list(args)

    def _null_p(args):
        if len(args) != 1:
            raise SchemeError("null?: expected 1 argument")
        return args[0] is EMPTY_LIST

    def _pair_p(args):
        if len(args) != 1:
            raise SchemeError("pair?: expected 1 argument")
        return isinstance(args[0], Pair)

    def _list_p(args):
        if len(args) != 1:
            raise SchemeError("list?: expected 1 argument")
        return is_proper_list(args[0])

    def _length(args):
        if len(args) != 1:
            raise SchemeError("length: expected 1 argument")
        l = args[0]
        if not is_proper_list(l):
            raise SchemeError("length: expected a proper list")
        n = 0
        current = l
        while isinstance(current, Pair):
            n += 1
            current = current.cdr
        return n

    def _append(args):
        for a in args[:-1] if args else []:
            if not is_proper_list(a):
                raise SchemeError("append: all but last argument must be proper lists")
        if not args:
            return EMPTY_LIST
        last = args[-1]
        result = last
        for l in reversed(args[:-1]):
            if l is EMPTY_LIST:
                continue
            # Prepend elements of l to result
            # Convert l to a list, reverse, prepend
            elems = to_list(l)
            for e in reversed(elems):
                result = Pair(e, result)
        return result

    def _reverse(args):
        if len(args) != 1:
            raise SchemeError("reverse: expected 1 argument")
        l = args[0]
        if not is_proper_list(l):
            raise SchemeError("reverse: expected a proper list")
        result = EMPTY_LIST
        current = l
        while isinstance(current, Pair):
            result = Pair(current.car, result)
            current = current.cdr
        return result

    def _apply(args):
        if len(args) < 2:
            raise SchemeError("apply: expected at least 2 arguments")
        f = args[0]
        extra = args[1:-1]
        lst = args[-1]
        if not is_proper_list(lst):
            raise SchemeError("apply: last argument must be a proper list")
        all_args = extra + to_list(lst)
        if isinstance(f, Builtin):
            return f.func(all_args)
        elif isinstance(f, Closure):
            env = _apply_closure(f, all_args)
            return _evaluate(f.body[-1], env)
        else:
            raise SchemeError("apply: first argument must be a procedure")

    def _eq(args):
        if len(args) != 2:
            raise SchemeError("eq?: expected 2 arguments")
        a, b = args
        if isinstance(a, Symbol) and isinstance(b, Symbol):
            return a.name == b.name
        if type(a) is int and type(b) is int:
            return a == b
        if type(a) is bool and type(b) is bool:
            return a == b
        if a is EMPTY_LIST and b is EMPTY_LIST:
            return True
        return a is b

    def _equal(args):
        if len(args) != 2:
            raise SchemeError("equal?: expected 2 arguments")
        a, b = args
        work = [(a, b)]
        while work:
            a, b = work.pop()
            if a is b:
                continue
            a_bool = type(a) is bool
            b_bool = type(b) is bool
            a_int = type(a) is int
            b_int = type(b) is int
            a_str = isinstance(a, str)
            b_str = isinstance(b, str)
            a_sym = isinstance(a, Symbol)
            b_sym = isinstance(b, Symbol)
            a_pair = isinstance(a, Pair)
            b_pair = isinstance(b, Pair)
            a_empty = a is EMPTY_LIST
            b_empty = b is EMPTY_LIST
            a_proc = isinstance(a, (Closure, Builtin))
            b_proc = isinstance(b, (Closure, Builtin))

            if a_bool or b_bool:
                if not (a_bool and b_bool):
                    return False
                if a != b:
                    return False
            elif a_int and b_int:
                if a != b:
                    return False
            elif a_str and b_str:
                if a != b:
                    return False
            elif a_sym and b_sym:
                if a.name != b.name:
                    return False
            elif a_empty and b_empty:
                pass
            elif a_proc and b_proc:
                return False
            elif a_pair and b_pair:
                work.append((a.car, b.car))
                work.append((a.cdr, b.cdr))
            else:
                return False
        return True

    def _not(args):
        if len(args) != 1:
            raise SchemeError("not: expected 1 argument")
        return args[0] is False

    def _number_p(args):
        if len(args) != 1:
            raise SchemeError("number?: expected 1 argument")
        return type(args[0]) is int

    def _symbol_p(args):
        if len(args) != 1:
            raise SchemeError("symbol?: expected 1 argument")
        return isinstance(args[0], Symbol)

    def _string_p(args):
        if len(args) != 1:
            raise SchemeError("string?: expected 1 argument")
        return isinstance(args[0], str)

    def _procedure_p(args):
        if len(args) != 1:
            raise SchemeError("procedure?: expected 1 argument")
        return isinstance(args[0], (Closure, Builtin))

    def _string_append(args):
        for a in args:
            if not isinstance(a, str):
                raise SchemeError("string-append: expected string arguments")
        return ''.join(args)

    def _display(args):
        if len(args) != 1:
            raise SchemeError("display: expected 1 argument")
        output_buf.append(display_repr(args[0], True))
        return UNSPECIFIED

    def _newline(args):
        if len(args) != 0:
            raise SchemeError("newline: expected 0 arguments")
        output_buf.append("\n")
        return UNSPECIFIED

    def _error(args):
        if len(args) < 1:
            raise SchemeError("error: expected at least 1 argument")
        msg = args[0]
        if not isinstance(msg, str):
            raise SchemeError("error: first argument must be a string")
        full_msg = msg
        for irritant in args[1:]:
            full_msg += " " + display_repr(irritant, False)
        raise SchemeError(full_msg)

    frame['+'] = Builtin('+', _plus)
    frame['*'] = Builtin('*', _times)
    frame['-'] = Builtin('-', _minus)
    frame['quotient'] = Builtin('quotient', _quotient)
    frame['remainder'] = Builtin('remainder', _remainder)
    frame['modulo'] = Builtin('modulo', _modulo)
    frame['='] = Builtin('=', _compare('='))
    frame['<'] = Builtin('<', _compare('<'))
    frame['>'] = Builtin('>', _compare('>'))
    frame['<='] = Builtin('<=', _compare('<='))
    frame['>='] = Builtin('>=', _compare('>='))
    frame['number->string'] = Builtin('number->string', _number_to_string)
    frame['cons'] = Builtin('cons', _cons)
    frame['car'] = Builtin('car', _car)
    frame['cdr'] = Builtin('cdr', _cdr)
    frame['list'] = Builtin('list', _list)
    frame['null?'] = Builtin('null?', _null_p)
    frame['pair?'] = Builtin('pair?', _pair_p)
    frame['list?'] = Builtin('list?', _list_p)
    frame['length'] = Builtin('length', _length)
    frame['append'] = Builtin('append', _append)
    frame['reverse'] = Builtin('reverse', _reverse)
    frame['apply'] = Builtin('apply', _apply)
    frame['eq?'] = Builtin('eq?', _eq)
    frame['equal?'] = Builtin('equal?', _equal)
    frame['not'] = Builtin('not', _not)
    frame['number?'] = Builtin('number?', _number_p)
    frame['symbol?'] = Builtin('symbol?', _symbol_p)
    frame['string?'] = Builtin('string?', _string_p)
    frame['procedure?'] = Builtin('procedure?', _procedure_p)
    frame['string-append'] = Builtin('string-append', _string_append)
    frame['display'] = Builtin('display', _display)
    frame['newline'] = Builtin('newline', _newline)
    frame['error'] = Builtin('error', _error)

    return frame


# --- Evaluator ---

SPECIAL_FORMS = {'quote', 'if', 'define', 'set!', 'begin', 'cond', 'and', 'or', 'let', 'let*', 'letrec', 'lambda'}


def _apply_closure(closure, args):
    formals = closure.formals
    if isinstance(formals, Symbol):
        frame = {formals: make_list(args)}
    elif isinstance(formals, Pair):
        fixed = []
        rest_sym = None
        current = formals
        while isinstance(current, Pair):
            if not isinstance(current.car, Symbol):
                raise SchemeError("formal must be a symbol")
            fixed.append(current.car)
            current = current.cdr
        if current is not EMPTY_LIST:
            if not isinstance(current, Symbol):
                raise SchemeError("dotted formal must end in a symbol")
            rest_sym = current
        if rest_sym is None:
            if len(args) != len(fixed):
                raise SchemeError("wrong number of arguments")
            frame = {}
            for i, sym in enumerate(fixed):
                frame[sym] = args[i]
        else:
            if len(args) < len(fixed):
                raise SchemeError("wrong number of arguments")
            frame = {}
            for i, sym in enumerate(fixed):
                frame[sym] = args[i]
            frame[rest_sym] = make_list(args[len(fixed):])
    else:
        raise SchemeError("invalid formals")
    return Environment(frame, closure.env)


def _is_define_form(form):
    if not isinstance(form, Pair):
        return False
    if not is_proper_list(form):
        return False
    if form is EMPTY_LIST:
        return False
    head = form.car
    return isinstance(head, Symbol) and head.name == 'define'


def _get_define_name(form):
    rest = form.cdr
    first = rest.car
    if isinstance(first, Symbol):
        return first
    elif isinstance(first, Pair):
        return first.car
    else:
        raise SchemeError("malformed define")


def _parse_define(form):
    rest = form.cdr
    if rest is EMPTY_LIST:
        raise SchemeError("malformed define")
    first = rest.car
    if isinstance(first, Symbol):
        if rest.cdr is EMPTY_LIST:
            raise SchemeError("malformed define")
        name = first
        expr = rest.cdr.car
        if rest.cdr.cdr is not EMPTY_LIST:
            raise SchemeError("malformed define")
        return name, expr
    elif isinstance(first, Pair):
        if not is_proper_list(first):
            raise SchemeError("malformed define")
        name = first.car
        if not isinstance(name, Symbol):
            raise SchemeError("malformed define")
        formals = first.cdr
        body = to_list(rest.cdr)
        if not body:
            raise SchemeError("malformed define: empty body")
        lambda_form = Pair(Symbol('lambda'), Pair(formals, make_list(body)))
        return name, lambda_form
    else:
        raise SchemeError("malformed define")


def _parse_let_bindings(rest):
    """Parse ((v init) ...) from rest (a proper list)."""
    if rest is EMPTY_LIST:
        return []
    if not is_proper_list(rest):
        raise SchemeError("malformed let bindings")
    bindings = []
    current = rest
    while isinstance(current, Pair):
        binding = current.car
        if not isinstance(binding, Pair):
            raise SchemeError("malformed let binding")
        if not is_proper_list(binding):
            raise SchemeError("malformed let binding")
        if binding.cdr is EMPTY_LIST:
            raise SchemeError("malformed let binding: no init")
        name = binding.car
        if not isinstance(name, Symbol):
            raise SchemeError("let binding name must be a symbol")
        init = binding.cdr.car
        if binding.cdr.cdr is not EMPTY_LIST:
            raise SchemeError("malformed let binding")
        bindings.append((name, init))
        current = current.cdr
    return bindings


def _evaluate_body(forms, env):
    """Evaluate a body (Python list of forms) with internal definitions.
    The last form is in tail position."""
    if not forms:
        raise SchemeError("empty body")

    internal_names = set()
    for form in forms:
        if _is_define_form(form):
            name = _get_define_name(form)
            internal_names.add(name)

    if not internal_names:
        for i in range(len(forms) - 1):
            _evaluate(forms[i], env)
        return _evaluate(forms[-1], env)

    frame = {name: UNINITIALIZED for name in internal_names}
    new_env = Environment(frame, env)

    for i in range(len(forms) - 1):
        form = forms[i]
        if _is_define_form(form):
            name, expr = _parse_define(form)
            val = _evaluate(expr, new_env)
            frame[name] = val
        else:
            _evaluate(form, new_env)

    last = forms[-1]
    if _is_define_form(last):
        name, expr = _parse_define(last)
        val = _evaluate(expr, new_env)
        frame[name] = val
        return UNSPECIFIED
    else:
        return _evaluate(last, new_env)


def _evaluate(form, env):
    """Main evaluation loop with TCO."""
    while True:
        # Literals
        if type(form) is int:
            return form
        if type(form) is bool:
            return form
        if isinstance(form, str):
            return form
        if isinstance(form, Symbol):
            return env.lookup(form)
        if form is EMPTY_LIST:
            raise SchemeError("cannot apply ()")
        if form is UNSPECIFIED:
            return form
        if isinstance(form, (Closure, Builtin)):
            return form

        if isinstance(form, Pair):
            if not is_proper_list(form):
                raise SchemeError("dotted form used as application")

            head = form.car
            rest = form.cdr

            if isinstance(head, Symbol) and head.name in SPECIAL_FORMS:
                result = _handle_special_form(head.name, rest, env)
                if isinstance(result, _Continue):
                    form = result.form
                    env = result.env
                    continue
                return result

            # Application
            op = _evaluate(head, env)
            args = []
            current = rest
            while isinstance(current, Pair):
                args.append(_evaluate(current.car, env))
                current = current.cdr

            if not isinstance(op, (Closure, Builtin)):
                raise SchemeError(f"cannot apply {display_repr(op, True)}")

            # Special TCO for apply
            if isinstance(op, Builtin) and op.name == 'apply':
                if len(args) < 2:
                    raise SchemeError("apply: expected at least 2 arguments")
                f = args[0]
                extra = args[1:-1]
                lst = args[-1]
                if not is_proper_list(lst):
                    raise SchemeError("apply: last argument must be a proper list")
                all_args = extra + to_list(lst)
                if isinstance(f, Closure):
                    env = _apply_closure(f, all_args)
                    form = f.body[-1]
                    continue
                elif isinstance(f, Builtin):
                    return f.func(all_args)
                else:
                    raise SchemeError("apply: first argument must be a procedure")

            if isinstance(op, Closure):
                env = _apply_closure(op, args)
                form = op.body[-1]
                continue
            else:
                return op.func(args)

        raise SchemeError(f"invalid form")


class _Continue:
    __slots__ = ('form', 'env')
    def __init__(self, form, env):
        self.form = form
        self.env = env


def _handle_special_form(name, rest, env):
    """Handle a special form. Returns a value or _Continue(form, env)."""

    if name == 'quote':
        if rest is EMPTY_LIST:
            raise SchemeError("malformed quote")
        if rest.cdr is not EMPTY_LIST:
            raise SchemeError("malformed quote")
        return rest.car

    if name == 'if':
        if rest is EMPTY_LIST or rest.cdr is EMPTY_LIST:
            raise SchemeError("malformed if")
        test = rest.car
        then = rest.cdr.car
        has_else = rest.cdr.cdr is not EMPTY_LIST
        if has_else:
            else_form = rest.cdr.cdr.car
            if rest.cdr.cdr.cdr is not EMPTY_LIST:
                raise SchemeError("malformed if")
        test_val = _evaluate(test, env)
        if test_val is not False:
            return _Continue(then, env)
        else:
            if has_else:
                return _Continue(else_form, env)
            return UNSPECIFIED

    if name == 'define':
        if rest is EMPTY_LIST:
            raise SchemeError("malformed define")
        name_sym, expr = _parse_define(Pair(Symbol('define'), rest))
        val = _evaluate(expr, env)
        global_env = env.get_global()
        global_env.frame[name_sym] = val
        return UNSPECIFIED

    if name == 'set!':
        if rest is EMPTY_LIST or rest.cdr is EMPTY_LIST:
            raise SchemeError("malformed set!")
        if rest.cdr.cdr is not EMPTY_LIST:
            raise SchemeError("malformed set!")
        var = rest.car
        if not isinstance(var, Symbol):
            raise SchemeError("set!: variable must be a symbol")
        expr = rest.cdr.car
        val = _evaluate(expr, env)
        env.set(var, val)
        return UNSPECIFIED

    if name == 'begin':
        if rest is EMPTY_LIST:
            raise SchemeError("malformed begin")
        forms = to_list(rest)
        for i in range(len(forms) - 1):
            _evaluate(forms[i], env)
        return _Continue(forms[-1], env)

    if name == 'cond':
        if rest is EMPTY_LIST:
            raise SchemeError("malformed cond")
        clauses = to_list(rest)
        # Check else is only last
        for i, clause in enumerate(clauses[:-1]):
            if isinstance(clause, Pair) and isinstance(clause.car, Symbol) and clause.car.name == 'else':
                raise SchemeError("cond: else must be the last clause")
        for clause in clauses:
            if not isinstance(clause, Pair):
                raise SchemeError("malformed cond clause")
            if not is_proper_list(clause):
                raise SchemeError("malformed cond clause")
            test = clause.car
            exprs = to_list(clause.cdr)
            if isinstance(test, Symbol) and test.name == 'else':
                if not exprs:
                    raise SchemeError("cond: else clause must have expressions")
                for e in exprs[:-1]:
                    _evaluate(e, env)
                return _Continue(exprs[-1], env)
            else:
                test_val = _evaluate(test, env)
                if test_val is not False:
                    if not exprs:
                        return test_val
                    for e in exprs[:-1]:
                        _evaluate(e, env)
                    return _Continue(exprs[-1], env)
        return UNSPECIFIED

    if name == 'and':
        if rest is EMPTY_LIST:
            return True
        forms = to_list(rest)
        for i in range(len(forms) - 1):
            val = _evaluate(forms[i], env)
            if val is False:
                return False
        return _Continue(forms[-1], env)

    if name == 'or':
        if rest is EMPTY_LIST:
            return False
        forms = to_list(rest)
        for i in range(len(forms) - 1):
            val = _evaluate(forms[i], env)
            if val is not False:
                return val
        return _Continue(forms[-1], env)

    if name == 'let':
        # Check for named let
        first = rest.car
        if isinstance(first, Symbol):
            # Named let: (let name ((v init) ...) body...)
            let_name = first
            rest2 = rest.cdr
            if rest2 is EMPTY_LIST:
                raise SchemeError("malformed named let")
            bindings_list = rest2.car
            if not isinstance(bindings_list, Pair) and bindings_list is not EMPTY_LIST:
                raise SchemeError("malformed named let")
            bindings = _parse_let_bindings(bindings_list)
            body = to_list(rest2.cdr)
            if not body:
                raise SchemeError("malformed named let: empty body")
            # Evaluate inits in outer scope
            values = []
            for _, init in bindings:
                values.append(_evaluate(init, env))
            formals = [n for n, _ in bindings]
            closure = Closure(make_list(formals), body, None)
            frame = {let_name: closure}
            new_env = Environment(frame, env)
            closure.env = new_env
            # Tail-call the closure
            new_env2 = _apply_closure(closure, values)
            return _Continue(body[-1], new_env2)
        else:
            # Regular let: (let ((v init) ...) body...)
            bindings = _parse_let_bindings(rest)
            body = to_list(rest)
            # Wait, rest is ((v init) ...) body...
            # I need to separate bindings from body
            # rest = Pair(bindings_list, Pair(body1, Pair(body2, ...)))
            bindings_list = rest.car
            body = to_list(rest.cdr)
            if not body:
                raise SchemeError("malformed let: empty body")
            bindings = _parse_let_bindings(bindings_list)
            # Evaluate inits in outer scope
            values = []
            for _, init in bindings:
                values.append(_evaluate(init, env))
            frame = {}
            for (n, _), v in zip(bindings, values):
                frame[n] = v
            new_env = Environment(frame, env)
            return _Continue(body[-1], new_env)

    if name == 'let*':
        bindings_list = rest.car
        body = to_list(rest.cdr)
        if not body:
            raise SchemeError("malformed let*: empty body")
        bindings = _parse_let_bindings(bindings_list)
        frame = {}
        new_env = Environment(frame, env)
        for n, init in bindings:
            val = _evaluate(init, new_env)
            frame[n] = val
        return _Continue(body[-1], new_env)

    if name == 'letrec':
        bindings_list = rest.car
        body = to_list(rest.cdr)
        if not body:
            raise SchemeError("malformed letrec: empty body")
        bindings = _parse_let_bindings(bindings_list)
        frame = {n: UNINITIALIZED for n, _ in bindings}
        new_env = Environment(frame, env)
        for n, init in bindings:
            val = _evaluate(init, new_env)
            frame[n] = val
        return _Continue(body[-1], new_env)

    if name == 'lambda':
        if rest is EMPTY_LIST:
            raise SchemeError("malformed lambda")
        formals = rest.car
        body = to_list(rest.cdr)
        if not body:
            raise SchemeError("malformed lambda: empty body")
        # Validate formals
        if isinstance(formals, Symbol):
            pass  # rest parameter
        elif isinstance(formals, Pair):
            current = formals
            while isinstance(current, Pair):
                if not isinstance(current.car, Symbol):
                    raise SchemeError("formal must be a symbol")
                current = current.cdr
            if current is not EMPTY_LIST:
                if not isinstance(current, Symbol):
                    raise SchemeError("dotted formal must end in a symbol")
        else:
            raise SchemeError("invalid formals")
        return Closure(formals, body, env)

    raise SchemeError(f"unknown special form: {name}")


# --- Main run function ---

def run(source):
    # Phase 1: Read
    try:
        tokens = tokenize(source)
        forms = []
        pos = 0
        while pos < len(tokens):
            form, pos = parse(tokens, pos)
            forms.append(form)
    except SchemeError:
        raise
    except Exception as e:
        raise SchemeError(str(e))

    # Phase 2: Evaluate in a thread with large stack
    output_buf = []
    global_env = Environment(make_global_frame(output_buf))

    result = [None]
    error = [None]

    def target():
        sys.setrecursionlimit(100000)
        try:
            for form in forms:
                _evaluate(form, global_env)
            result[0] = ''.join(output_buf)
        except SchemeError as e:
            e.output = ''.join(output_buf)
            error[0] = e
        except RecursionError:
            error[0] = SchemeError("maximum recursion depth exceeded", output=''.join(output_buf))
        except Exception as e:
            error[0] = SchemeError(str(e), output=''.join(output_buf))

    t = threading.Thread(target=target, stack_size=64 * 1024 * 1024)
    t.start()
    t.join()

    if error[0] is not None:
        raise error[0]
    return result[0]
