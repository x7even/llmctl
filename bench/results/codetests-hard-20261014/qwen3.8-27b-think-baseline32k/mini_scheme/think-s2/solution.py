import sys
import re

if hasattr(sys, 'set_int_max_str_digits'):
    sys.set_int_max_str_digits(0)

sys.setrecursionlimit(100000)


class SchemeError(Exception):
    def __init__(self, message, output=''):
        super().__init__(message)
        self.output = output


class Symbol:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name


class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr


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
