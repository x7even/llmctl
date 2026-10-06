"""Hidden tests for expr_eval. Each test takes the loaded solution module `m`."""
import math
import random


def _eq(got, want):
    assert type(got) is type(want), f"type {type(got).__name__} != {type(want).__name__} (got {got!r}, want {want!r})"
    if isinstance(want, float):
        assert math.isclose(got, want, rel_tol=1e-9, abs_tol=1e-12), f"{got!r} != {want!r}"
    else:
        assert got == want, f"{got!r} != {want!r}"


def _case(expr):
    want = eval(expr)  # ground truth: Python itself (test side only)
    return lambda m: _eq(m.evaluate(expr), want)


def _raises(exc, expr):
    def t(m):
        try:
            m.evaluate(expr)
        except exc:
            return
        except Exception as e:  # wrong exception type
            raise AssertionError(f"{expr!r}: raised {type(e).__name__}, expected {exc.__name__}")
        raise AssertionError(f"{expr!r}: did not raise {exc.__name__}")
    return t


def test_basic_ints(m):
    for e in ["1", "42", "1+2", "7-10", "3*4", "2+3*4", "(2+3)*4", "10-4-3", "100//7", "100%7"]:
        _case(e)(m)


def test_division_types(m):
    for e in ["7/2", "4/2", "0/5", "7//2", "7.0//2", "7%3", "7.5%2"]:
        _case(e)(m)


def test_floor_semantics_negative(m):
    for e in ["-7//2", "7//-2", "-7//-2", "-7%3", "7%-3", "-7.5//2", "-7.5%2", "7.5%-2"]:
        _case(e)(m)


def test_decimal_literals(m):
    for e in [".5", "2.", "3.5+.5", "2.*3", ".5*.5", "10/4.", "0.1+0.2"]:
        _case(e)(m)


def test_left_associativity(m):
    for e in ["100/10/5", "100//7//2", "2-3-4", "100%30%7", "8/4*2", "8//4*2", "2*8//4%3"]:
        _case(e)(m)


def test_power_right_assoc(m):
    for e in ["2**3**2", "2**3**0", "(2**3)**2", "2**10", "3**2**2**1"]:
        _case(e)(m)


def test_unary_vs_power(m):
    for e in ["-2**2", "(-2)**2", "-2**-2", "2**-1", "2**-2**2", "-2**3**2", "+2**2", "- -2**2"]:
        _case(e)(m)


def test_stacked_unary(m):
    for e in ["--3", "+-+2", "---1", "-+-+1", "1--1", "1+-+-2", "2*-3", "2*+-3", "-(-(3))", "-(2+3)*2"]:
        _case(e)(m)


def test_unary_precedence_vs_mul(m):
    for e in ["-3*2", "-3//2", "-3%2", "2*-3**2", "-3**2*2", "10--3--3"]:
        _case(e)(m)


def test_whitespace(m):
    for e in ["  1 +   2 ", "\t3\t*\t4", "( 1 + 2 ) * ( 3 - 1 )", "2 ** - 1", "- 2", " 1 / 4 "]:
        _case(e)(m)


def test_nested_parens(m):
    for e in ["((((1))))", "(1+(2*(3+(4*5))))", "((2))**((3))", "-(-(-(1)))", "(((1+2)))*(((3)))"]:
        _case(e)(m)


def test_int_float_result_types(m):
    for e in ["2**2", "2**-1", "2.0**2", "2**2.0", "4/2", "1+1.0", "5//1.0", "True" if False else "3-3.0"]:
        _case(e)(m)


def test_big_ints(m):
    for e in ["2**100", "123456789*987654321", "10**30//7", "99999999999999999999+1"]:
        _case(e)(m)


def test_zero_division(m):
    for e in ["1/0", "1//0", "1%0", "1/(2-2)", "5.5//0", "5.5%0.0", "0**-1", "1/0.0", "1+1/(3-3)"]:
        _raises(ZeroDivisionError, e)(m)


def test_zero_ok(m):
    for e in ["0/1", "0//3", "0%3", "0**0", "0**2", "0.0/2"]:
        _case(e)(m)


def test_malformed_raises_valueerror(m):
    bad = ["", "   ", "\t", "()", "(", ")", "(1", "1)", "((1)", "(1))", "1 +", "+", "*2", "1 2", "1 (2)", "(1)(2)",
           "1 + * 2", "1 ** ** 2", "1 //", "1..2", "1.2.3", ".", "1 + .", "abc", "1 + a", "1_000", "1e3", "0x10",
           "2 ^ 3", "1 , 2", "1 = 1", "1 +- ", "(+)", "1 + ()", "- ", "3 $ 4"]
    for e in bad:
        _raises(ValueError, e)(m)


def test_not_using_eval(m):
    # solutions must not call eval/exec/compile/ast — check the source
    import inspect
    import re
    src = inspect.getsource(m)
    code = "\n".join(l.split("#")[0] for l in src.splitlines())
    assert hasattr(m, "evaluate"), "no evaluate() defined"
    assert not re.search(r"(?<![\w.])(eval|exec|compile)\s*\(", code), "uses eval/exec/compile"
    assert not re.search(r"^\s*(import ast|from ast)", code, re.M), "imports ast"


def test_differential_fuzz(m):
    """500 random well-formed expressions vs Python's own eval."""
    rnd = random.Random(1234)
    ops = ["+", "-", "*", "/", "//", "%", "**"]

    def num():
        c = rnd.random()
        if c < 0.55:
            return str(rnd.randint(0, 9))
        if c < 0.8:
            return f"{rnd.randint(0, 9)}.{rnd.randint(0, 9)}"
        return rnd.choice([".5", "2.", "3.", ".25"])

    def gen(depth):
        if depth == 0 or rnd.random() < 0.25:
            s = num()
        else:
            s = f"{gen(depth - 1)}{rnd.choice(['', ' '])}{rnd.choice(ops)}{rnd.choice(['', ' '])}{gen(depth - 1)}"
        r = rnd.random()
        if r < 0.15:
            s = f"({s})"
        elif r < 0.25:
            s = f"{rnd.choice(['-', '+', '--', '-+'])}{s if s[0] == '(' or s.replace('.', '').isdigit() else '(' + s + ')'}"
        return s

    checked = 0
    for _ in range(4000):
        e = gen(3)
        if len(e) > 60:
            continue
        try:
            want = eval(e)
        except ZeroDivisionError:
            _raises(ZeroDivisionError, e)(m)
            checked += 1
            continue
        except Exception:
            continue
        if isinstance(want, complex) or (isinstance(want, (int, float)) and abs(want) > 1e12):
            continue
        _eq(m.evaluate(e), want)
        checked += 1
        if checked >= 500:
            break
    assert checked >= 300, f"fuzz generated too few cases ({checked})"


TESTS = [
    test_basic_ints, test_division_types, test_floor_semantics_negative, test_decimal_literals,
    test_left_associativity, test_power_right_assoc, test_unary_vs_power, test_stacked_unary,
    test_unary_precedence_vs_mul, test_whitespace, test_nested_parens, test_int_float_result_types,
    test_big_ints, test_zero_division, test_zero_ok, test_malformed_raises_valueerror,
    test_not_using_eval, test_differential_fuzz,
]
