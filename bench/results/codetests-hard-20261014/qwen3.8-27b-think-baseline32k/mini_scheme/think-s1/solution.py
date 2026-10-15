import sys
import re

try:
    sys.set_int_max_str_digits(0)
except AttributeError:
    pass
sys.setrecursionlimit(500000)


# ==================== Data Types ====================

class SSymbol:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name

class SPair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr

class SProcedure:
    pass

class Builtin(SProcedure):
    __slots__ = ('name', 'func')
    def __init__(self, name, func):
        self.name = name
        self.func = func
    def call(self, args):
        return self.func(args)

class Closure(SProcedure):
    __slots__ = ('formals', 'body', 'env')
    def __init__(self, formals, body, env):
        self.formals = formals
        self.body = body
        self.env = env

class _SEmptyList:
    _inst = None
    def __new__(cls):
        if cls._inst is None:
            cls._inst = super().__new__(cls)
        return cls._inst

EMPTY = _SEmptyList()

class SBool:
    __slots__ = ('value',)
    def __init__(self, value):
        self.value = value

TRUE = SBool(True)
FALSE = SBool(False)

class _Unspecified:
    _inst = None
    def __new__(cls):
        if cls._inst is None:
            cls._inst = super().__new__(cls)
        return cls._inst

UNSPECIFIED = _Unspecified()
UNBOUND = object()


# ==================== Helpers ====================

def is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)

def is_bool(x):
    return isinstance(x, SBool)

def is_string(x):
    return isinstance(x, str)

def is_symbol(x):
    return isinstance(x, SSymbol)

def is_pair(x):
    return isinstance(x, SPair)

def is_empty(x):
    return x is EMPTY

def is_procedure(x):
    return isinstance(x, SProcedure)

def is_proper_list(x):
    if x is EMPTY:
        return True
    while isinstance(x, SPair):
        x = x.cdr
    return x is EMPTY

def to_list(x):
    result = []
    while x is not EMPTY:
        if not isinstance(x, SPair):
            raise SchemeError("not a proper list")
        result.append(x.car)
        x = x.cdr
    return result

def from_list(lst):
    result = EMPTY
    for item in reversed(lst):
        result = SPair(item, result)
    return result

def truthy(x):
    return x is not FALSE


# ==================== Error ====================

class SchemeError(Exception):
    def __init__(self, message, output=''):
        super().__init__(message)
        self.output = output


# ==================== Reader ====================

INT_RE = re.compile(r'^[+-]?[0-9]+$')

class Reader:
    def __init__(self, source):
        self.source = source
        self.pos = 0
        self.n = len(source)

    def _err(self, msg):
        raise SchemeError(msg)

    def skip_ws_and_comments(self):
        while self.pos < self.n:
            c = self.source[self.pos]
            if c in ' \t\n\r':
                self.pos += 1
            elif c == ';':
                while self.pos < self.n and self.source[self.pos] != '\n':
                    self.pos += 1
            else:
                break

    def read_datum(self):
        self.skip_ws_and_comments()
        if self.pos >= self.n:
            self._err("unexpected end of input")
        c = self.source[self.pos]
        if c == '(':
            return self.read_list()
        elif c == "'":
            self.pos += 1
            datum = self.read_datum()
            return SPair(SSymbol('quote'), SPair(datum, EMPTY))
        elif c == '"':
            return self.read_string()
        elif c == '#':
            self.pos += 1
            if self.pos < self.n and self.source[self.pos] == 't':
                self.pos += 1
                return TRUE
            elif self.pos < self.n and self.source[self.pos] == 'f':
                self.pos += 1
                return FALSE
            else:
                self._err("invalid # token")
        elif c == ')':
            self._err("unexpected )")
        else:
            return self.read_atom()

    def read_atom(self):
        start = self.pos
        while self.pos < self.n:
            c = self.source[self.pos]
            if c in ' \t\n\r()"\'':
                break
            self.pos += 1
        token = self.source[start:self.pos]
        if not token:
            self._err("empty token")
        if INT_RE.match(token):
            return int(token)
        return SSymbol(token)

    def read_string(self):
        assert self.source[self.pos] == '"'
        self.pos += 1
        result = []
        while self.pos < self.n:
            c = self.source[self.pos]
            if c == '"':
                self.pos += 1
                return ''.join(result)
            elif c == '\\':
                self.pos += 1
                if self.pos >= self.n:
                    self._err("unterminated string")
                esc = self.source[self.pos]
                if esc == '"':
                    result.append('"')
                elif esc == '\\':
                    result.append('\\')
                elif esc == 'n':
                    result.append('\n')
                else:
                    self._err("invalid escape sequence")
                self.pos += 1
            else:
                result.append(c)
                self.pos += 1
        self._err("unterminated string")

    def _is_dot_token(self):
        if self.source[self.pos] != '.':
            return False
        if self.pos + 1 >= self.n:
            return True
        return self.source[self.pos + 1] in ' \t\n\r)'

    def read_list(self):
        assert self.source[self.pos] == '('
        self.pos += 1
        elements = []
        while True:
            self.skip_ws_and_comments()
            if self.pos >= self.n:
                self._err("unterminated list")
            c = self.source[self.pos]
            if c == ')':
                self.pos += 1
                return from_list(elements)
            elif c == '.' and self._is_dot_token():
                if not elements:
                    self._err("dot must be preceded by at least one element")
                self.pos += 1
                self.skip_ws_and_comments()
                if self.pos >= self.n:
                    self._err("unterminated list")
                if self.source[self.pos] == ')':
                    self._err("dotted form must have exactly one datum after dot")
                dotted_val = self.read_datum()
                self.skip_ws_and_comments()
                if self.pos >= self.n or self.source[self.pos] != ')':
                    self._err("dotted form must end with )")
                self.pos += 1
                result = SPair(dotted_val, EMPTY)
                for e in reversed(elements):
                    result = SPair(e, result)
                return result
            else:
                datum = self.read_datum()
                elements.append(datum)


# ==================== Environment ====================

class Environment:
    __slots__ = ('frame', 'parent')
    def __init__(self, frame, parent=None):
        self.frame = frame
        self.parent = parent

    def lookup(self, name):
        env = self
        while env is not None:
            if name in env.frame:
                val = env.frame[name]
                if val is UNBOUND:
                    raise SchemeError(f"variable '{name}' referenced before definition")
                return val
            env = env.parent
        raise SchemeError(f"unbound variable: {name}")

    def set(self, name, value):
        env = self
        while env is not None:
            if name in env.frame:
                env.frame[name] = value
                return
            env = env.parent
        raise SchemeError(f"unbound variable: {name}")

    def define(self, name, value):
        self.frame[name] = value


# ==================== Text Representation ====================

def display_repr(x):
    if x is UNSPECIFIED:
        return ''
    if is_int(x):
        return str(x)
    if x is TRUE:
        return '#t'
    if x is FALSE:
        return '#f'
    if is_string(x):
        return x
    if is_symbol(x):
        return x.name
    if x is EMPTY:
        return '()'
    if is_procedure(x):
        return '#<procedure>'
    if is_pair(x):
        return _display_pair(x)
    raise SchemeError("cannot display value")

def _display_pair(p):
    parts = []
    first = True
    while True:
        if p is EMPTY:
            break
        if not isinstance(p, SPair):
            if not first:
                parts.append(' ')
            parts.append('. ')
            parts.append(display_repr(p))
            return '(' + ''.join(parts) + ')'
        if not first:
            parts.append(' ')
        parts.append(display_repr(p.car))
        p = p.cdr
        first = False
    return '(' + ''.join(parts) + ')'

def write_repr(x):
    if x is UNSPECIFIED:
        return ''
    if is_int(x):
        return str(x)
    if x is TRUE:
        return '#t'
    if x is FALSE:
        return '#f'
    if is_string(x):
        escaped = x.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        return '"' + escaped + '"'
    if is_symbol(x):
        return x.name
    if x is EMPTY:
        return '()'
    if is_procedure(x):
        return '#<procedure>'
    if is_pair(x):
        return _write_pair(x)
    raise SchemeError("cannot write value")

def _write_pair(p):
    parts = []
    first = True
    while True:
        if p is EMPTY:
            break
        if not isinstance(p, SPair):
            if not first:
                parts.append(' ')
            parts.append('. ')
            parts.append(write_repr(p))
            return '(' + ''.join(parts) + ')'
        if not first:
            parts.append(' ')
        parts.append(write_repr(p.car))
        p = p.cdr
        first = False
    return '(' + ''.join(parts) + ')'


# ==================== Evaluator ====================

def _is_define_form(f):
    if not isinstance(f, SPair):
        return False
    if not is_proper_list(f):
        return False
    if f is EMPTY:
        return False
    head = f.car
    return is_symbol(head) and head.name == 'define'

def _parse_define(f):
    """Parse a define form. Returns (name_symbol, expr) or (name_symbol, formals, body_list)."""
    parts = to_list(f.cdr)
    if not parts:
        raise SchemeError("malformed define")
    if is_symbol(parts[0]):
        if len(parts) != 2:
            raise SchemeError("malformed define")
        return (parts[0], parts[1])
    elif is_proper_list(parts[0]) and parts[0] is not EMPTY:
        name = parts[0].car
        if not is_symbol(name):
            raise SchemeError("malformed define")
        formals = parts[0].cdr
        body = parts[1:]
        if not body:
            raise SchemeError("malformed define: empty body")
        return (name, formals, body)
    else:
        raise SchemeError("malformed define")

def _parse_formals(formals_expr):
    """Parse formals. Returns ('fixed', [SSymbol,...]) or ('dotted', [SSymbol,...], SSymbol) or ('rest', SSymbol)."""
    if is_symbol(formals_expr):
        return ('rest', formals_expr)
    if is_proper_list(formals_expr):
        elems = to_list(formals_expr)
        for e in elems:
            if not is_symbol(e):
                raise SchemeError("formals must be symbols")
        return ('fixed', elems)
    if is_pair(formals_expr):
        # Dotted: (a b . rest)
        named = []
        p = formals_expr
        while isinstance(p, SPair) and p.cdr is not EMPTY and isinstance(p.cdr, SPair):
            if not is_symbol(p.car):
                raise SchemeError("formals must be symbols")
            named.append(p.car)
            p = p.cdr
        # p is now the last pair: (rest . something)
        if not isinstance(p, SPair):
            raise SchemeError("invalid dotted formals")
        rest_sym = p.car
        if not is_symbol(rest_sym):
            raise SchemeError("formals rest must be a symbol")
        if p.cdr is not EMPTY:
            raise SchemeError("invalid dotted formals")
        return ('dotted', named, rest_sym)
    raise SchemeError("invalid formals")

def _bind_params(closure, args):
    formals = closure.formals
    kind = formals[0]
    if kind == 'rest':
        sym = formals[1]
        return Environment({sym.name: from_list(args)}, closure.env)
    elif kind == 'fixed':
        named = formals[1]
        if len(args) != len(named):
            raise SchemeError(f"wrong number of arguments: expected {len(named)}, got {len(args)}")
        frame = {}
        for i, sym in enumerate(named):
            frame[sym.name] = args[i]
        return Environment(frame, closure.env)
    elif kind == 'dotted':
        named = formals[1]
        rest_sym = formals[2]
        if len(args) < len(named):
            raise SchemeError(f"wrong number of arguments: expected at least {len(named)}, got {len(args)}")
        frame = {}
        for i, sym in enumerate(named):
            frame[sym.name] = args[i]
        frame[rest_sym.name] = from_list(args[len(named):])
        return Environment(frame, closure.env)
    raise SchemeError("invalid formals")

def _setup_body(body, env):
    """Set up internal definitions for a body. Returns the environment to use."""
    def_names = []
    for f in body:
        if _is_define_form(f):
            parsed = _parse_define(f)
            def_names.append(parsed[0].name)
    if def_names:
        new_frame = {name: UNBOUND for name in def_names}
        return Environment(new_frame, env)
    return env

def _eval_body(body, env, output):
    """Evaluate a body in non-tail position."""
    body_env = _setup_body(body, env)
    result = UNSPECIFIED
    for f in body:
        if _is_define_form(f):
            parsed = _parse_define(f)
            dname = parsed[0]
            val = _eval_define_body(parsed, body_env, output)
            body_env.frame[dname.name] = val
            result = UNSPECIFIED
        else:
            result = eval_expr(f, body_env, output)
    return result

def _eval_define_body(parsed, env, output):
    """Evaluate the expression part of a define form."""
    if len(parsed) == 2:
        # (define name expr)
        return eval_expr(parsed[1], env, output)
    else:
        # (define (name . formals) body...)
        name, formals_expr, body = parsed
        formals = _parse_formals(formals_expr)
        return Closure(formals, body, env)

def eval_expr(expr, env, output):
    """Evaluate expr in env (non-tail position). Returns a value."""
    if is_int(expr):
        return expr
    if is_bool(expr):
        return expr
    if is_string(expr):
        return expr
    if is_symbol(expr):
        return env.lookup(expr.name)
    if expr is EMPTY:
        return EMPTY
    if is_procedure(expr):
        return expr
    if expr is UNSPECIFIED:
        return UNSPECIFIED
    if is_pair(expr):
        if not is_proper_list(expr):
            raise SchemeError("dotted form used as application")
        return _eval_list(expr, env, output)
    raise SchemeError("invalid expression")

def _eval_list(form, env, output):
    head = form.car
    if is_symbol(head):
        name = head.name
        if name == 'quote':
            parts = to_list(form.cdr)
            if len(parts) != 1:
                raise SchemeError("malformed quote")
            return parts[0]
        elif name == 'if':
            parts = to_list(form.cdr)
            if len(parts) not in (2, 3):
                raise SchemeError("malformed if")
            test = eval_expr(parts[0], env, output)
            if truthy(test):
                return eval_expr(parts[1], env, output)
            elif len(parts) == 3:
                return eval_expr(parts[2], env, output)
            else:
                return UNSPECIFIED
        elif name == 'begin':
            parts = to_list(form.cdr)
            if not parts:
                raise SchemeError("malformed begin")
            result = UNSPECIFIED
            for p in parts:
                result = eval_expr(p, env, output)
            return result
        elif name == 'cond':
            parts = to_list(form.cdr)
            if not parts:
                raise SchemeError("malformed cond")
            for i, clause in enumerate(parts):
                if not is_proper_list(clause) or clause is EMPTY:
                    raise SchemeError("malformed cond clause")
                test_expr = clause.car
                body = to_list(clause.cdr)
                if is_symbol(test_expr) and test_expr.name == 'else':
                    if i != len(parts) - 1:
                        raise SchemeError("else must be last clause")
                    if not body:
                        raise SchemeError("malformed cond else clause")
                    result = UNSPECIFIED
                    for b in body:
                        result = eval_expr(b, env, output)
                    return result
                else:
                    test_val = eval_expr(test_expr, env, output)
                    if truthy(test_val):
                        if not body:
                            return test_val
                        result = UNSPECIFIED
                        for b in body:
                            result = eval_expr(b, env, output)
                        return result
            return UNSPECIFIED
        elif name == 'and':
            parts = to_list(form.cdr)
            if not parts:
                return TRUE
            result = TRUE
            for p in parts:
                result = eval_expr(p, env, output)
                if result is FALSE:
                    return FALSE
            return result
        elif name == 'or':
            parts = to_list(form.cdr)
            if not parts:
                return FALSE
            for p in parts:
                result = eval_expr(p, env, output)
                if truthy(result):
                    return result
            return FALSE
        elif name == 'define':
            parsed = _parse_define(form)
            dname = parsed[0]
            val = _eval_define_body(parsed, env, output)
            env.define(dname.name, val)
            return UNSPECIFIED
        elif name == 'set!':
            parts = to_list(form.cdr)
            if len(parts) != 2:
                raise SchemeError("malformed set!")
            if not is_symbol(parts[0]):
                raise SchemeError("set! requires a symbol")
            val = eval_expr(parts[1], env, output)
            env.set(parts[0].name, val)
            return UNSPECIFIED
        elif name == 'lambda':
            parts = to_list(form.cdr)
            if len(parts) < 2:
                raise SchemeError("malformed lambda")
            formals_expr = parts[0]
            body = parts[1:]
            if not body:
                raise SchemeError("malformed lambda: empty body")
            formals = _parse_formals(formals_expr)
            return Closure(formals, body, env)
        elif name == 'let':
            parts = to_list(form.cdr)
            if not parts:
                raise SchemeError("malformed let")
            if is_symbol(parts[0]):
                # Named let
                return _eval_named_let(parts, env, output)
            else:
                bindings_list = parts[0]
                body = parts[1:]
                if not body:
                    raise SchemeError("malformed let: empty body")
                if not is_proper_list(bindings_list):
                    raise SchemeError("malformed let bindings")
                new_frame = {}
                for b in to_list(bindings_list):
                    if not is_proper_list(b):
                        raise SchemeError("malformed let binding")
                    belems = to_list(b)
                    if len(belems) != 2:
                        raise SchemeError("malformed let binding")
                    if not is_symbol(belems[0]):
                        raise SchemeError("let binding variable must be a symbol")
                    new_frame[belems[0].name] = eval_expr(belems[1], env, output)
                new_env = Environment(new_frame, env)
                return _eval_body(body, new_env, output)
        elif name == 'let*':
            parts = to_list(form.cdr)
            if not parts:
                raise SchemeError("malformed let*")
            bindings_list = parts[0]
            body = parts[1:]
            if not body:
                raise SchemeError("malformed let*: empty body")
            if not is_proper_list(bindings_list):
                raise SchemeError("malformed let* bindings")
            new_env = env
            for b in to_list(bindings_list):
                if not is_proper_list(b):
                    raise SchemeError("malformed let* binding")
                belems = to_list(b)
                if len(belems) != 2:
                    raise SchemeError("malformed let* binding")
                if not is_symbol(belems[0]):
                    raise SchemeError("let* binding variable must be a symbol")
                val = eval_expr(belems[1], new_env, output)
                new_env = Environment({belems[0].name: val}, new_env)
            return _eval_body(body, new_env, output)
        elif name == 'letrec':
            parts = to_list(form.cdr)
            if not parts:
                raise SchemeError("malformed letrec")
            bindings_list = parts[0]
            body = parts[1:]
            if not body:
                raise SchemeError("malformed letrec: empty body")
            if not is_proper_list(bindings_list):
                raise SchemeError("malformed letrec bindings")
            new_frame = {}
            for b in to_list(bindings_list):
                if not is_proper_list(b):
                    raise SchemeError("malformed letrec binding")
                belems = to_list(b)
                if len(belems) != 2:
                    raise SchemeError("malformed letrec binding")
                if not is_symbol(belems[0]):
                    raise SchemeError("letrec binding variable must be a symbol")
                new_frame[belems[0].name] = UNBOUND
            new_env = Environment(new_frame, env)
            for b in to_list(bindings_list):
                belems = to_list(b)
                val = eval_expr(belems[1], new_env, output)
                new_env.frame[belems[0].name] = val
            return _eval_body(body, new_env, output)
    
    # Regular application
    op = eval_expr(head, env, output)
    args = [eval_expr(a, env, output) for a in to_list(form.cdr)]
    return _call_procedure(op, args)

def _call_procedure(op, args):
    if not is_procedure(op):
        raise SchemeError("attempt to apply non-procedure")
    if isinstance(op, Builtin):
        return op.call(args)
    else:
        new_env = _bind_params(op, args)
        return _eval_body(op.body, new_env, _dummy_output)

# We need a way to handle output in non-tail body evaluation
# Actually, let me restructure: _eval_body needs output

def _eval_body(body, env, output):
    body_env = _setup_body(body, env)
    result = UNSPECIFIED
    for f in body:
        if _is_define_form(f):
            parsed = _parse_define(f)
            dname = parsed[0]
            val = _eval_define_body(parsed, body_env, output)
            body_env.frame[dname.name] = val
            result = UNSPECIFIED
        else:
            result = eval_expr(f, body_env, output)
    return result

def _eval_named_let(parts, env, output):
    let_name = parts[0]
    bindings_list = parts[1]
    body = parts[2:]
    if not body:
        raise SchemeError("malformed named let: empty body")
    if not is_proper_list(bindings_list):
        raise SchemeError("malformed let bindings")
    # Evaluate inits in outer scope
    inits = []
    var_syms = []
    for b in to_list(bindings_list):
        if not is_proper_list(b):
            raise SchemeError("malformed let binding")
        belems = to_list(b)
        if len(belems) != 2:
            raise SchemeError("malformed let binding")
        if not is_symbol(belems[0]):
            raise SchemeError("let binding variable must be a symbol")
        var_syms.append(belems[0])
        inits.append(eval_expr(belems[1], env, output))
    # Create closure for the named let
    formals = ('fixed', var_syms)
    new_env = Environment({let_name.name: UNBOUND}, env)
    closure = Closure(formals, body, new_env)
    new_env.frame[let_name.name] = closure
    # Call the closure with inits
    call_env = _bind_params(closure, inits)
    return _eval_body(body, call_env, output)

def _call_procedure(op, args, output):
    if not is_procedure(op):
        raise SchemeError("attempt to apply non-procedure")
    if isinstance(op, Builtin):
        return op.call(args)
    else:
        new_env = _bind_params(op, args)
        return _eval_body(op.body, new_env, output)


# ==================== Tail Evaluator ====================

def eval_tail(expr, env, output):
    """Evaluate expr in env in a tail position. Returns a value."""
    while True:
        # Atoms
        if is_int(expr):
            return expr
        if is_bool(expr):
            return expr
        if is_string(expr):
            return expr
        if is_symbol(expr):
            return env.lookup(expr.name)
        if expr is EMPTY: