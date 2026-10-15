import sys
import re

try:
    sys.set_int_max_str_digits(0)
except (AttributeError, ValueError):
    pass
sys.setrecursionlimit(200000)


class SchemeError(Exception):
    def __init__(self, message, output=''):
        super().__init__(message)
        self.output = output


class Symbol:
    __slots__ = ('name',)
    _intern = {}

    def __new__(cls, name):
        if name in cls._intern:
            return cls._intern[name]
        obj = super().__new__(cls)
        obj.name = name
        cls._intern[name] = obj
        return obj

    def __repr__(self):
        return f"Symbol({self.name})"


class Pair:
    __slots__ = ('car', 'cdr')

    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr


class _Nil:
    def __repr__(self):
        return '()'


NIL = _Nil()


class _Unspecified:
    def __repr__(self):
        return '#<unspecified>'


UNSPECIFIED = _Unspecified()


class _Unbound:
    pass


UNBOUND = _Unbound()


class Closure:
    __slots__ = ('params', 'rest_param', 'body', 'env')

    def __init__(self, params, rest_param, body, env):
        self.params = params
        self.rest_param = rest_param
        self.body = body
        self.env = env


class Builtin:
    __slots__ = ('name', 'func', 'min_args', 'max_args')

    def __init__(self, name, func, min_args=0, max_args=None):
        self.name = name
        self.func = func
        self.min_args = min_args
        self.max_args = max_args


class TailCall:
    __slots__ = ('proc', 'args')

    def __init__(self, proc, args):
        self.proc = proc
        self.args = args


class Env:
    __slots__ = ('frame', 'parent')

    def __init__(self, frame, parent=None):
        self.frame = frame
        self.parent = parent


# ============ READER ============

_INT_RE = re.compile(r'^[+-]?[0-9]+$')


def tokenize(source):
    tokens = []
    i = 0
    n = len(source)
    while i < n:
        c = source[i]
        if c in ' \t\n\r':
            i += 1
            continue
        if c == ';':
            while i < n and source[i] != '\n':
                i += 1
            continue
        if c in '()\'':
            tokens.append(c)
            i += 1
            continue
        if c == '"':
            i += 1
            s = []
            terminated = False
            while i < n:
                c2 = source[i]
                if c2 == '\\':
                    i += 1
                    if i >= n:
                        raise SchemeError("unterminated string")
                    ec = source[i]
                    if ec == '"':
                        s.append('"')
                    elif ec == '\\':
                        s.append('\\')
                    elif ec == 'n':
                        s.append('\n')
                    else:
                        raise SchemeError(f"invalid escape \\{ec}")
                    i += 1
                elif c2 == '"':
                    i += 1
                    terminated = True
                    break
                else:
                    s.append(c2)
                    i += 1
            if not terminated:
                raise SchemeError("unterminated string")
            tokens.append(('STRING', ''.join(s)))
            continue
        start = i
        while i < n and source[i] not in ' \t\n\r()\";\'':
            i += 1
        tok = source[start:i]
        if tok:
            tokens.append(tok)
    return tokens


def parse_atom(token):
    if token == '#t':
        return True
    if token == '#f':
        return False
    if token.startswith('#'):
        raise SchemeError(f"syntax error: {token}")
    if _INT_RE.match(token):
        return int(token)
    return Symbol(token)


def parse_datum(tokens, pos):
    if pos >= len(tokens):
        raise SchemeError("unexpected end of input")
    token = tokens[pos]
    if token == '(':
        return parse_list(tokens, pos + 1)
    if token == ')':
        raise SchemeError("unexpected )")
    if token == "'":
        datum, pos2 = parse_datum(tokens, pos + 1)
        return Pair(Symbol('quote'), Pair(datum, NIL)), pos2
    if isinstance(token, tuple) and token[0] == 'STRING':
        return token[1], pos + 1
    return parse_atom(token), pos + 1


def parse_list(tokens, pos):
    elements = []
    dotted = False
    rest = None
    while True:
        if pos >= len(tokens):
            raise SchemeError("unbalanced (")
        token = tokens[pos]
        if token == ')':
            pos += 1
            break
        if token == '.':
            if dotted:
                raise SchemeError("multiple dots in list")
            if not elements:
                raise SchemeError("dot without preceding element")
            dotted = True
            pos += 1
            datum, pos = parse_datum(tokens, pos)
            rest = datum
            if pos >= len(tokens) or tokens[pos] != ')':
                raise SchemeError("expected ) after dotted rest")
            pos += 1
            break
        datum, pos = parse_datum(tokens, pos)
        elements.append(datum)
    if dotted:
        result = rest
    else:
        result = NIL
    for elem in reversed(elements):
        result = Pair(elem, result)
    return result, pos


def read_all(source):
    tokens = tokenize(source)
    forms = []
    pos = 0
    while pos < len(tokens):
        datum, pos = parse_datum(tokens, pos)
        forms.append(datum)
    return forms


# ============ HELPERS ============

def is_true(x):
    return x is not False


SPECIAL_FORMS = {'quote', 'if', 'define', 'set!', 'begin', 'cond', 'and', 'or',
                 'let', 'let*', 'letrec', 'apply'}


# ============ INTERPRETER ============

class Interpreter:
    def __init__(self):
        self.output = []
        self.global_frame = {}
        self.global_env = Env(self.global_frame)
        self._setup_builtins()

    def get_output(self):
        return ''.join(self.output)

    # ---- Environment helpers ----

    def lookup(self, name, env):
        e = env
        while e is not None:
            if name in e.frame:
                val = e.frame[name]
                if val is UNBOUND:
                    raise SchemeError(f"unbound variable: {name.name}")
                return val
            e = e.parent
        raise SchemeError(f"unbound variable: {name.name}")

    # ---- Core evaluation ----

    def resolve(self, result):
        while isinstance(result, TailCall):
            result = self.apply_proc(result.proc, result.args)
        return result

    def eval_expr(self, expr, env):
        if isinstance(expr, bool):
            return expr
        if isinstance(expr, int):
            return expr
        if isinstance(expr, str):
            return expr
        if isinstance(expr, Symbol):
            return self.lookup(expr, env)
        if expr is NIL:
            raise SchemeError("cannot evaluate ()")
        if isinstance(expr, Pair):
            head = expr.car
            if isinstance(head, Symbol) and head.name in SPECIAL_FORMS:
                return self.eval_special(head.name, expr.cdr, env)
            proc = self.resolve(self.eval_expr(head, env))
            args = self.eval_args(expr.cdr, env)
            return self.apply_proc(proc, args)
        raise SchemeError("cannot evaluate expression")

    def eval_args(self, args, env):
        result = []
        current = args
        while current is not NIL:
            if not isinstance(current, Pair):
                raise SchemeError("improper argument list")
            result.append(self.resolve(self.eval_expr(current.car, env)))
            current = current.cdr
        return result

    def apply_proc(self, proc, args):
        if isinstance(proc, Closure):
            n = len(proc.params)
            if proc.rest_param is None:
                if len(args) != n:
                    raise SchemeError(f"wrong number of arguments (expected {n}, got {len(args)})")
            else:
                if len(args) < n:
                    raise SchemeError(f"wrong number of arguments (expected at least {n}, got {len(args)})")
            frame = {}
            for i, p in enumerate(proc.params):
                frame[p] = args[i]
            if proc.rest_param is not None:
                rest_list = NIL
                for a in reversed(args[n:]):
                    rest_list = Pair(a, rest_list)
                frame[proc.rest_param] = rest_list
            new_env = Env(frame, proc.env)
            return self.eval_body(proc.body, new_env)
        elif isinstance(proc, Builtin):
            if len(args) < proc.min_args:
                raise SchemeError(f"{proc.name}: too few arguments")
            if proc.max_args is not None and len(args) > proc.max_args:
                raise SchemeError(f"{proc.name}: too many arguments")
            return proc.func(args)
        else:
            raise SchemeError("not a procedure")

    def eval_body(self, forms, env):
        if not forms:
            raise SchemeError("empty body")
        for form in forms[:-1]:
            self.resolve(self.eval_expr(form, env))
        return self.eval_expr(forms[-1], env)

    def eval_body_with_defs(self, body, env):
        internal_defs = self._scan_internal_defs(body)
        frame = {}
        for name in internal_defs:
            frame[name] = UNBOUND
        new_env = Env(frame, env)
        return self.eval_body(body, new_env)

    def _scan_internal_defs(self, body):
        names = []
        for form in body:
            if isinstance(form, Pair) and isinstance(form.car, Symbol) and form.car.name == 'define':
                args = form.cdr
                if args is not NIL and isinstance(args, Pair):
                    target = args.car
                    if isinstance(target, Symbol):
                        names.append(target)
                    elif isinstance(target, Pair) and isinstance(target.car, Symbol):
                        names.append(target.car)
        return names

    def _to_list(self, pair):
        result = []
        current = pair
        while current is not NIL:
            if not isinstance(current, Pair):
                raise SchemeError("malformed form")
            result.append(current.car)
            current = current.cdr
        return result

    def _parse_formals(self, formals):
        if isinstance(formals, Symbol):
            return [], formals
        if formals is NIL:
            return [], None
        if isinstance(formals, Pair):
            params = []
            current = formals
            while isinstance(current, Pair):
                p = current.car
                if not isinstance(p, Symbol):
                    raise SchemeError("bad formals")
                params.append(p)
                current = current.cdr
            if current is NIL:
                return params, None
            elif isinstance(current, Symbol):
                return params, current
            else:
                raise SchemeError("bad formals")
        raise SchemeError("bad formals")

    # ---- Special forms ----

    def eval_special(self, name, args, env):
        if name == 'quote':
            return self._eval_quote(args)
        elif name == 'if':
            return self._eval_if(args, env)
        elif name == 'define':
            return self._eval_define(args, env)
        elif name == 'set!':
            return self._eval_set(args, env)
        elif name == 'begin':
            return self._eval_begin(args, env)
        elif name == 'cond':
            return self._eval_cond(args, env)
        elif name == 'and':
            return self._eval_and(args, env)
        elif name == 'or':
            return self._eval_or(args, env)
        elif name == 'let':
            return self._eval_let(args, env)
        elif name == 'let*':
            return self._eval_let_star(args, env)
        elif name == 'letrec':
            return self._eval_letrec(args, env)
        elif name == 'apply':
            return self._eval_apply(args, env)
        raise SchemeError(f"unknown special form: {name}")

    def _eval_quote(self, args):
        if args is NIL or not isinstance(args, Pair):
            raise SchemeError("malformed quote")
        if args.cdr is not NIL:
            raise SchemeError("malformed quote")
        return args.car

    def _eval_if(self, args, env):
        if args is NIL or not isinstance(args, Pair):
            raise SchemeError("malformed if")
        test = self.resolve(self.eval_expr(args.car, env))
        if args.cdr is NIL or not isinstance(args.cdr, Pair):
            raise SchemeError("malformed if")
        then_expr = args.cdr.car
        rest = args.cdr.cdr
        if is_true(test):
            return self.eval_expr(then_expr, env)
        else:
            if rest is NIL:
                return UNSPECIFIED
            if not isinstance(rest, Pair):
                raise SchemeError("malformed if")
            return self.eval_expr(rest.car, env)

    def _eval_define(self, args, env):
        if args is NIL or not isinstance(args, Pair):
            raise SchemeError("malformed define")
        target = args.car
        if isinstance(target, Symbol):
            if args.cdr is NIL or not isinstance(args.cdr, Pair):
                raise SchemeError("malformed define")
            val = self.resolve(self.eval_expr(args.cdr.car, env))
            env.frame[target] = val
            return UNSPECIFIED
        elif isinstance(target, Pair):
            name = target.car
            if not isinstance(name, Symbol):
                raise SchemeError("malformed define")
            formals = target.cdr
            body = self._to_list(args.cdr)
            if not body:
                raise SchemeError("empty body in define")
            params, rest_param = self._parse_formals(formals)
            closure = Closure(params, rest_param, body, env)
            env.frame[name] = closure
            return UNSPECIFIED
        else:
            raise SchemeError("malformed define")

    def _eval_set(self, args, env):
        if args is NIL or not isinstance(args, Pair):
            raise SchemeError("malformed set!")
        name = args.car
        if not isinstance(name, Symbol):
            raise SchemeError("set! requires a symbol")
        if args.cdr is NIL or not isinstance(args.cdr, Pair):
            raise SchemeError("malformed set!")
        val = self.resolve(self.eval_expr(args.cdr.car, env))
        e = env
        while e is not None:
            if name in e.frame:
                e.frame[name] = val
                return UNSPECIFIED
            e = e.parent
        raise SchemeError(f"set!: unbound variable: {name.name}")

    def _eval_begin(self, args, env):
        forms = self._to_list(args)
        if not forms:
            raise SchemeError("empty begin")
        for form in forms[:-1]:
            self.resolve(self.eval_expr(form, env))
        return self.eval_expr(forms[-1], env)

    def _eval_cond(self, args, env):
        clauses = self._to_list(args)
        for i, clause in enumerate(clauses):
            if not isinstance(clause, Pair):
                raise SchemeError("malformed cond clause")
            test = clause.car
            body = self._to_list(clause.cdr)
            if isinstance(test, Symbol) and test.name == 'else':
                if i != len(clauses) - 1:
                    raise SchemeError("else must be last clause")
                if not body:
                    return UNSPECIFIED
                for form in body[:-1]:
                    self.resolve(self.eval_expr(form, env))
                return self.eval_expr(body[-1], env)
            else:
                val = self.resolve(self.eval_expr(test, env))
                if is_true(val):
                    if not body:
                        return val
                    for form in body[:-1]:
                        self.resolve(self.eval_expr(form, env))
                    return self.eval_expr(body[-1], env)
        return UNSPECIFIED

    def _eval_and(self, args, env):
        exprs = self._to_list(args)
        if not exprs:
            return True
        for i, expr in enumerate(exprs):
            if i == len(exprs) - 1:
                return self.eval_expr(expr, env)
            val = self.resolve(self.eval_expr(expr, env))
            if not is_true(val):
                return False
        return True

    def _eval_or(self, args, env):
        exprs = self._to_list(args)
        if not exprs:
            return False
        for i, expr in enumerate(exprs):
            if i == len(exprs) - 1:
                return self.eval_expr(expr, env)
            val = self.resolve(self.eval_expr(expr, env))
            if is_true(val):
                return val
        return False

    def _parse_let_bindings(self, bindings):
        result = []
        current = bindings
        while current is not NIL:
            if not isinstance(current, Pair):
                raise SchemeError("malformed let bindings")
            b = current.car
            if not isinstance(b, Pair):
                raise SchemeError("malformed let binding")
            var = b.car
            if not isinstance(var, Symbol):
                raise SchemeError("malformed let binding")
            rest = b.cdr
            if rest is NIL or not isinstance(rest, Pair):
                raise SchemeError("malformed let binding")
            init = rest.car
            if rest.cdr is not NIL:
                raise SchemeError("malformed let binding")
            result.append((var, init))
            current = current.cdr
        return result

    def _eval_let(self, args, env):
        if args is NIL or not isinstance(args, Pair):
            raise SchemeError("malformed let")
        first = args.car
        if isinstance(first, Symbol):
            name = first
            rest = args.cdr
            if rest is NIL or not isinstance(rest, Pair):
                raise SchemeError("malformed named let")
            bindings = rest.car
            body = self._to_list(rest.cdr)
            if not body:
                raise SchemeError("empty named let body")
            return self._eval_named_let(name, bindings, body, env)
        else:
            bindings = first
            body = self._to_list(args.cdr)
            if not body:
                raise SchemeError("empty let body")
            return self._eval_regular_let(bindings, body, env)

    def _eval_regular_let(self, bindings, body, env):
        binding_list = self._parse_let_bindings(bindings)
        init_values = []
        for var, init in binding_list:
            val = self.resolve(self.eval_expr(init, env))
            init_values.append((var, val))
        frame = {}
        for var, val in init_values:
            frame[var] = val
        internal_defs = self._scan_internal_defs(body)
        for name in internal_defs:
            if name not in frame:
                frame[name] = UNBOUND
        new_env = Env(frame, env)
        return self.eval_body(body, new_env)

    def _eval_let_star(self, args, env):
        if args is NIL or not isinstance(args, Pair):
            raise SchemeError("malformed let*")
        bindings = args.car
        body = self._to_list(args.cdr)
        if not body:
            raise SchemeError("empty let* body")
        binding_list = self._parse_let_bindings(bindings)
        frame = {}
        internal_defs = self._scan_internal_defs(body)
        for name in internal_defs:
            frame[name] = UNBOUND
        new_env = Env(frame, env)
        for var, init in binding_list:
            val = self.resolve(self.eval_expr(init, new_env))
            frame[var] = val
        return self.eval_body(body, new_env)

    def _eval_letrec(self, args, env):
        if args is NIL or not isinstance(args, Pair):
            raise SchemeError("malformed letrec")
        bindings = args.car
        body = self._to_list(args.cdr)
        if not body:
            raise SchemeError("empty letrec body")
        binding_list = self._parse_let_bindings(bindings)
        frame = {}
        for var, init in binding_list:
            frame[var] = UNBOUND
        internal_defs = self._scan_internal_defs(body)
        for name in internal_defs:
            if name not in frame:
                frame[name] = UNBOUND
        new_env = Env(frame, env)
        for var, init in binding_list:
            val = self.resolve(self.eval_expr(init, new_env))
            frame[var] = val
        return self.eval_body(body, new_env)

    def _eval_named_let(self, name, bindings, body, env):
        binding_list = self._parse_let_bindings(bindings)
        params = []
        init_values = []
        for var, init in binding_list:
            params.append(var)
            val = self.resolve(self.eval_expr(init, env))
            init_values.append(val)
        frame = {}
        frame[name] = UNBOUND
        new_env = Env(frame, env)
        closure = Closure(params, None, body, new_env)
        frame[name] = closure
        return TailCall(closure, init_values)

    def _eval_apply(self, args, env):
        arg_list = self._to_list(args)
        if len(arg_list) < 2:
            raise SchemeError("apply requires at least 2 arguments")
        proc = self.resolve(self.eval_expr(arg_list[0], env))
        individual = []
        for a in arg_list[1:-1]:
            individual.append(self.resolve(self.eval_expr(a, env)))
        last = self.resolve(self.eval_expr(arg_list[-1], env))
        expanded = []
        current = last
        while current is not NIL:
            if not isinstance(current, Pair):
                raise SchemeError("apply: last argument is not a proper list")
            expanded.append(current.car)
            current = current.cdr
        full_args = individual + expanded
        return TailCall(proc, full_args)

    # ---- Display / Write ----

    def display_value(self, x):
        if isinstance(x, bool):
            return '#t' if x else '#f'
        if isinstance(x, int):
            return str(x)
        if isinstance(x, str):
            return x
        if isinstance(x, Symbol):
            return x.name
        if x is NIL:
            return '()'
        if isinstance(x, Pair):
            return self._display_pair(x)
        if isinstance(x, (Closure, Builtin)):
            return '#<procedure>'
        if x is UNSPECIFIED:
            return ''
        return ''

    def _display_pair(self, p):
        elements = []
        current = p
        while isinstance(current, Pair):
            elements.append(self.display_value(current.car))
            current = current.cdr
        if current is NIL:
            return '(' + ' '.join(elements) + ')'
        else:
            return '(' + ' '.join(elements) + ' . ' + self.display_value(current) + ')'

    def write_value(self, x):
        if isinstance(x, str):
            escaped = x.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
            return '"' + escaped + '"'
        if isinstance(x, Pair):
            return self._write_pair(x)
        if isinstance(x, bool):
            return '#t' if x else '#f'
        if isinstance(x, int):
            return str(x)
        if isinstance(x, Symbol):
            return x.name
        if x is NIL:
            return '()'
        if isinstance(x, (Closure, Builtin)):
            return '#<procedure>'
        if x is UNSPECIFIED:
            return ''
        return ''

    def _write_pair(self, p):
        elements = []
        current = p
        while isinstance(current, Pair):
            elements.append(self.write_value(current.car))
            current = current.cdr
        if current is NIL:
            return '(' + ' '.join(elements) + ')'
        else:
            return '(' + ' '.join(elements) + ' . ' + self.write_value(current) + ')'

    # ---- Builtins setup ----

    def _setup_builtins(self):
        g = self.global_frame
        S = Symbol

        g[S('+')] = Builtin('+', self._bi_plus, 0, None)
        g[S('*')] = Builtin('*', self._bi_mult, 0, None)
        g[S('-')] = Builtin('-', self._bi_minus, 1, None)
        g[S('quotient')] = Builtin('quotient', self._bi_quotient, 2, 2)
        g[S('remainder')] = Builtin('remainder', self._bi_remainder, 2, 2)
        g[S('modulo')] = Builtin('modulo', self._bi_modulo, 2, 2)
        g[S('=')] = Builtin('=', self._bi_num_eq, 1, None)
        g[S('<')] = Builtin('<', self._bi_lt, 1, None)
        g[S('>')] = Builtin('>', self._bi_gt, 1, None)
        g[S('<=')] = Builtin('<=', self._bi_le, 1, None)
        g[S('>=')] = Builtin('>=', self._bi_ge, 1, None)
        g[S('number->string')] = Builtin('number->string', self._bi_num2str, 1, 2)

        g[S('cons')] = Builtin('cons', self._bi_cons, 2, 2)
        g[S('car')] = Builtin('car', self._bi_car, 1, 1)
        g[S('cdr')] = Builtin('cdr', self._bi_cdr, 1, 1)
        g[S('list')] = Builtin('list', self._bi_list, 0, None)
        g[S('null?')] = Builtin('null?', self._bi_null, 1, 1)
        g[S('pair?')] = Builtin('pair?', self._bi_pairp, 1, 1)
        g[S('list?')] = Builtin('list?', self._bi_listp, 1, 1)
        g[S('length')] = Builtin('length', self._bi_length, 1, 1)
        g[S('append')] = Builtin('append', self._bi_append, 0, None)
        g[S('reverse')] = Builtin('reverse', self._bi_reverse, 1, 1)
        g[S('apply')] = Builtin('apply', self._bi_apply, 2, None)

        g[S('eq?')] = Builtin('eq?', self._bi_eqq, 2, 2)
        g[S('equal?')] = Builtin('equal?', self._bi_equal, 2, 2)
        g[S('not')] = Builtin('not', self._bi_not, 1, 1)
        g[S('number?')] = Builtin('number?', self._bi_numberp, 1, 1)
        g[S('symbol?')] = Builtin('symbol?', self._bi_symbolp, 1, 1)
        g[S('string?')] = Builtin('string?', self._bi_stringp, 1, 1)
        g[S('procedure?')] = Builtin('procedure?', self._bi_procp, 1, 1)
        g[S('string-append')] = Builtin('string-append', self._bi_str_append, 0, None)

        g[S('display')] = Builtin('display', self._bi_display, 1, 1)
        g[S('newline')] = Builtin('newline', self._bi_newline, 0, 0)
        g[S('error')] = Builtin('error', self._bi_error, 1, None)

    # ---- Builtin implementations ----

    def _check_int(self, x):
        if isinstance(x, bool) or not isinstance(x, int):
            raise SchemeError("expected an integer")

    def _bi_plus(self, args):
        result = 0
        for a in args:
            self._check_int(a)
            result += a
        return result

    def _bi_mult(self, args):
        result = 1
        for a in args:
            self._check_int(a)
            result *= a
        return result

    def _bi_minus(self, args):
        for a in args:
            self._check_int(a)
        if len(args) == 1:
            return -args[0]
        result = args[0]
        for a in args[1:]:
            result -= a
        return result

    def _bi_quotient(self, args):
        a, b = args
        self._check_int(a)
        self._check_int(b)
        if b == 0:
            raise SchemeError("division by zero")
        q = abs(a) // abs(b)
        if (a < 0) != (b < 0):
            q = -q
        return q

    def _bi_remainder(self, args):
        a, b = args
        self._check_int(a)
        self._check_int(b)
        if b == 0:
            raise SchemeError("division by zero")
        r = abs(a) % abs(b)
        if a < 0:
            r = -r
        return r

    def _bi_modulo(self, args):
        a, b = args
        self._check_int(a)
        self._check_int(b)
        if b == 0:
            raise SchemeError("division by zero")
        return a % b

    def _bi_num_eq(self, args):
        for a in args:
            self._check_int(a)
        for i in range(len(args) - 1):
            if args[i] != args[i + 1]:
                return False
        return True

    def _bi_lt(self, args):
        for a in args:
            self._check_int(a)
        for i in range(len(args) - 1):
            if not (args[i] < args[i + 1]):
                return False
        return True

    def _bi_gt(self, args):
        for a in args:
            self._check_int(a)
        for i in range(len(args) - 1):
            if not (args[i] > args[i + 1]):
                return False
        return True

    def _bi_le(self, args):
        for a in args:
            self._check_int(a)
        for i in range(len(args) - 1):
            if not (args[i] <= args[i + 1]):
                return False
        return True

    def _bi_ge(self, args):
        for a in args:
            self._check_int(a)
        for i in range(len(args) - 1):
            if not (args[i] >= args[i + 1]):
                return False
        return True

    def _bi_num2str(self, args):
        n = args[0]
        self._check_int(n)
        radix = 10
        if len(args) > 1:
            radix = args[1]
            self._check_int(radix)
            if radix not in (2, 8, 10, 16):
                raise SchemeError("number->string: invalid radix")
        if n == 0:
            return "0"
        negative = n < 0
        n = abs(n)
        digits = '0123456789abcdef'
        parts = []
        while n > 0:
            parts.append(digits[n % radix])
            n //= radix
        parts.reverse()
        s = ''.join(parts)
        if negative:
            s = '-' + s
        return s

    def _bi_cons(self, args):
        return Pair(args[0], args[1])

    def _bi_car(self, args):
        p = args[0]
        if not isinstance(p, Pair):
            raise SchemeError("car: not a pair")
        return p.car

    def _bi_cdr(self, args):
        p = args[0]
        if not isinstance(p, Pair):
            raise SchemeError("cdr: not a pair")
        return p.cdr

    def _bi_list(self, args):
        result = NIL
        for a in reversed(args):
            result = Pair(a, result)
        return result

    def _bi_null(self, args):
        return args[0] is NIL

    def _bi_pairp(self, args):
        return isinstance(args[0], Pair)

    def _bi_listp(self, args):
        current = args[0]
        while isinstance(current, Pair):
            current = current.cdr
        return current is NIL

    def _bi_length(self, args):
        current = args[0]
        count = 0
        while current is not NIL:
            if not isinstance(current, Pair):
                raise SchemeError("length: not a proper list")
            count += 1
            current = current.cdr
        return count

    def _bi_append(self, args):
        if not args:
            return NIL
        result = args[-1]
        for i in range(len(args) - 2, -1, -1):
            lst = args[i]
            elements = []
            current = lst
            while current is not NIL:
                if not isinstance(current, Pair):
                    raise SchemeError("append: not a proper list")
                elements.append(current.car)
                current = current.cdr
            for e in reversed(elements):
                result = Pair(e, result)
        return result

    def _bi_reverse(self, args):
        current = args[0]
        result = NIL
        while current is not NIL:
            if not isinstance(current, Pair):
                raise SchemeError("reverse: not a proper list")
            result = Pair(current.car, result)
            current = current.cdr
        return result

    def _bi_apply(self, args):
        proc = args[0]
        individual = args[1:-1]
        last = args[-1]
        expanded = []
        current = last
        while current is not NIL:
            if not isinstance(current, Pair):
                raise SchemeError("apply: last argument is not a proper list")
            expanded.append(current.car)
            current = current.cdr
        full_args = individual + expanded
        return self.resolve(self.apply_proc(proc, full_args))

    def _bi_eqq(self, args):
        a, b = args
        if isinstance(a, bool) and isinstance(b, bool):
            return a is b
        if isinstance(a, bool) or isinstance(b, bool):
            return False
        if isinstance(a, int) and isinstance(b, int):
            return a == b
        if isinstance(a, int) or isinstance(b, int):
            return False
        if isinstance(a, Symbol) and isinstance(b, Symbol):
            return a is b
        if a is NIL and b is NIL:
            return True
        return a is b

    def _bi_equal(self, args):
        return self._scheme_equal(args[0], args[1])

    def _scheme_equal(self, a, b):
        stack = [(a, b)]
        while stack:
            a, b = stack.pop()
            if a is b:
                continue
            if isinstance(a, bool) or isinstance(b, bool):
                return False
            if isinstance(a, int) and isinstance(b, int):
                if a != b:
                    return False
                continue
            if isinstance(a, int) or isinstance(b, int):
                return False
            if isinstance(a, str) and isinstance(b, str):
                if a != b:
                    return False
                continue
            if isinstance(a, str) or isinstance(b, str):
                return False
            if isinstance(a, Symbol) and isinstance(b, Symbol):
                if a.name != b.name:
                    return False
                continue
            if isinstance(a, Symbol) or isinstance(b, Symbol):
                return False
            if a is NIL and b is NIL:
                continue
            if a is NIL or b is NIL:
                return False
            if isinstance(a, Pair) and isinstance(b, Pair):
                stack.append((a.car, b.car))
                stack.append((a.cdr, b.cdr))
                continue
            if isinstance(a, (Closure, Builtin)) and isinstance(b, (Closure, Builtin)):
                if a is not b:
                    return False
                continue
            if a is UNSPECIFIED and b is UNSPECIFIED:
                continue
            return False
        return True

    def _bi_not(self, args):
        return args[0] is False

    def _bi_numberp(self, args):
        return isinstance(args[0], int) and not isinstance(args[0], bool)

    def _bi_symbolp(self, args):
        return isinstance(args[0], Symbol)

    def _bi_stringp(self, args):
        return isinstance(args[0], str)

    def _bi_procp(self, args):
        return isinstance(args[0], (Closure, Builtin))

    def _bi_str_append(self, args):
        for s in args:
            if not isinstance(s, str):
                raise SchemeError("string-append requires strings")
        return ''.join(args)

    def _bi_display(self, args):
        self.output.append(self.display_value(args[0]))
        return UNSPECIFIED

    def _bi_newline(self, args):
        self.output.append('\n')
        return UNSPECIFIED

    def _bi_error(self, args):
        msg = args[0]
        if not isinstance(msg, str):
            raise SchemeError("error: first argument must be a string")
        parts = [msg]
        for irritant in args[1:]:
            parts.append(' ')
            parts.append(self.write_value(irritant))
        raise SchemeError(''.join(parts))


# ============ PUBLIC API ============

def run(source):
    try:
        forms = read_all(source)
    except SchemeError:
        raise
    except Exception as e:
        raise SchemeError(str(e))

    interp = Interpreter()
    try:
        for form in forms:
            result = interp.eval_expr(form, interp.global_env)
            interp.resolve(result)
    except SchemeError as e:
        e.output = interp.get_output()
        raise
    except Exception as e:
        raise SchemeError(str(e), interp.get_output())

    return interp.get_output()
