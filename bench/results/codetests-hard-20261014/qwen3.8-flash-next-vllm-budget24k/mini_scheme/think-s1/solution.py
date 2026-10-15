import sys

try:
    sys.set_int_max_str_digits(0)
except (AttributeError, ValueError):
    pass

sys.setrecursionlimit(100000)


class SchemeError(Exception):
    def __init__(self, msg, output=''):
        super().__init__(msg)
        self.output = output


class Symbol:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name
    def __repr__(self):
        return self.name


class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr


class _EmptyList:
    def __repr__(self):
        return "()"

EMPTY = _EmptyList()


class _Unspecified:
    def __repr__(self):
        return "unspecified"

UNSPECIFIED = _Unspecified()


class _Uninitialized:
    pass

UNINITIALIZED = _Uninitialized()


class Builtin:
    def __init__(self, name, func):
        self.name = name
        self.func = func


class Closure:
    def __init__(self, formals, body, env):
        self.formals = formals
        self.body = body
        self.env = env


class TailCall:
    def __init__(self, proc, args):
        self.proc = proc
        self.args = args


class Env:
    __slots__ = ('frame', 'parent')
    def __init__(self, frame, parent):
        self.frame = frame
        self.parent = parent


def _is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)


def _is_bool(x):
    return isinstance(x, bool)


def _list_to_scheme(lst):
    result = EMPTY
    for item in reversed(lst):
        result = Pair(item, result)
    return result


def _scheme_to_list(p):
    result = []
    while isinstance(p, Pair):
        result.append(p.car)
        p = p.cdr
    if p is not EMPTY:
        raise SchemeError("not a proper list")
    return result


def _is_proper_list(p):
    while isinstance(p, Pair):
        p = p.cdr
    return p is EMPTY


# ============== READER ==============

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
            chars = []
            while i < n and source[i] != '"':
                if source[i] == '\\':
                    i += 1
                    if i >= n:
                        raise SchemeError("unterminated string")
                    nc = source[i]
                    if nc == '"':
                        chars.append('"')
                    elif nc == '\\':
                        chars.append('\\')
                    elif nc == 'n':
                        chars.append('\n')
                    else:
                        raise SchemeError("invalid escape: \\" + nc)
                    i += 1
                else:
                    chars.append(source[i])
                    i += 1
            if i >= n:
                raise SchemeError("unterminated string")
            i += 1
            tokens.append(('string', ''.join(chars)))
        else:
            start = i
            while i < n and source[i] not in ' \t\n\r()";\'':
                i += 1
            tokens.append(('atom', source[start:i]))
    return tokens


def _is_integer_token(s):
    if not s:
        return False
    i = 0
    if s[0] in '+-':
        i = 1
    if i >= len(s):
        return False
    while i < len(s):
        if s[i] < '0' or s[i] > '9':
            return False
        i += 1
    return True


def _parse_all(source):
    tokens = _tokenize(source)
    pos = [0]

    def peek():
        return tokens[pos[0]] if pos[0] < len(tokens) else None

    def consume():
        t = tokens[pos[0]]
        pos[0] += 1
        return t

    def parse_datum():
        tok = peek()
        if tok is None:
            raise SchemeError("unexpected end of input")
        kind, val = tok
        if kind == '(':
            return parse_list()
        elif kind == "'":
            consume()
            datum = parse_datum()
            return Pair(Symbol('quote'), Pair(datum, EMPTY))
        elif kind == 'string':
            consume()
            return val
        elif kind == 'atom':
            consume()
            return parse_atom(val)
        elif kind == ')':
            raise SchemeError("unexpected )")
        else:
            raise SchemeError("unexpected token")

    def parse_list():
        consume()
        elements = []
        while True:
            tok = peek()
            if tok is None:
                raise SchemeError("unbalanced (")
            if tok[0] == ')':
                consume()
                break
            if tok[0] == 'atom' and tok[1] == '.':
                if len(elements) == 0:
                    raise SchemeError("dot with no preceding element")
                consume()
                dot_val = parse_datum()
                tok = peek()
                if tok is None or tok[0] != ')':
                    raise SchemeError("expected ) after dotted pair")
                consume()
                result = dot_val
                for elem in reversed(elements):
                    result = Pair(elem, result)
                return result
            elements.append(parse_datum())
        result = EMPTY
        for elem in reversed(elements):
            result = Pair(elem, result)
        return result

    def parse_atom(s):
        if _is_integer_token(s):
            return int(s)
        if s == '#t':
            return True
        if s == '#f':
            return False
        if s.startswith('#'):
            raise SchemeError("invalid token: " + s)
        return Symbol(s)

    datums = []
    while pos[0] < len(tokens):
        datums.append(parse_datum())
    return datums


# ============== FORMATTING ==============

def _format(val, write=False):
    result = []
    stack = [(val, write)]
    while stack:
        item = stack.pop()
        if isinstance(item, tuple) and len(item) == 2 and item[0] == _LIT:
            result.append(item[1])
            continue
        v, w = item
        if _is_int(v):
            result.append(str(v))
        elif isinstance(v, bool):
            result.append('#t' if v else '#f')
        elif isinstance(v, Symbol):
            result.append(v.name)
        elif isinstance(v, str):
            if w:
                result.append('"')
                for c in v:
                    if c == '"':
                        result.append('\\"')
                    elif c == '\\':
                        result.append('\\\\')
                    elif c == '\n':
                        result.append('\\n')
                    else:
                        result.append(c)
                result.append('"')
            else:
                result.append(v)
        elif v is EMPTY:
            result.append('()')
        elif isinstance(v, Pair):
            elements = []
            cur = v
            while isinstance(cur, Pair):
                elements.append(cur.car)
                cur = cur.cdr
            stack.append((_LIT, ')'))
            if cur is not EMPTY:
                stack.append((_LIT, ' . '))
                stack.append((cur, w))
            for i in range(len(elements) - 1, -1, -1):
                if i > 0:
                    stack.append((_LIT, ' '))
                stack.append((elements[i], w))
            stack.append((_LIT, '('))
        elif isinstance(v, (Builtin, Closure)):
            result.append('#<procedure>')
        elif v is UNSPECIFIED:
            pass
        else:
            result.append(str(v))
    return ''.join(result)


_LIT = object()


# ============== INTERPRETER ==============

class Interpreter:
    def __init__(self):
        self.output = []
        self.global_frame = {}
        self.global_env = Env(self.global_frame, None)
        self._setup_globals()

    def _setup_globals(self):
        gf = self.global_frame

        def bi(name, func):
            gf[name] = Builtin(name, func)

        # Numbers
        def _check_nums(args):
            for a in args:
                if not _is_int(a):
                    raise SchemeError("expected a number")

        def _plus(args):
            _check_nums(args)
            s = 0
            for a in args:
                s += a
            return s

        def _times(args):
            _check_nums(args)
            p = 1
            for a in args:
                p *= a
            return p

        def _minus(args):
            _check_nums(args)
            if len(args) == 1:
                return -args[0]
            r = args[0]
            for a in args[1:]:
                r -= a
            return r

        def _quotient(args):
            _check_nums(args)
            if args[1] == 0:
                raise SchemeError("division by zero")
            q = abs(args[0]) // abs(args[1])
            if (args[0] < 0) != (args[1] < 0):
                q = -q
            return q

        def _remainder(args):
            _check_nums(args)
            if args[1] == 0:
                raise SchemeError("division by zero")
            return args[0] % args[1] if args[0] >= 0 else -((-args[0]) % abs(args[1]))

        def _modulo(args):
            _check_nums(args)
            if args[1] == 0:
                raise SchemeError("division by zero")
            r = args[0] % args[1]
            return r

        # Fix remainder for negative dividend
        def _remainder2(args):
            _check_nums(args)
            if args[1] == 0:
                raise SchemeError("division by zero")
            a, b = args[0], args[1]
            q = abs(a) // abs(b)
            if (a < 0) != (b < 0):
                q = -q
            return a - q * b

        def _make_cmp(op):
            def cmp_fn(args):
                _check_nums(args)
                for i in range(len(args) - 1):
                    if not op(args[i], args[i + 1]):
                        return False
                return True
            return cmp_fn

        bi('+', _plus)
        bi('*', _times)
        bi('-', _minus)
        bi('quotient', _quotient)
        bi('remainder', _remainder2)
        bi('modulo', _modulo)
        bi('=', _make_cmp(lambda a, b: a == b))
        bi('<', _make_cmp(lambda a, b: a < b))
        bi('>', _make_cmp(lambda a, b: a > b))
        bi('<=', _make_cmp(lambda a, b: a <= b))
        bi('>=', _make_cmp(lambda a, b: a >= b))

        def _number_to_string(args):
            if len(args) < 1 or len(args) > 2:
                raise SchemeError("number->string: wrong arity")
            n = args[0]
            if not _is_int(n):
                raise SchemeError("number->string: expected integer")
            radix = args[1] if len(args) == 2 else 10
            if not _is_int(radix) or radix not in (2, 8, 10, 16):
                raise SchemeError("number->string: invalid radix")
            if radix == 10:
                return str(n)
            if n == 0:
                return "0"
            neg = n < 0
            n = abs(n)
            digits = "0123456789abcdef"
            parts = []
            while n > 0:
                parts.append(digits[n % radix])
                n //= radix
            if neg:
                parts.append('-')
            return ''.join(reversed(parts))

        bi('number->string', _number_to_string)

        # Lists and pairs
        def _cons(args):
            return Pair(args[0], args[1])

        def _car(args):
            p = args[0]
            if not isinstance(p, Pair):
                raise SchemeError("car: not a pair")
            return p.car

        def _cdr(args):
            p = args[0]
            if not isinstance(p, Pair):
                raise SchemeError("cdr: not a pair")
            return p.cdr

        def _list(args):
            return _list_to_scheme(args)

        def _null_p(args):
            return args[0] is EMPTY

        def _pair_p(args):
            return isinstance(args[0], Pair)

        def _list_p(args):
            return _is_proper_list(args[0])

        def _length(args):
            l = args[0]
            count = 0
            while isinstance(l, Pair):
                count += 1
                l = l.cdr
            if l is not EMPTY:
                raise SchemeError("length: not a proper list")
            return count

        def _append(args):
            if not args:
                return EMPTY
            for lst in args[:-1]:
                if not _is_proper_list(lst):
                    raise SchemeError("append: not a proper list")
            result = args[-1]
            for lst in reversed(args[:-1]):
                elements = []
                cur = lst
                while isinstance(cur, Pair):
                    elements.append(cur.car)
                    cur = cur.cdr
                for elem in reversed(elements):
                    result = Pair(elem, result)
            return result

        def _reverse(args):
            l = args[0]
            result = EMPTY
            while isinstance(l, Pair):
                result = Pair(l.car, result)
                l = l.cdr
            if l is not EMPTY:
                raise SchemeError("reverse: not a proper list")
            return result

        def _apply_builtin(args):
            f = args[0]
            regular = list(args[1:-1])
            lst = args[-1]
            if not _is_proper_list(lst):
                raise SchemeError("apply: last argument not a proper list")
            extra = []
            cur = lst
            while isinstance(cur, Pair):
                extra.append(cur.car)
                cur = cur.cdr
            all_args = regular + extra
            return self.force(self.apply(f, all_args))

        bi('cons', _cons)
        bi('car', _car)
        bi('cdr', _cdr)
        bi('list', _list)
        bi('null?', _null_p)
        bi('pair?', _pair_p)
        bi('list?', _list_p)
        bi('length', _length)
        bi('append', _append)
        bi('reverse', _reverse)
        bi('apply', _apply_builtin)

        # Equality and predicates
        def _eq(args):
            a, b = args[0], args[1]
            if a is b:
                return True
            if _is_int(a) and _is_int(b):
                return a == b
            if isinstance(a, bool) and isinstance(b, bool):
                return a == b
            if isinstance(a, Symbol) and isinstance(b, Symbol):
                return a.name == b.name
            return False

        def _equal(args):
            return _equal_iter(args[0], args[1])

        def _not(args):
            return args[0] is False

        def _number_p(args):
            return _is_int(args[0])

        def _symbol_p(args):
            return isinstance(args[0], Symbol)

        def _string_p(args):
            return isinstance(args[0], str)

        def _procedure_p(args):
            return isinstance(args[0], (Builtin, Closure))

        def _string_append(args):
            parts = []
            for s in args:
                if not isinstance(s, str):
                    raise SchemeError("string-append: expected string")
                parts.append(s)
            return ''.join(parts)

        bi('eq?', _eq)
        bi('equal?', _equal)
        bi('not', _not)
        bi('number?', _number_p)
        bi('symbol?', _symbol_p)
        bi('string?', _string_p)
        bi('procedure?', _procedure_p)
        bi('string-append', _string_append)

        # Output and errors
        def _display(args):
            self.output.append(_format(args[0], write=False))
            return UNSPECIFIED

        def _newline(args):
            self.output.append('\n')
            return UNSPECIFIED

        def _error(args):
            msg = args[0]
            if not isinstance(msg, str):
                raise SchemeError("error: first argument must be a string")
            parts = [msg]
            for irr in args[1:]:
                parts.append(' ')
                parts.append(_format(irr, write=True))
            raise SchemeError(''.join(parts))

        bi('display', _display)
        bi('newline', _newline)
        bi('error', _error)

    def run(self, source):
        try:
            forms = _parse_all(source)
        except SchemeError as e:
            e.output = ''
            raise
        except Exception as e:
            raise SchemeError(str(e), '')

        for form in forms:
            try:
                self.force(self.eval(form, self.global_env, False))
            except SchemeError as e:
                e.output = ''.join(self.output)
                raise
        return ''.join(self.output)

    def force(self, result):
        while isinstance(result, TailCall):
            result = self.apply(result.proc, result.args)
        return result

    def apply(self, proc, args):
        if isinstance(proc, Builtin):
            return proc.func(args)
        elif isinstance(proc, Closure):
            return self._apply_closure(proc, args)
        else:
            raise SchemeError("not a procedure")

    def _apply_closure(self, closure, args):
        formals = closure.formals
        kind = formals[0]
        frame = {}
        if kind == 'fixed':
            params = formals[1]
            if len(args) != len(params):
                raise SchemeError("wrong number of arguments")
            for i, p in enumerate(params):
                frame[p.name] = args[i]
        elif kind == 'variadic':
            sym = formals[1]
            frame[sym.name] = _list_to_scheme(args)
        elif kind == 'dotted':
            params = formals[1]
            rest = formals[2]
            if len(args) < len(params):
                raise SchemeError("too few arguments")
            for i, p in enumerate(params):
                frame[p.name] = args[i]
            frame[rest.name] = _list_to_scheme(args[len(params):])

        env = Env(frame, closure.env)
        body = closure.body

        define_names = self._scan_internal_defines(body)
        for name in define_names:
            frame[name] = UNINITIALIZED

        result = UNSPECIFIED
        for i in range(len(body)):
            form = body[i]
            if self._is_define_form(form):
                self._exec_define_in_body(form, env, frame)
                result = UNSPECIFIED
            elif i == len(body) - 1:
                return self.eval(form, env, True)
            else:
                result = self.force(self.eval(form, env, False))
        return result

    def eval(self, expr, env, tail):
        if _is_int(expr):
            return expr
        if isinstance(expr, bool):
            return expr
        if isinstance(expr, str):
            return expr
        if isinstance(expr, Symbol):
            return self._lookup(env, expr.name)
        if expr is EMPTY:
            raise SchemeError("cannot evaluate empty list")
        if isinstance(expr, Pair):
            return self._eval_pair(expr, env, tail)
        raise SchemeError("invalid expression")

    def _eval_pair(self, expr, env, tail):
        head = expr.car
        if isinstance(head, Symbol):
            name = head.name
            if name == 'quote':
                return self._eval_quote(expr)
            elif name == 'if':
                return self._eval_if(expr, env, tail)
            elif name == 'define':
                return self._eval_define(expr, env)
            elif name == 'set!':
                return self._eval_set(expr, env)
            elif name == 'begin':
                return self._eval_begin(expr, env, tail)
            elif name == 'cond':
                return self._eval_cond(expr, env, tail)
            elif name == 'and':
                return self._eval_and(expr, env, tail)
            elif name == 'or':
                return self._eval_or(expr, env, tail)
            elif name == 'lambda':
                return self._eval_lambda(expr, env)
            elif name == 'let':
                return self._eval_let(expr, env, tail)
            elif name == 'let*':
                return self._eval_letstar(expr, env, tail)
            elif name == 'letrec':
                return self._eval_letrec(expr, env, tail)
            elif name == 'apply':
                return self._eval_apply(expr, env, tail)

        return self._eval_application(expr, env, tail)

    def _eval_application(self, expr, env, tail):
        proc = self.force(self.eval(expr.car, env, False))
        args = []
        cur = expr.cdr
        while cur is not EMPTY:
            if not isinstance(cur, Pair):
                raise SchemeError("dotted form used as application")
            args.append(self.force(self.eval(cur.car, env, False)))
            cur = cur.cdr
        if not isinstance(proc, (Builtin, Closure)):
            raise SchemeError("not a procedure")
        if isinstance(proc, Closure):
            self._check_closure_arity(proc, args)
        if tail:
            return TailCall(proc, args)
        else:
            return self.force(self.apply(proc, args))

    def _check_closure_arity(self, closure, args):
        formals = closure.formals
        kind = formals[0]
        if kind == 'fixed':
            if len(args) != len(formals[1]):
                raise SchemeError("wrong number of arguments")
        elif kind == 'dotted':
            if len(args) < len(formals[1]):
                raise SchemeError("too few arguments")

    def _lookup(self, env, name):
        e = env
        while e is not None:
            if name in e.frame:
                val = e.frame[name]
                if isinstance(val, _Uninitialized):
                    raise SchemeError("uninitialized variable: " + name)
                return val
            e = e.parent
        raise SchemeError("unbound variable: " + name)

    def _set_var(self, env, name, val):
        e = env
        while e is not None:
            if name in e.frame:
                e.frame[name] = val
                return
            e = e.parent
        raise SchemeError("unbound variable: " + name)

    # --- Special forms ---

    def _eval_quote(self, expr):
        cdr = expr.cdr
        if not isinstance(cdr, Pair) or cdr.cdr is not EMPTY:
            raise SchemeError("malformed quote")
        return cdr.car

    def _eval_if(self, expr, env, tail):
        cdr = expr.cdr
        if not isinstance(cdr, Pair):
            raise SchemeError("malformed if")
        test_expr = cdr.car
        then_cdr = cdr.cdr
        if not isinstance(then_cdr, Pair):
            raise SchemeError("malformed if")
        then_expr = then_cdr.car
        else_cdr = then_cdr.cdr

        test_val = self.force(self.eval(test_expr, env, False))
        if test_val is not False:
            return self.eval(then_expr, env, tail)
        else:
            if else_cdr is EMPTY:
                return UNSPECIFIED
            if not isinstance(else_cdr, Pair):
                raise SchemeError("malformed if")
            return self.eval(else_cdr.car, env, tail)

    def _eval_define(self, expr, env):
        cdr = expr.cdr
        if not isinstance(cdr, Pair):
            raise SchemeError("malformed define")
        target = cdr.car
        rest = cdr.cdr

        if isinstance(target, Symbol):
            # (define name expr)
            if not isinstance(rest, Pair) or rest.cdr is not EMPTY:
                raise SchemeError("malformed define")
            val = self.force(self.eval(rest.car, env, False))
            env.frame[target.name] = val
            return UNSPECIFIED
        elif isinstance(target, Pair):
            # (define (name . formals) body...)
            name = target.car
            if not isinstance(name, Symbol):
                raise SchemeError("malformed define: name must be a symbol")
            formals = target.cdr
            if not isinstance(rest, Pair):
                raise SchemeError("malformed define: missing body")
            body = _pair_to_list(rest)
            formals_parsed = self._parse_formals(formals)
            closure = Closure(formals_parsed, body, env)
            env.frame[name.name] = closure
            return UNSPECIFIED
        else:
            raise SchemeError("malformed define")

    def _eval_set(self, expr, env):
        cdr = expr.cdr
        if not isinstance(cdr, Pair):
            raise SchemeError("malformed set!")
        name_expr = cdr.car
        if not isinstance(name_expr, Symbol):
            raise SchemeError("set!: expected a symbol")
        val_expr = cdr.cdr
        if not isinstance(val_expr, Pair) or val_expr.cdr is not EMPTY:
            raise SchemeError("malformed set!")
        val = self.force(self.eval(val_expr.car, env, False))
        self._set_var(env, name_expr.name, val)
        return UNSPECIFIED

    def _eval_begin(self, expr, env, tail):
        forms = _pair_to_list(expr.cdr)
        if not forms:
            raise SchemeError("malformed begin")
        for i in range(len(forms) - 1):
            self.force(self.eval(forms[i], env, False))
        return self.eval(forms[-1], env, tail)

    def _eval_cond(self, expr, env, tail):
        clauses = _pair_to_list(expr.cdr)
        if not clauses:
            raise SchemeError("malformed cond")
        for i, clause in enumerate(clauses):
            if not isinstance(clause, Pair):
                raise SchemeError("malformed cond clause")
            test = clause.car
            body = _pair_to_list_safe(clause.cdr)

            if isinstance(test, Symbol) and test.name == 'else':
                if i != len(clauses) - 1:
                    raise SchemeError("else must be last clause")
                if not body:
                    raise SchemeError("malformed else clause")
                for j in range(len(body) - 1):
                    self.force(self.eval(body[j], env, False))
                return self.eval(body[-1], env, tail)

            val = self.force(self.eval(test, env, False))
            if val is not False:
                if not body:
                    return val
                for j in range(len(body) - 1):
                    self.force(self.eval(body[j], env, False))
                return self.eval(body[-1], env, tail)
        return UNSPECIFIED

    def _eval_and(self, expr, env, tail):
        forms = _pair_to_list(expr.cdr)
        if not forms:
            return True
        for i in range(len(forms) - 1):
            val = self.force(self.eval(forms[i], env, False))
            if val is False:
                return False
        return self.eval(forms[-1], env, tail)

    def _eval_or(self, expr, env, tail):
        forms = _pair_to_list(expr.cdr)
        if not forms:
            return False
        for i in range(len(forms) - 1):
            val = self.force(self.eval(forms[i], env, False))
            if val is not False:
                return val
        return self.eval(forms[-1], env, tail)

    def _eval_lambda(self, expr, env):
        cdr = expr.cdr
        if not isinstance(cdr, Pair):
            raise SchemeError("malformed lambda")
        formals = cdr.car
        body_cdr = cdr.cdr
        if not isinstance(body_cdr, Pair):
            raise SchemeError("malformed lambda: empty body")
        body = _pair_to_list(body_cdr)
        formals_parsed = self._parse_formals(formals)
        return Closure(formals_parsed, body, env)

    def _eval_let(self, expr, env, tail):
        cdr = expr.cdr
        if not isinstance(cdr, Pair):
            raise SchemeError("malformed let")
        # Check for named let
        first = cdr.car
        if isinstance(first, Symbol):
            return self._eval_named_let(cdr, env, tail)

        bindings = _pair_to_list_safe(cdr.car)
        body_cdr = cdr.cdr
        if not isinstance(body_cdr, Pair):
            raise SchemeError("malformed let: empty body")
        body = _pair_to_list(body_cdr)

        # Evaluate inits in outer scope
        names = []
        vals = []
        for b in bindings:
            if not isinstance(b, Pair):
                raise SchemeError("malformed let binding")
            var = b.car
            if not isinstance(var, Symbol):
                raise SchemeError("malformed let binding: not a symbol")
            init_cdr = b.cdr
            if not isinstance(init_cdr, Pair) or init_cdr.cdr is not EMPTY:
                raise SchemeError("malformed let binding")
            names.append(var.name)
            vals.append(self.force(self.eval(init_cdr.car, env, False)))

        frame = {}
        for i, name in enumerate(names):
            frame[name] = vals[i]
        new_env = Env(frame, env)

        # Internal defines
        define_names = self._scan_internal_defines(body)
        for name in define_names:
            frame[name] = UNINITIALIZED

        result = UNSPECIFIED
        for i in range(len(body)):
            form = body[i]
            if self._is_define_form(form):
                self._exec_define_in_body(form, new_env, frame)
                result = UNSPECIFIED
            elif i == len(body) - 1:
                return self.eval(form, new_env, tail)
            else:
                result = self.force(self.eval(form, new_env, False))
        return result

    def _eval_named_let(self, cdr, env, tail):
        # cdr starts with the name symbol
        name_sym = cdr.car
        bindings_cdr = cdr.cdr
        if not isinstance(bindings_cdr, Pair):
            raise SchemeError("malformed named let")
        bindings = _pair_to_list_safe(bindings_cdr.car)
        body_cdr = bindings_cdr.cdr
        if not isinstance(body_cdr, Pair):
            raise SchemeError("malformed named let: empty body")
        body = _pair_to_list(body_cdr)

        # Evaluate inits in outer scope
        names = []
        inits = []
        for b in bindings:
            if not isinstance(b, Pair):
                raise SchemeError("malformed let binding")
            var = b.car
            if not isinstance(var, Symbol):
                raise SchemeError("malformed let binding: not a symbol")
            init_cdr = b.cdr
            if not isinstance(init_cdr, Pair) or init_cdr.cdr is not EMPTY:
                raise SchemeError("malformed let binding")
            names.append(var)
            inits.append(init_cdr.car)

        init_vals = [self.force(self.eval(init, env, False)) for init in inits]

        # Create letrec-like binding
        frame = {}
        frame[name_sym.name] = UNINITIALIZED
        letrec_env = Env(frame, env)

        formals_parsed = ('fixed', names)
        closure = Closure(formals_parsed, body, letrec_env)
        frame[name_sym.name] = closure

        args = init_vals
        if tail:
            return TailCall(closure, args)
        else:
            return self.force(self.apply(closure, args))

    def _eval_letstar(self, expr, env, tail):
        cdr = expr.cdr
        if not isinstance(cdr, Pair):
            raise SchemeError("malformed let*")
        bindings = _pair_to_list_safe(cdr.car)
        body_cdr = cdr.cdr
        if not isinstance(body_cdr, Pair):
            raise SchemeError("malformed let*: empty body")
        body = _pair_to_list(body_cdr)

        frame = {}
        cur_env = env
        for b in bindings:
            if not isinstance(b, Pair):
                raise SchemeError("malformed let* binding")
            var = b.car
            if not isinstance(var, Symbol):
                raise SchemeError("malformed let* binding: not a symbol")
            init_cdr = b.cdr
            if not isinstance(init_cdr, Pair) or init_cdr.cdr is not EMPTY:
                raise SchemeError("malformed let* binding")
            val = self.force(self.eval(init_cdr.car, cur_env, False))
            frame[var.name] = val
            cur_env = Env(frame, env)

        # Internal defines
        define_names = self._scan_internal_defines(body)
        for name in define_names:
            frame[name] = UNINITIALIZED

        result = UNSPECIFIED
        for i in range(len(body)):
            form = body[i]
            if self._is_define_form(form):
                self._exec_define_in_body(form, cur_env, frame)
                result = UNSPECIFIED
            elif i == len(body) - 1:
                return self.eval(form, cur_env, tail)
            else:
                result = self.force(self.eval(form, cur_env, False))
        return result

    def _eval_letrec(self, expr, env, tail):
        cdr = expr.cdr
        if not isinstance(cdr, Pair):
            raise SchemeError("malformed letrec")
        bindings = _pair_to_list_safe(cdr.car)
        body_cdr = cdr.cdr
        if not isinstance(body_cdr, Pair):
            raise SchemeError("malformed letrec: empty body