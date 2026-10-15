import sys
import threading

sys.setrecursionlimit(1000000)
try:
    sys.set_int_max_str_digits(0)
except AttributeError:
    pass


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


class _Nil:
    def __repr__(self):
        return '()'
NIL = _Nil()


class _Unspecified:
    def __repr__(self):
        return 'Unspecified'
UNSPECIFIED = _Unspecified()


class Closure:
    __slots__ = ('formals', 'body', 'env')
    def __init__(self, formals, body, env):
        self.formals = formals
        self.body = body
        self.env = env


class Builtin:
    __slots__ = ('name', 'func', 'min_args', 'max_args')
    def __init__(self, name, func, min_args=None, max_args=None):
        self.name = name
        self.func = func
        self.min_args = min_args
        self.max_args = max_args


class TailCall:
    __slots__ = ('proc', 'args')
    def __init__(self, proc, args):
        self.proc = proc
        self.args = args


class SchemeError(Exception):
    def __init__(self, message, output=''):
        super().__init__(message)
        self.output = output


_UNBOUND = object()


class Frame:
    __slots__ = ('vars', 'parent')
    def __init__(self, vars_dict, parent):
        self.vars = vars_dict
        self.parent = parent


def make_frame(d, parent):
    return Frame(d, parent)


def lookup(name, env):
    while env is not None:
        if name.name in env.vars:
            val = env.vars[name.name]
            if val is _UNBOUND:
                raise SchemeError("unbound variable: " + name.name)
            return val
        env = env.parent
    raise SchemeError("unbound variable: " + name.name)


def set_var(name, val, env):
    while env is not None:
        if name.name in env.vars:
            env.vars[name.name] = val
            return
        env = env.parent
    raise SchemeError("set!: unbound variable: " + name.name)


def define_var(name, val, env):
    env.vars[name.name] = val


# ============ READER ============

def _is_int_tok(tok):
    if not tok:
        return False
    i = 0
    if tok[0] in '+-':
        if len(tok) == 1:
            return False
        i = 1
    return all('0' <= c <= '9' for c in tok[i:])


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
            chars = []
            closed = False
            while i < n:
                if source[i] == '\\':
                    i += 1
                    if i >= n:
                        raise SchemeError("unterminated string escape")
                    ec = source[i]
                    if ec == '"':
                        chars.append('"')
                    elif ec == '\\':
                        chars.append('\\')
                    elif ec == 'n':
                        chars.append('\n')
                    else:
                        raise SchemeError("bad escape: \\" + ec)
                    i += 1
                elif source[i] == '"':
                    i += 1
                    closed = True
                    break
                else:
                    chars.append(source[i])
                    i += 1
            if not closed:
                raise SchemeError("unterminated string")
            tokens.append(('str', ''.join(chars)))
        else:
            j = i
            while j < n and source[j] not in ' \t\n\r()";\'':
                j += 1
            tok = source[i:j]
            i = j
            if tok == '#t':
                tokens.append(True)
            elif tok == '#f':
                tokens.append(False)
            elif tok.startswith('#'):
                raise SchemeError("bad token: " + tok)
            elif tok == '.':
                tokens.append('.')
            elif _is_int_tok(tok):
                tokens.append(int(tok))
            else:
                tokens.append(Symbol(tok))
    return tokens


def parse_datum(tokens, pos):
    if pos[0] >= len(tokens):
        raise SchemeError("unexpected end of input")
    tok = tokens[pos[0]]
    if tok == '(':
        return parse_list(tokens, pos)
    elif tok == "'":
        pos[0] += 1
        datum = parse_datum(tokens, pos)
        return Pair(Symbol('quote'), Pair(datum, NIL))
    elif tok == ')':
        raise SchemeError("unexpected )")
    elif tok == '.':
        raise SchemeError("unexpected .")
    elif isinstance(tok, tuple) and tok[0] == 'str':
        pos[0] += 1
        return tok[1]
    else:
        pos[0] += 1
        return tok


def parse_list(tokens, pos):
    pos[0] += 1  # consume (
    elements = []
    dot_seen = False
    cdr = None
    while True:
        if pos[0] >= len(tokens):
            raise SchemeError("unexpected end of input (unclosed ()")
        tok = tokens[pos[0]]
        if tok == ')':
            pos[0] += 1
            break
        elif tok == '.':
            if dot_seen:
                raise SchemeError("multiple dots in list")
            if len(elements) == 0:
                raise SchemeError("dot with no preceding element")
            dot_seen = True
            pos[