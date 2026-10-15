import sys
import re
import threading

if hasattr(sys, 'set_int_max_str_digits'):
    sys.set_int_max_str_digits(0)


class SchemeError(Exception):
    def __init__(self, message, output=''):
        super().__init__(message)
        self.output = output


# ─── Data Types ───────────────────────────────────────────────────────────────

class Symbol:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name

class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr

class _EmptyList:
    pass
EMPTY = _EmptyList()

class _Unspecified:
    pass
UNSPEC = _Unspecified()

class _Unbound:
    pass
UNBOUND = _Unbound()

class Builtin:
    __slots__ = ('name', 'func', 'min_args', 'max_args')
    def __init__(self, name, func, min_args=0, max_args=None):
        self.name = name
        self.func = func
        self.min_args = min_args
        self.max_args = max_args

class Closure:
    __slots__ = ('formals', 'body', 'env')
    def __init__(self, formals, body, env):
        self.formals = formals
        self.body = body
        self.env = env


# ─── Environment ──────────────────────────────────────────────────────────────

class Frame:
    __slots__ = ('vars',)
    def __init__(self):
        self.vars = {}

class Env:
    __slots__ = ('frame', 'parent')
    def __init__(self, frame, parent):
        self.frame = frame
        self.parent = parent


# ─── Reader ───────────────────────────────────────────────────────────────────

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
        if c == '(':
            tokens.append(('(', '('))
            i += 1
            continue
        if c == ')':
            tokens.append((')', ')'))
            i += 1
            continue
        if c == "'":
            tokens.append(("'", "'"))
            i += 1
            continue
        if c == '"':
            i += 1
            chars = []
            while i < n and source[i] != '"':
                if source[i] == '\\':
                    i += 1
                    if i >= n:
                        raise SchemeError("unterminated string")
                    if source[i] == '"':
                        chars.append('"')
                    elif source[i] == '\\':
                        chars.append('\\')
                    elif source[i] == 'n':
                        chars.append('\n')
                    else:
                        raise SchemeError("invalid escape")
                    i += 1
                else:
                    chars.append(source[i])
                    i += 1
            if i >= n:
                raise SchemeError("unterminated string")
            i += 1
            tokens.append(('string', ''.join(chars)))
            continue
        start = i
        while i < n and source[i] not in ' \t\n\r()";\'':
            i += 1
        tok = source[start:i]
        if tok == '#t':
            tokens.append(('bool', True))
        elif tok == '#f':
            tokens.append(('bool', False))
        elif tok.startswith('#'):
            raise SchemeError("invalid token: " + tok)
        elif tok == '.':
            tokens.append(('dot', '.'))
        elif _INT_RE.match(tok):
            tokens.append(('int', int(tok)))
        else:
            tokens.append(('symbol', tok))
    return tokens


def parse_all(tokens):
    pos = [0]

    def peek():
        return tokens[pos[0]] if pos[0] < len(tokens) else None

    def consume():
        t = tokens[pos[0]]
        pos[0] += 1
        return t

    def parse_datum():
        t = peek()
        if t is None:
            raise SchemeError("unexpected end of input")
        if t[0] == '(':
            consume()
            return parse_list()
        if t[0] == "'":
            consume()
            datum = parse_datum()
            return Pair(Symbol('quote'), Pair(datum, EMPTY))
        if t[0] == ')':
            raise SchemeError("unexpected )")
        if t[0] == 'dot':
            raise SchemeError("unexpected .")
        consume()
        if t[0] == 'string':
            return t[1]
        if t[0] == 'int':
            return t[1]
        if t[0] == 'bool':
            return t[1]
        if t[0] == 'symbol':
            return Symbol(t[1])
        raise SchemeError("unexpected token")

    def parse_list():
        elements = []
        while True:
            t = peek()
            if t is None:
                raise SchemeError("unbalanced (")
            if t[0] == ')':
                consume()
                result = EMPTY
                for e in reversed(elements):
                    result = Pair(e, result)
                return result
            if t[0] == 'dot':
                consume()
                if not elements:
                    raise SchemeError("dot with no preceding element")
                cdr = parse_datum()
                t2 = peek()
                if t2 is None or t2[0] != ')':
                    raise SchemeError("expected ) after dotted cdr")
                consume()
                result = cdr
                for e in reversed(elements):
                    result = Pair(e, result)
                return result
            elements.append(parse_datum())

    forms = []
    while pos[0] < len(tokens):
        forms.append(parse_datum())
    return forms


# ─── Interpreter ──────────────────────────────────────────────────────────────

def _is_number(x):
    return isinstance(x, int) and not isinstance(x, bool)


class Interpreter:
    def __init__(self):
        self.output = []
        self.global_frame = Frame()
        self.global_env = Env(self.global_frame, None)
        self._setup_builtins()

    # ── helpers ──

    def _to_list(self, x):
        result = []
        while isinstance(x, Pair):
            result.append(x.car)
            x = x.cdr
        if x is not EMPTY:
            raise SchemeError("improper list")
        return result

    def _list_to_pair(self, lst):
        result = EMPTY
        for item in reversed(lst):
            result = Pair(item, result)
        return result

    def _is_proper_list(self, x):
        while isinstance(x, Pair):
            x = x.cdr
        return x is EMPTY

    def _lookup(self, sym, env):
        name = sym.name
        cur = env
        while cur is not None:
            if name in cur.frame.vars:
                val = cur.frame.vars[name]
                if isinstance(val, _Unbound):
                    raise SchemeError("unbound variable: " + name)
                return val
            cur = cur.parent
        raise SchemeError("unbound variable: " + name)

    def _set_var(self, sym, val, env):
        name = sym.name
        cur = env
        while cur is not None:
            if name in cur.frame.vars:
                cur.frame.vars[name] = val
                return
            cur = cur.parent
        raise SchemeError("unbound variable: " + name)

    def _bind_params(self, formals, args, env):
        frame = Frame()
        if isinstance(formals, Symbol):
            frame.vars[formals.name] = self._list_to_pair(args)
        elif formals is EMPTY:
            if args:
                raise SchemeError("too many arguments")
        elif isinstance(formals, Pair):
            cur = formals
            i = 0
            while isinstance(cur, Pair):
                if i >= len(args):
                    raise SchemeError("too few arguments")
                if not isinstance(cur.car, Symbol):
                    raise SchemeError("invalid parameter")
                frame.vars[cur.car.name] = args[i]
                i += 1
                cur = cur.cdr
            if isinstance(cur, Symbol):
                frame.vars[cur.name] = self._list_to_pair(args[i:])
            elif cur is EMPTY:
                if i != len(args):
                    raise SchemeError("too many arguments")
            else:
                raise SchemeError("invalid formals")
        else:
            raise SchemeError("invalid formals")
        return Env(frame, env)

    # ── display / write ──

    def _display_value(self, x):
        if isinstance(x, bool):
            return '#t' if x else '#f'
        if isinstance(x, int):
            return str(x)
        if isinstance(x, str):
            return x
        if isinstance(x, Symbol):
            return x.name
        if x is EMPTY:
            return '()'
        if isinstance(x, Pair):
            return self._format_pair(x, False)
        if isinstance(x, (Builtin, Closure)):
            return '#<procedure>'
        if isinstance(x, _Unspecified):
            return ''
        return ''

    def _write_value(self, x):
        if isinstance(x, str):
            s = x.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
            return '"' + s + '"'
        if isinstance(x, Pair):
            return self._format_pair(x, True)
        if isinstance(x, (Builtin, Closure)):
            return '#<procedure>'
        return self._display_value(x)

    def _format_pair(self, p, write_mode):
        elements = []
        cur = p
        while isinstance(cur, Pair):
            if write_mode:
                elements.append(self._write_value(cur.car))
            else:
                elements.append(self._display_value(cur.car))
            cur = cur.cdr
        if cur is EMPTY:
            return '(' + ' '.join(elements) + ')'
        tail = self._write_value(cur) if write_mode else self._display_value(cur)
        return '(' + ' '.join(elements) + ' . ' + tail + ')'

    # ── equal? ──

    def _equal_values(self, a, b):
        stack = [(a, b)]
        while stack:
            a, b = stack.pop()
            if a is b:
                continue
            if isinstance(a, bool) and isinstance(b, bool):
                if a is not b:
                    return False
                continue
            if isinstance(a, bool) or isinstance(b, bool):
                return False
            if _is_number(a) and _is_number(b):
                if a != b:
                    return False
                continue
            if isinstance(a, Symbol) and isinstance(b, Symbol):
                if a.name != b.name:
                    return False
                continue
            if isinstance(a, str) and isinstance(b, str):
                if a != b:
                    return False
                continue
            if a is EMPTY and b is EMPTY:
                continue
            if isinstance(a, Pair) and isinstance(b, Pair):
                stack.append((a.cdr, b.cdr))
                stack.append((a.car, b.car))
                continue
            return False
        return True

    # ── body processing ──

    def _extract_define_name(self, form):
        target = form.cdr.car
        if isinstance(target, Symbol):
            return target.name
        if isinstance(target, Pair) and isinstance(target.car, Symbol):
            return target.car.name
        raise SchemeError("define: invalid target")

    def _transform_internal_define(self, form):
        if not (isinstance(form, Pair) and isinstance(form.car, Symbol) and form.car.name == 'define'):
            return form
        target = form.cdr.car
        if isinstance(target, Symbol):
            expr = form.cdr.cdr.car if isinstance(form.cdr.cdr, Pair) else EMPTY
            return Pair(Symbol('set!'), Pair(target, Pair(expr, EMPTY)))
        if isinstance(target, Pair) and isinstance(target.car, Symbol):
            name = target.car
            formals = target.cdr
            body = form.cdr.cdr
            lambda_form = Pair(Symbol('lambda'), Pair(formals, body))
            return Pair(Symbol('set!'), Pair(name, Pair(lambda_form, EMPTY)))
        raise SchemeError("define: invalid target")

    def _process_body(self, body, env):
        if not body:
            raise SchemeError("empty body")
        internal_names = []
        for form in body:
            if isinstance(form, Pair) and isinstance(form.car, Symbol) and form.car.name == 'define':
                internal_names.append(self._extract_define_name(form))
        if internal_names:
            new_frame = Frame()
            for nm in internal_names:
                new_frame.vars[nm] = UNBOUND
            env = Env(new_frame, env)
        for i in range(len(body) - 1):
            actual = self._transform_internal_define(body[i]) if internal_names else body[i]
            self.eval_expr(actual, env)
        last = self._transform_internal_define(body[-1]) if internal_names else body[-1]
        return last, env

    # ── core evaluator (trampoline for tail calls) ──

    def eval_expr(self, expr, env):
        while True:
            if isinstance(expr, bool):
                return expr
            if isinstance(expr, int):
                return expr
            if isinstance(expr, str):
                return expr
            if isinstance(expr, Symbol):
                return self._lookup(expr, env)
            if expr is EMPTY:
                raise SchemeError("cannot evaluate ()")
            if not isinstance(expr, Pair):
                raise SchemeError("cannot evaluate")

            head = expr.car

            if isinstance(head, Symbol):
                hname = head.name

                if hname == 'quote':
                    if not isinstance(expr.cdr, Pair) or expr.cdr.cdr is not EMPTY:
                        raise SchemeError("quote: wrong form")
                    return expr.cdr.car

                if hname == 'if':
                    args = self._to_list(expr.cdr)
                    if len(args) < 2 or len(args) > 3:
                        raise SchemeError("if: wrong form")
                    tv = self.eval_expr(args[0], env)
                    if tv is not False:
                        expr = args[1]
                    elif len(args) == 3:
                        expr = args[2]
                    else:
                        return UNSPEC
                    continue

                if hname == 'lambda':
                    if not isinstance(expr.cdr, Pair):
                        raise SchemeError("lambda: wrong form")
                    formals = expr.cdr.car
                    body = self._to_list(expr.cdr.cdr)
                    if not body:
                        raise SchemeError("lambda: empty body")
                    return Closure(formals, body, env)

                if hname == 'define':
                    if expr.cdr is EMPTY or not isinstance(expr.cdr, Pair):
                        raise SchemeError("define: wrong form")
                    target = expr.cdr.car
                    if isinstance(target, Symbol):
                        if expr.cdr.cdr is EMPTY:
                            raise SchemeError("define: missing expression")
                        val = self.eval_expr(expr.cdr.cdr.car, env)
                        self.global_frame.vars[target.name] = val
                    elif isinstance(target, Pair) and isinstance(target.car, Symbol):
                        nm = target.car
                        formals = target.cdr
                        body = self._to_list(expr.cdr.cdr)
                        if not body:
                            raise SchemeError("define: empty body")
                        self.global_frame.vars[nm.name] = Closure(formals, body, env)
                    else:
                        raise SchemeError("define: invalid target")
                    return UNSPEC

                if hname == 'set!':
                    args = self._to_list(expr.cdr)
                    if len(args) != 2 or not isinstance(args[0], Symbol):
                        raise SchemeError("set!: wrong form")
                    val = self.eval_expr(args[1], env)
                    self._set_var(args[0], val, env)
                    return UNSPEC

                if hname == 'begin':
                    forms = self._to_list(expr.cdr)
                    if not forms:
                        raise SchemeError("begin: empty")
                    for f in forms[:-1]:
                        self.eval_expr(f, env)
                    expr = forms[-1]
                    continue

                if hname == 'cond':
                    clauses = self._to_list(expr.cdr)
                    matched = False
                    for clause in clauses:
                        if not isinstance(clause, Pair):
                            raise SchemeError("cond: malformed clause")
                        test = clause.car
                        if isinstance(test, Symbol) and test.name == 'else':
                            body_forms = self._to_list(clause.cdr)
                            if not body_forms:
                                return UNSPEC
                            for f in body_forms[:-1]:
                                self.eval_expr(f, env)
                            expr = body_forms[-1]
                            matched = True
                            break
                        else:
                            tv = self.eval_expr(test, env)
                            if tv is not False:
                                body_forms = self._to_list(clause.cdr)
                                if not body_forms:
                                    return tv
                                for f in body_forms[:-1]:
                                    self.eval_expr(f, env)
                                expr = body_forms[-1]
                                matched = True
                                break
                    if not matched:
                        return UNSPEC
                    continue

                if hname == 'and':
                    forms = self._to_list(expr.cdr)
                    if not forms:
                        return True
                    for f in forms[:-1]:
                        v = self.eval_expr(f, env)
                        if v is False:
                            return False
                    expr = forms[-1]
                    continue

                if hname == 'or':
                    forms = self._to_list(expr.cdr)
                    if not forms:
                        return False
                    for f in forms[:-1]:
                        v = self.eval_expr(f, env)
                        if v is not False:
                            return v
                    expr = forms[-1]
                    continue

                if hname == 'let':
                    rest = expr.cdr
                    if not isinstance(rest, Pair):
                        raise SchemeError("let: wrong form")
                    if isinstance(rest.car, Symbol):
                        # named let
                        name_sym = rest.car
                        bindings = self._to_list(rest.cdr.car)
                        body = self._to_list(rest.cdr.cdr)
                        if not body:
                            raise SchemeError("let: empty body")
                        init_vals = []
                        for b in bindings:
                            if not isinstance(b, Pair) or not isinstance(b.car, Symbol):
                                raise SchemeError("let: malformed binding")
                            if b.cdr is EMPTY or not isinstance(b.cdr, Pair):
                                raise SchemeError("let: malformed binding")
                            init_vals.append(self.eval_expr(b.cdr.car, env))
                        formals = self._list_to_pair([b.car for b in bindings])
                        frame = Frame()
                        frame.vars[name_sym.name] = UNBOUND
                        let_env = Env(frame, env)
                        closure = Closure(formals, body, let_env)
                        frame.vars[name_sym.name] = closure
                        new_env = self._bind_params(formals, init_vals, let_env)
                        expr, env = self._process_body(body, new_env)
                        continue
                    else:
                        # regular let
                        bindings = self._to_list(rest.car)
                        body = self._to_list(rest.cdr)
                        if not body:
                            raise SchemeError("let: empty body")
                        init_vals = []
                        names = []
                        for b in bindings:
                            if not isinstance(b, Pair) or not isinstance(b.car, Symbol):
                                raise SchemeError("let: malformed binding")
                            if b.cdr is EMPTY or not isinstance(b.cdr, Pair) or b.cdr.cdr is not EMPTY:
                                raise SchemeError("let: malformed binding")
                            names.append(b.car.name)
                            init_vals.append(self.eval_expr(b.cdr.car, env))
                        frame = Frame()
                        for i, nm in enumerate(names):
                            frame.vars[nm] = init_vals[i]
                        new_env = Env(frame, env)
                        expr, env = self._process_body(body, new_env)
                        continue

                if hname == 'let*':
                    bindings = self._to_list(expr.cdr.car)
                    body = self._to_list(expr.cdr.cdr)
                    if not body:
                        raise SchemeError("let*: empty body")
                    cur_env = env
                    for b in bindings:
                        if not isinstance(b, Pair) or not isinstance(b.car, Symbol):
                            raise SchemeError("let*: malformed binding")
                        if b.cdr is EMPTY or not isinstance(b.cdr, Pair) or b.cdr.cdr is not EMPTY:
                            raise SchemeError("let*: malformed binding")
                        val = self.eval_expr(b.cdr.car, cur_env)
                        frame = Frame()
                        frame.vars[b.car.name] = val
                        cur_env = Env(frame, cur_env)
                    expr, env = self._process_body(body, cur_env)
                    continue

                if hname == 'letrec':
                    bindings = self._to_list(expr.cdr.car)
                    body = self._to_list(expr.cdr.cdr)
                    if not body:
                        raise SchemeError("letrec: empty body")
                    frame = Frame()
                    for b in bindings:
                        if not isinstance(b, Pair) or not isinstance(b.car, Symbol):
                            raise SchemeError("letrec: malformed binding")
                        frame.vars[b.car.name] = UNBOUND
                    new_env = Env(frame, env)
                    for b in bindings:
                        if b.cdr is EMPTY or not isinstance(b.cdr, Pair) or b.cdr.cdr is not EMPTY:
                            raise SchemeError("letrec: malformed binding")
                        val = self.eval_expr(b.cdr.car, new_env)
                        frame.vars[b.car.name] = val
                    expr, env = self._process_body(body, new_env)
                    continue

                if hname == 'apply':
                    forms = self._to_list(expr.cdr)
                    if len(forms) < 2:
                        raise SchemeError("apply: too few arguments")
                    proc = self.eval_expr(forms[0], env)
                    middle = []
                    for f in forms[1:-1]:
                        middle.append(self.eval_expr(f, env))
                    lst = self.eval_expr(forms[-1], env)
                    final_args = list(middle)
                    cur = lst
                    while isinstance(cur, Pair):
                        final_args.append(cur.car)
                        cur = cur.cdr
                    if cur is not EMPTY:
                        raise SchemeError("apply: not a proper list")
                    if isinstance(proc, Closure):
                        new_env = self._bind_params(proc.formals, final_args, proc.env)
                        expr, env = self._process_body(proc.body, new_env)
                        continue
                    elif isinstance(proc, Builtin):
                        return self._call_builtin(proc, final_args)
                    else:
                        raise SchemeError("not a procedure")

            # ── regular application ──
            proc = self.eval_expr(head, env)
            args = []
            cur = expr.cdr
            while cur is not EMPTY:
                if not isinstance(cur, Pair):
                    raise SchemeError("improper form in application")
                args.append(self.eval_expr(cur.car, env))
                cur = cur.cdr
            if isinstance(proc, Closure):
                new_env = self._bind_params(proc.formals, args, proc.env)
                expr, env = self._process_body(proc.body, new_env)
                continue
            elif isinstance(proc, Builtin):
                return self._call_builtin(proc, args)
            else:
                raise SchemeError("not a procedure")

    # ── call builtin ──

    def _call_builtin(self, b, args):
        if len(args) < b.min_args:
            raise SchemeError(b.name + ": too few arguments")
        if b.max_args is not None and len(args) > b.max_args:
            raise SchemeError(b.name + ": too many arguments")
        return b.func(self, args)

    # ── builtins ──

    def _setup_builtins(self):
        g = self.global_frame.vars
        g['+'] = Builtin('+', self._b_add, 0)
        g['*'] = Builtin('*', self._b_mul, 0)
        g['-'] = Builtin('-', self._b_sub, 1)
        g['quotient'] = Builtin('quotient', self._b_quotient, 2, 2)
        g['remainder'] = Builtin('remainder', self._b_remainder, 2, 2)
        g['modulo'] = Builtin('modulo', self._b_modulo, 2, 2)
        g['='] = Builtin('=', self._b_eq_num, 1)
        g['<'] = Builtin('<', self._b_lt, 1)
        g['>'] = Builtin('>', self._b_gt, 1)
        g['<='] = Builtin('<=', self._b_le, 1)
        g['>='] = Builtin('>=', self._b_ge, 1)
        g['number->string'] = Builtin('number->string', self._b_num_str, 1, 2)
        g['cons'] = Builtin('cons', self._b_cons, 2, 2)
        g['car'] = Builtin('car', self._b_car, 1, 1)
        g['cdr'] = Builtin('cdr', self._b_cdr, 1, 1)
        g['list'] = Builtin('list', self._b_list, 0)
        g['null?'] = Builtin('null?', self._b_null, 1, 1)
        g['pair?'] = Builtin('pair?', self._b_pair, 1, 1)
        g['list?'] = Builtin('list?', self._b_list_q, 1, 1)
        g['length'] = Builtin('length', self._b_length, 1, 1)
        g['append'] = Builtin('append', self._b_append, 0)
        g['reverse'] = Builtin('reverse', self._b_reverse, 1, 1)
        g['apply'] = Builtin('apply', self._b_apply, 2)
        g['eq?'] = Builtin('eq?', self._b_eq, 2, 2)
        g['equal?'] = Builtin('equal?', self._b_equal, 2, 2)
        g['not'] = Builtin('not', self._b_not, 1, 1)
        g['number?'] = Builtin('number?', self._b_number_q, 1, 1)
        g['symbol?'] = Builtin('symbol?', self._b_symbol_q, 1, 1)
        g['string?'] = Builtin('string?', self._b_string_q, 1, 1)
        g['procedure?'] = Builtin('procedure?', self._b_proc_q, 1, 1)
        g['string-append'] = Builtin('string-append', self._b_str_append, 0)
        g['display'] = Builtin('display', self._b_display, 1, 1)
        g['newline'] = Builtin('newline', self._b_newline, 0, 0)
        g['error'] = Builtin('error', self._b_error, 1)

    def _b_add(self, args):
        r = 0
        for a in args:
            if not _is_number(a):
                raise SchemeError("+: not a number")
            r += a
        return r

    def _b_mul(self, args):
        r = 1
        for a in args:
            if not _is_number(a):
                raise SchemeError("*: not a number")
            r *= a
        return r

    def _b_sub(self, args):
        for a in args:
            if not _is_number(a):
                raise SchemeError("-: not a number")
        if len(args) == 1:
            return -args[0]
        r = args[0]
        for a in args[1:]:
            r -= a
        return r

    def _b_quotient(self, args):
        a, b = args
        if not _is_number(a) or not _is_number(b):
            raise SchemeError("quotient: not a number")
        if b == 0:
            raise SchemeError("quotient: division by zero")
        q = abs(a) // abs(b)
        if (a < 0) != (b < 0):
            q = -q
        return q

    def _b_remainder(self, args):
        a, b = args
        if not _is_number(a) or not _is_number(b):
            raise SchemeError("remainder: not a number")
        if b == 0:
            raise SchemeError("remainder: division by zero")
        q = abs(a) // abs(b)
        if (a < 0) != (b < 0):
            q = -q
        return a - q * b

    def _b_modulo(self, args):
        a, b = args
        if not _is_number(a) or not _is_number(b):
            raise SchemeError("modulo: not a number")
        if b == 0:
            raise SchemeError("modulo: division by zero")
        q = abs(a) // abs(b)
        if (a < 0) != (b < 0):
            q = -q
        r = a - q * b
        if r != 0 and (r < 0) != (b < 0):
            r += b
        return r

    def _b_eq_num(self, args):
        for a in args:
            if not _is_number(a):
                raise SchemeError("=: not a number")
        for i in range(len(args) - 1):
            if args[i] != args[i + 1]:
                return False
        return True

    def _b_lt(self, args):
        for a in args:
            if not _is_number(a):
                raise SchemeError("<: not a number")
        for i in range(len(args) - 1):
            if not (args[i] < args[i + 1]):
                return False
        return True

    def _b_gt(self, args):
        for a in args:
            if not _is_number(a):
                raise SchemeError(">: not a number")
        for i in range(len(args) - 1):
            if not (args[i] > args[i + 1]):
                return False
        return True

    def _b_le(self, args):
        for a in args:
            if not _is_number(a):
                raise SchemeError("<=: not a number")
        for i in range(len(args) - 1):
            if not (args[i] <= args[i + 1]):
                return False
        return True

    def _b_ge(self, args):
        for a in args:
            if not _is_number(a):
                raise SchemeError(">=: not a number")
        for i in range(len(args) - 1):
            if not (args[i] >= args[i + 1]):
                return False
        return True

    def _b_num_str(self, args):
        n = args[0]
        if not _is_number(n):
            raise SchemeError("number->string: not a number")
        if len(args) == 1:
            return str(n)
        radix = args[1]
        if not _is_number(radix):
            raise SchemeError("number->string: radix not a number")
        if radix not in (2, 8, 10, 16):
            raise SchemeError("number->string: invalid radix")
        if radix == 10:
            return str(n)
        neg = n < 0
        n = abs(n)
        if n == 0:
            return '0'
        digits = '0123456789abcdef'
        parts = []
        while n > 0:
            parts.append(digits[n % radix])
            n //= radix
        s = ''.join(reversed(parts))
        return ('-' + s) if neg else s

    def _b_cons(self, args):
        return Pair(args[0], args[1])

    def _b_car(self, args):
        p = args[0]
        if not isinstance(p, Pair):
            raise SchemeError("car: not a pair")
        return p.car

    def _b_cdr(self, args):
        p = args[0]
        if not isinstance(p, Pair):
            raise SchemeError("cdr: not a pair")
        return p.cdr

    def _b_list(self, args):
        return self._list_to_pair(args)

    def _b_null(self, args):
        return args[0] is EMPTY

    def _b_pair(self, args):
        return isinstance(args[0], Pair)

    def _b_list_q(self, args):
        return self._is_proper_list(args[0])

    def _b_length(self, args):
        x = args[0]
        n = 0
        while isinstance(x, Pair):
            n += 1
            x = x.cdr
        if x is not EMPTY:
            raise SchemeError("length: not a proper list")
        return n

    def _b_append(self, args):
        if not args:
            return EMPTY
        tail = args[-1]
        elements = []
        for i in range(len(args) - 1):
            x = args[i]
            while isinstance(x, Pair):
                elements.append(x.car)
                x = x.cdr
            if x is not EMPTY:
                raise SchemeError("append: not a proper list")
        result = tail
        for e in reversed(elements):
            result = Pair(e, result)
        return result

    def _b_reverse(self, args):
        x = args[0]
        result = EMPTY
        while isinstance(x, Pair):
            result = Pair(x.car, result)
            x = x.cdr
        if x is not EMPTY:
            raise SchemeError("reverse: not a proper list")
        return result

    def _b_apply(self, args):
        f = args[0]
        lst = args[-1]
        middle = list(args[1:-1])
        cur = lst
        while isinstance(cur, Pair):
            middle.append(cur.car)
            cur = cur.cdr
        if cur is not EMPTY:
            raise SchemeError("apply: not a proper list")
        if isinstance(f, Closure):
            new_env = self._bind_params(f.formals, middle, f.env)
            result = UNSPEC
            for form in f.body:
                result = self.eval_expr(form, new_env)
            return result
        elif isinstance(f, Builtin):
            return self._call_builtin(f, middle)
        else:
            raise SchemeError("apply: not a procedure")

    def _b_eq(self, args):
        a, b = args
        if isinstance(a, Symbol) and isinstance(b, Symbol):
            return a.name == b.name
        if _is_number(a) and _is_number(b):
            return a == b
        if isinstance(a, bool) and isinstance(b, bool):
            return a is b
        if a is EMPTY and b is EMPTY:
            return True
        return a is b

    def _b_equal(self, args):
        return self._equal_values(args[0], args[1])

    def _b_not(self, args):
        return args[0] is False

    def _b_number_q(self, args):
        return _is_number(args[0])

    def _b_symbol_q(self, args):
        return isinstance(args[0], Symbol)

    def _b_string_q(self, args):
        return isinstance(args[0], str)

    def _b_proc_q(self, args):
        return isinstance(args[0], (Builtin, Closure))

    def _b_str_append(self, args):
        for s in args:
            if not isinstance(s, str):
                raise SchemeError("string-append: not a string")
        return ''.join(args)

    def _b_display(self, args):
        self.output.append(self._display_value(args[0]))
        return UNSPEC

    def _b_newline(self, args):
        self.output.append('\n')
        return UNSPEC

    def _b_error(self, args):
        msg = args[0]
        if not isinstance(msg, str):
            raise SchemeError("error: message is not a string")
        parts = [msg]
        for irr in args[1:]:
            parts.append(' ')
            parts.append(self._write_value(irr))
        raise SchemeError(''.join(parts))


# ─── Public API ───────────────────────────────────────────────────────────────

def run(source: str) -> str:
    result = [None]
    error = [None]

    def _target():
        try:
            result[0] = _run_inner(source)
        except SchemeError as e:
            error[0] = e
        except RecursionError:
            error[0] = SchemeError("stack overflow")
        except Exception as e:
            error[0] = SchemeError(str(e))

    old_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(500000)
    try:
        try:
            threading.stack_size(256 * 1024 * 1024)
        except Exception:
            pass
        t = threading.Thread(target=_target)
        t.start()
        t.join()
    finally:
        sys.setrecursionlimit(old_limit)
        try:
            threading.stack_size(0)
        except Exception:
            pass

    if error[0] is not None:
        raise error[0]
    return result[0]


def _run_inner(source):
    interp = Interpreter()
    # Read everything first; syntax errors have output=''
    try:
        tokens = tokenize(source)
        forms = parse_all(tokens)
    except SchemeError as e:
        raise SchemeError(str(e), '')
    except Exception as e:
        raise SchemeError(str(e), '')

    # Evaluate top-level forms
    try:
        for form in forms:
            interp.eval_expr(form, interp.global_env)
    except SchemeError as e:
        e.output = ''.join(interp.output)
        raise
    except RecursionError:
        raise SchemeError("stack overflow", ''.join(interp.output))
    except Exception as e:
        raise SchemeError(str(e), ''.join(interp.output))

    return ''.join(interp.output)
