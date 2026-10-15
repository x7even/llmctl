"""Hidden tests for regex_engine. Each test takes the loaded solution module `m`.

Oracle: Python's own `re` module (test side only). Every differential test compares, for the
SAME pattern and string, the full observable result (span, groups, per-group start/end/group)
of `fullmatch` and `search` between `re` and the solution. Generators are seeded
(`random.Random(<const>)`) and were screened at authoring time so that `re` itself finishes each
test quickly and so that no case touches a place where the prompt deliberately differs from
`re` (see `test_strict_dialect_rejections`). The scale tests cannot use `re` (it is exponential
there), so their expected answers are derived analytically and written down in comments.
"""
import random
import re
import warnings

warnings.simplefilter("ignore")


# ------------------------------------------------------------------ helpers
def _sig(mt):
    if mt is None:
        return None
    n = len(mt.groups())
    return (mt.span(), mt.groups(),
            tuple((mt.start(i), mt.end(i), mt.group(i)) for i in range(n + 1)),
            tuple(mt.span(i) for i in range(n + 1)))


def _raises(exc, fn, what=""):
    try:
        fn()
    except exc:
        return
    except Exception as e:
        raise AssertionError(f"{what}: raised {type(e).__name__}, expected {exc.__name__}")
    raise AssertionError(f"{what}: did not raise {exc.__name__}")


def _diff(m, pattern, strings):
    """Compare solution against `re` on every string, for both fullmatch and search."""
    want_p = re.compile(pattern)
    got_p = m.compile(pattern)
    for s in strings:
        for kind in ("fullmatch", "search"):
            want = _sig(getattr(want_p, kind)(s))
            got = _sig(getattr(got_p, kind)(s))
            assert want == got, f"{kind}({pattern!r}, {s!r}): expected {want}, got {got}"


def _diff_table(m, table):
    for pattern, strings in table:
        _diff(m, pattern, strings)


def _ok(m, pattern, s, kind, span, groups):
    got = getattr(m.compile(pattern), kind)(s)
    assert got is not None, f"{kind}({pattern!r}, {s!r}) returned None"
    assert (got.span(), got.groups()) == (span, groups), \
        f"{kind}({pattern!r}, {s!r}): expected {(span, groups)}, got {(got.span(), got.groups())}"


def _none(m, pattern, s, kind):
    got = getattr(m.compile(pattern), kind)(s)
    assert got is None, f"{kind}({pattern!r}, {s!r}): expected None, got span {got.span()}"


# ------------------------------------------------------------------ handwritten tests
def test_api_and_examples(m):
    _ok(m, "(a|ab)(c|bcd)(d*)", "abcd", "fullmatch", (0, 4), ("a", "bcd", ""))
    _ok(m, "a*?", "aaa", "fullmatch", (0, 3), ())
    _ok(m, "a*?", "aaa", "search", (0, 0), ())
    _ok(m, "(a+)(b+)?", "xaab", "search", (1, 4), ("aa", "b"))
    _ok(m, "(a|b)*?c", "abc", "search", (0, 3), ("b",))
    _ok(m, "(a*)*", "aa", "fullmatch", (0, 2), ("",))
    _ok(m, "(?:(a)|b)+", "ab", "fullmatch", (0, 2), ("a",))
    _ok(m, "(a){0}b", "b", "fullmatch", (0, 1), (None,))
    _ok(m, "$", "ab\n", "search", (2, 2), ())
    _ok(m, "[]a]+", "x]a]", "search", (1, 4), ())
    # Match API details
    mt = m.compile(r"(a)(x)?(b)").fullmatch("ab")
    assert mt.span() == (0, 2) and mt.span(0) == (0, 2) and isinstance(mt.span(), tuple)
    assert mt.group() == "ab" and mt.group(0) == "ab" and mt.group(1) == "a" and mt.group(3) == "b"
    assert mt.group(2) is None and mt.start(2) == -1 and mt.end(2) == -1 and mt.span(2) == (-1, -1)
    assert mt.start() == 0 and mt.end() == 2 and mt.start(3) == 1 and mt.end(3) == 2
    assert mt.groups() == ("a", None, "b") and isinstance(mt.groups(), tuple)
    for bad in (4, 5, -1, 100):
        _raises(IndexError, lambda: mt.group(bad), f"group({bad})")
        _raises(IndexError, lambda: mt.span(bad), f"span({bad})")
        _raises(IndexError, lambda: mt.start(bad), f"start({bad})")
        _raises(IndexError, lambda: mt.end(bad), f"end({bad})")
    nogroups = m.compile("a+").search("baab")
    assert nogroups.groups() == () and nogroups.span() == (1, 3) and nogroups.group() == "aa"
    _raises(IndexError, lambda: nogroups.group(1), "group(1) without groups")
    # nested numbering is by opening parenthesis
    mt = m.compile(r"((a)(b(c)))(d)").fullmatch("abcd")
    assert mt.groups() == ("abc", "a", "bc", "c", "d")
    assert [mt.span(i) for i in range(6)] == [(0, 4), (0, 3), (0, 1), (1, 3), (2, 3), (3, 4)]
    # non-capturing groups do not take a number
    assert m.compile(r"(?:a)(b)(?:c)(d)").fullmatch("abcd").groups() == ("b", "d")
    # search vs fullmatch, and failure
    assert m.compile("b").fullmatch("ab") is None and m.compile("b").search("ab").span() == (1, 2)
    assert m.compile("").search("xyz").span() == (0, 0) and m.compile("").fullmatch("xyz") is None
    assert m.compile("").fullmatch("").span() == (0, 0)
    assert m.compile("x*").search("").span() == (0, 0)
    assert m.compile("a|ab").search("ab").span() == (0, 1)       # first in priority order, not longest
    assert m.compile("a|ab").fullmatch("ab").span() == (0, 2)    # fullmatch keeps backtracking
    # the compiled pattern is reusable and stateless
    p = m.compile(r"(\d+)-(\d+)")
    assert p.search("tel 12-34").groups() == ("12", "34")
    assert p.search("none") is None
    assert p.fullmatch("5-6").groups() == ("5", "6")
    assert p.search("tel 12-34").groups() == ("12", "34")


def test_classes_escapes_anchors(m):
    _diff_table(m, [
        ("[abc]+", ["abcabc", "abd", "", "cab"]),
        ("[a-c]+x", ["abcx", "dx", "ax", "x"]),
        ("[^a-c]+", ["xyz", "abc", "\n", "xa"]),
        ("[\\d_]+", ["12_3", "a", "_"]),
        ("[\\D]+", ["ab-", "1", "a1"]),
        ("[\\w-]+", ["ab-c_1", "a b", "-"]),
        ("[a-]+", ["a-a", "-", "b"]),
        ("[-a]+", ["a-a", "-", "b"]),
        ("[a-c-e]+", ["a-e", "abcde", "-", "d"]),
        ("[\\d-]+", ["1-2", "-", "a"]),
        ("[]a]+", ["]a]", "a", "]", "b"]),
        ("[^]a]+", ["bc", "]", "a", "b]"]),
        ("[]]", ["]", "a"]),
        ("[a\\-z]+", ["a-z", "b", "-"]),
        ("[\\]\\\\]+", ["]\\]", "a"]),
        ("[\\^a]+", ["^a", "b"]),
        ("[a^]+", ["^a", "b"]),
        ("[.*+?()|{}$]+", [".*+?()|{}$", "a"]),
        ("[\\s]+", [" \t\n\r\f\v", "a", " a"]),
        ("[^\\s]+", ["ab", "a b"]),
        ("[\\S\\s]+", ["a \n", ""]),
        ("[\\W\\d]+", ["-.1", "a"]),
        ("[^\\W]+", ["ab_1", "a-"]),
        ("[\\n\\t]+", ["\n\t", "a"]),
        ("[+--]+", ["+,-", "."]),
        ("[--/]+", ["-./", "0"]),
        ("[\\]-a]+", ["]^a", "b"]),
        ("[[]+", ["[[", "]"]),
        ("[a-a]", ["a", "b"]),
        (r"\d+\.\d*", ["3.14", "3.", ".5", "3x14"]),
        (r"\w+\s\w+", ["ab cd", "ab  cd", "a_1\tb", "ab\ncd"]),
        (r"\W+", ["-. \n", "a"]),
        (r"\D\S\s", ["a1 ", "1a ", "ab "]),
        (r"\S+", ["ab1_", "a b"]),
        ("a\\tb", ["a\tb", "atb"]),
        ("a\\nb", ["a\nb", "anb"]),
        (r"\(\)", ["()", ")("]),
        (r"\[x\]", ["[x]", "x"]),
        (r"\{2\}", ["{2}", "2"]),
        (r"\*\+\?", ["*+?", "a"]),
        (r"\^\$", ["^$", "$^"]),
        (r"\|", ["|", "a"]),
        (r"\/\-\_\ \,", ["/-_ ,"]),
        (r"a{2}\{", ["aa{", "a{"]),
        ("a}", ["a}", "a"]),
        ("]", ["]", "a"]),
        ("a]b", ["a]b"]),
        (".", ["\n", "a", ""]),
        (".+", ["ab\ncd", "\n", "ab"]),
        ("a.c", ["abc", "a\nc"]),
        # anchors
        ("^a", ["ba", "ab", "a", ""]),
        ("a$", ["a\n", "a\n\n", "ba", "a", "ab\n"]),
        ("^$", ["", "\n", "\n\n", "a"]),
        ("$", ["", "\n", "a\n", "a", "a\n\n"]),
        ("^", ["", "a"]),
        ("a$\n", ["a\n", "a"]),
        ("a\n$", ["a\n", "a\n\n"]),
        ("a\n?$", ["a\n", "a", "a\n\n"]),
        ("(?:a$)+", ["a", "aa", "a\n"]),
        ("$a", ["a", ""]),
        ("a^b", ["ab"]),
        ("^^a", ["a"]),
        ("a$$", ["a\n", "a"]),
        ("(^|x)a", ["a", "xa", "ba", "bxa"]),
        ("(a|^)b", ["b", "ab", " b", "bb"]),
        ("(a$|b)+", ["ab", "ba", "ba\n", "aa"]),
        ("^(?:a|b$)*$", ["aab", "aab\n", "ab\na", "b"]),
        (".*$", ["ab\n", "ab\ncd\n", "", "\n"]),
        ("\\s*$", ["a \n", "  ", "a\n\n", "a"]),
        ("^\\s*$", ["\n", "\n\n", " \n", "a"]),
        ("(^a)*", ["aa", "", "ba"]),
        ("(a$)?", ["a", "a\n", "b"]),
    ])


def test_priority_and_laziness(m):
    _diff_table(m, [
        ("a|ab", ["ab", "abc", "a"]),
        ("ab|a", ["ab", "a"]),
        ("(a|ab)(c|bcd)(d*)", ["abcd", "abc", "abcdd"]),
        ("(a|ab)(bc|c)?", ["abc", "ab", "a"]),
        ("(?:a|ab|abc)+", ["abcab", "aabc", "abab"]),
        ("a*", ["aaa", "baa", ""]),
        ("a*?", ["aaa", "baa", ""]),
        ("a*?b", ["aaab", "b", "aac"]),
        ("a+?", ["aaa", "b"]),
        ("a??", ["a", ""]),
        ("a??b", ["ab", "b"]),
        ("a{2,4}", ["aaaaaa", "a", "aaa"]),
        ("a{2,4}?", ["aaaaaa", "aaa"]),
        ("a{2,4}?b", ["aaab", "ab", "aaaaab"]),
        ("a{2,}", ["aaaaa", "a"]),
        ("a{2,}?", ["aaaaa"]),
        ("a{3}", ["aaaaa", "aa", "aaa"]),
        ("a{0}b", ["b", "ab"]),
        ("(a{1,2}){2}", ["aaa", "aaaa", "aa", "a"]),
        ("(a{1,2}?){2}", ["aaa", "aaaa", "aa"]),
        ("(a|b)*?c", ["abc", "c", "ab"]),
        ("(a|b)*c", ["abc", "c", "ab"]),
        ("(.*)(\\d+)", ["abc123", "12", "a1b22"]),
        ("(.*?)(\\d+)", ["abc123", "12", "a1b22"]),
        ("(.*?)(\\d+)$", ["abc123", "a1b22"]),
        ("(.+?)(.+?)(.+)", ["abcdef", "abc"]),
        ("(\\w+?)(\\d*)$", ["ab12", "ab", "1"]),
        ("<.+>", ["<a><b>", "<a>"]),
        ("<.+?>", ["<a><b>", "<a>"]),
        ("(a+)(a+)", ["aaaa", "aa"]),
        ("(a+?)(a+?)", ["aaaa", "aa"]),
        ("(a+)+b", ["aaab", "aaa"]),
        ("(a+?)+?b", ["aaab"]),
        ("x*(xx)*y", ["xxxy", "xy", "y", "xxy"]),
        ("(?:x?){3}y", ["xxy", "y", "xxxy"]),
        ("(a?){2}a", ["a", "aa", "aaa"]),
        ("(a?)*a", ["a", "aa"]),
        ("(a|ab|b)+c", ["abbc", "abc", "ac"]),
        ("(?:(a)|(ab))(b?)", ["ab", "a"]),
        ("a(?:b|bc)?(?:c|cd)?", ["abcd", "abc", "a"]),
        ("(ab|a)(bc|c)?", ["abc"]),
        ("(a)|(b)|(c)", ["a", "b", "c"]),
        ("((a)|(b))+", ["ab", "ba", "aab"]),
        ("a|b|", ["", "a", "b", "c"]),
        ("|a|b", ["a", "", "b"]),
        ("(|a)", ["a", ""]),
        ("(a|)", ["a", ""]),
        ("(a||b)", ["b", "a", ""]),
        ("a(|b)c", ["ac", "abc"]),
    ])


def test_capture_semantics(m):
    _diff_table(m, [
        ("(a|b)+", ["ab", "ba", "aab", "abab"]),
        ("(a|b)*", ["ab", "", "abba"]),
        ("(?:(a)|b)+", ["ab", "ba", "bb", "aba", "b"]),
        ("(?:(a)|(b))+", ["ab", "ba", "aab", "bbb"]),
        ("(?:(a)|(b))*", ["", "ab", "ba"]),
        ("(?:(a)|b)*c", ["abc", "bbc", "c", "ababc"]),
        ("(?:(a)|(b)|(c))+", ["abc", "cba", "acb"]),
        ("(?:(a)?b)+", ["abb", "bab", "bb", "ab"]),
        ("(?:(a)?(b)?)+", ["ab", "ba", "b", "a"]),
        ("(?:(a)|(b)){2}", ["ab", "ba", "aa"]),
        ("(?:(a)|(b)){2,3}", ["aba", "ab", "bbb"]),
        ("(a)?(b)?(c)?", ["abc", "ac", "b", ""]),
        ("(a)*", ["aaa", "", "b"]),
        ("(a)+?", ["aaa"]),
        ("(a){2}", ["aa", "a"]),
        ("(a){0}b", ["b"]),
        ("(a){0,0}", [""]),
        ("(a)|b", ["b", "a"]),
        ("(a)|(b)", ["b", "a"]),
        ("(?:(a)|b)(?:(c)|d)", ["bd", "ac", "bc", "ad"]),
        ("((a)|b)+", ["ab", "ba", "a"]),
        ("((a)|(b))*", ["ab", "ba"]),
        ("(a(b)?)+", ["aba", "abab", "aab", "a"]),
        ("(a(b)?)+?c", ["abac", "aac"]),
        ("(?:a(b)?)+", ["aba", "ab", "a"]),
        ("(?:a(b)|a)+", ["abab", "aab", "aba"]),
        ("(a|ab)(c|bcd)?", ["abcd", "ab", "abc"]),
        ("(?:(a)b|ac)+", ["abac", "acab", "ab"]),
        ("(?:(a)b|(a)c)+", ["abac", "acab"]),
        ("(x(a)|x(b))+", ["xaxb", "xbxa"]),
        ("(((a)))", ["a"]),
        ("(a(b(c)?)?)+", ["abcabab", "aab", "abc"]),
        ("(a*)(b*)(a*)", ["aabbaa", "bb", "", "aba"]),
        ("(a*)+(b*)", ["aab", "b", ""]),
        ("^(?:(a)|(b))*$", ["abab", "bba"]),
        ("(?:(a)|b)*?c", ["abc", "bbc"]),
        ("(?:(a)|b)*?$", ["ab", "ba"]),
        ("()", [""]),
        ("(())", [""]),
        ("(a)()", ["a"]),
        ("()+", [""]),
        ("(?:)+", [""]),
        ("(|)+", [""]),
        ("(a)|()", ["", "a"]),
    ])
    # a few absolute expectations (not relying on `re`)
    _ok(m, "(a|b)+", "abba", "fullmatch", (0, 4), ("a",))
    _ok(m, "(?:(a)|(b))+", "ab", "fullmatch", (0, 2), ("a", "b"))
    _ok(m, "(?:(a)|b)*c", "abbc", "fullmatch", (0, 4), ("a",))


def test_empty_iteration_loops(m):
    _diff_table(m, [
        ("(a*)*", ["aa", "", "b", "aab", "a"]),
        ("(a*)+", ["aa", "", "b", "aab"]),
        ("(a*)*?", ["aa", "", "b"]),
        ("(a*)+?", ["aa", "", "b"]),
        ("(a*)*b", ["aab", "b", "aa", "aabab"]),
        ("(a*)*?b", ["aab", "b", "aabab"]),
        ("(a|)+", ["aa", "", "b", "aab"]),
        ("(|a)+", ["aa", "", "b", "aab"]),
        ("(a|)+?", ["aa", ""]),
        ("(|a)+?", ["aa", ""]),
        ("(a|)*", ["aa", "b"]),
        ("(|a)*", ["aa", "b"]),
        ("(|a)*?", ["aa", "b"]),
        ("(a|)*?b", ["aab", "b"]),
        ("(|a)*?b", ["aab", "b"]),
        ("(a?)*", ["aa", "b", ""]),
        ("(a?)+", ["aa", "b", ""]),
        ("(a?)*?b", ["aab", "b"]),
        ("(a?){2}", ["a", "aa", "", "aaa"]),
        ("(a?){3}", ["a", "aa", "aaa", ""]),
        ("(a?){2,}", ["a", "aa", "aaa", ""]),
        ("(a?){2,3}", ["a", "aa", "aaa", "aaaa", ""]),
        ("(a?){2,3}?", ["a", "aa", "aaa", ""]),
        ("(a?){2,}?b", ["ab", "aab", "b", "aaab"]),
        ("(a?){0,2}", ["a", "aa", "aaa"]),
        ("(a?){0,2}?", ["a", "aa"]),
        ("(?:a?){2,}", ["a", "aa", ""]),
        ("(?:a*){2,3}", ["a", "aaaa", ""]),
        ("(a*){2,3}", ["aaaa", "a", ""]),
        ("(a*){2}", ["aaaa", "a", ""]),
        ("(a*){2}b", ["aab", "b"]),
        # forced (below-minimum) iterations may be empty without ending the loop early
        ("(a*?){2}", ["aa", "a", ""]),
        ("(a*?){2}$", ["aa", "a"]),
        ("(|a){3}", ["aa", "a", ""]),
        ("(|a){3}$", ["aa", "aaa"]),
        ("(a*)*(a)", ["aa", "a", "aaa"]),
        ("(a*)+(a)", ["aa", "a"]),
        ("(a*)*a", ["aa", "a", "aab"]),
        ("(a*?)*", ["aa", "b"]),
        ("(a*?)+", ["aa", "b"]),
        ("(a*?)*?b", ["aab"]),
        ("(a+|)*", ["aa", "b"]),
        ("(a+|b*)*", ["aabb", "bbaa", "ab"]),
        ("(a*|b*)*", ["aabb", "bbaa", "ab"]),
        ("(a*|b)*", ["ab", "ba", "aab"]),
        ("(b|a*)*", ["ab", "ba", "aab"]),
        ("(?:a*|b)*", ["ab", "ba", "aab"]),
        ("(a*b*)*", ["aabb", "abab", "ba"]),
        ("(a?b?)*", ["abab", "ba", "aabb"]),
        ("(a?b?)+", ["abab", "ba", ""]),
        ("(a?b?)*?c", ["abc", "c", "bac"]),
        ("(a|b|)*", ["ab", "ba", ""]),
        ("(a|b|)+", ["ab", "ba", "c"]),
        ("((a*)|b)*", ["aab", "baa", "b"]),
        ("((a)*)*", ["aa", "", "b"]),
        ("((a)*)+", ["aa", "", "b"]),
        ("((a*)*)*", ["aa", "b"]),
        ("(()|a)*", ["aa", ""]),
        ("(()|a)+", ["aa", ""]),
        ("(a|())+", ["aa", ""]),
        ("(a|())*b", ["aab", "b"]),
        ("()*", [""]),
        ("()+", [""]),
        ("()*?", [""]),
        ("()+?a", ["a"]),
        ("(){3}", [""]),
        ("(){0,3}", [""]),
        ("(?:)*", ["", "a"]),
        ("(?:)+?", ["", "a"]),
        ("(?:|)*", ["", "a"]),
        ("(?:a*)*", ["aa", "b", ""]),
        ("(?:a*)+", ["aa", "b", ""]),
        ("(?:a*)*?b", ["aab"]),
        ("(?:a*)+?b", ["aab", "b"]),
        ("(?:a?)*b", ["aab", "b", "ab"]),
        ("(?:a?)+?b", ["aab", "b"]),
        ("(?:^)*a", ["a", "ba"]),
        ("(?:$)*", ["", "a"]),
        ("(^)*", ["", "a"]),
        ("(^|a)*", ["aa", "ba"]),
        ("(a|$)*", ["aa", "a\n", ""]),
        ("(^|a)+", ["aa", "ba"]),
        ("(a*)*(b*)*", ["aabb", "bbaa", ""]),
        ("(a*)(a*)*", ["aa", "a", ""]),
        ("(a*)+(a*)+", ["aa", "a", ""]),
        ("((a)|(b)|())*", ["ab", "", "ba"]),
        ("((a)|(b)|())+", ["ab", "", "ba"]),
        ("((a)|(b)|())+?c", ["abc", "c"]),
        ("(a*)*$", ["aa", "aab", "a\n"]),
        ("(a*)*\\s", ["aa ", " "]),
        ("(\\d*\\.?)*", ["1.2.3", "..", "12", ""]),
        ("(\\d*\\.?)+x", ["1.2.3x", "..x", "x"]),
        ("(\\w*\\s*)*", ["ab cd ef", "  ", ""]),
    ])
    # absolute expectations stated in the prompt
    _ok(m, "(a*)*", "aa", "fullmatch", (0, 2), ("",))
    _ok(m, "(a|)+", "aa", "fullmatch", (0, 2), ("",))
    _ok(m, "(a*)+", "b", "search", (0, 0), ("",))


def test_invalid_patterns(m):
    bad = [
        "(", ")", "(()", "())", "a)", "(a", "(?:a", "((a)", "(a))", ")(", "(?:", "a(b|c",
        "[a", "[", "[]", "[^]", "[a-", "[^a", "[z-a]", "[\\d-z]", "[a-\\d]", "[b-a]x", "[\\w-a]", "[\\s-0]",
        "*", "+", "?", "a|*", "(*)", "(?:+)", "|+", "^*", "$+", "^?", "$*", "x|?", "(|*)",
        "a**", "a+*", "a*??", "a???", "a+??", "a{2}{3}", "a*{2}", "a{2}*", "a{2}?{3}", "a?*", "(a)**",
        "a{2,1}", "a{3,2}?", "a{10,9}", "{2}", "a|{2}", "(?:{2})", "{1,2}a", "^{2}", "${1}",
        "\\", "a\\", "[\\", "[a\\", "\\q", "\\1", "\\z",
    ]
    for p in bad:
        _raises(ValueError, lambda: m.compile(p), f"compile({p!r})")
    good = [
        "", "|", "()", "(?:)", "a||b", "(|)", "[]]", "[^]]", "[a-a]", "a{0}", "a{0,0}", "(a){0,}?",
        "\\\\", "\\.", "[\\]]", "a{1,1}", "a{00}", "(?:a|)", "(?:|a)+", "a{2,2}?", "((((a))))", "(?:(?:a))",
        "a?", "a??", "a*?", "a+?", "(a)+?", "[a-]", "[-a]", "[\\d-]", "x]", "x}", "-", ",", "a,b",
    ]
    for p in good:
        got = m.compile(p)
        assert hasattr(got, "fullmatch") and hasattr(got, "search"), p
    _diff_table(m, [(p, ["", "a", "ab", "aa", "a]", "]", "x}", "-"]) for p in good])
    # errors are raised by compile, not deferred; and repeated compiles stay consistent
    for p in bad[:5]:
        _raises(ValueError, lambda: m.compile(p), "second compile")


def test_strict_dialect_rejections(m):
    # Deliberate differences from `re`: the prompt defines a stricter dialect, so these are errors.
    strict = [
        "a{", "a{x}", "a{,3}", "{", "a{1,2", "a{1,", "a{1,x}", "x{ 1}", "x{1 }", "}{",
        "a*+", "a++", "a?+", "a{1,2}+", "a{2}+",
        "(?=a)", "(?!a)", "(?<=a)b", "(?<!a)b", "(?i)a", "(?P<n>a)", "(?#c)", "(?>a)", "(?",
        "\\b", "\\B", "\\A", "\\Z", "\\r", "\\f", "\\v", "\\0", "\\x41", "\\a", "\\e", "\\u0041", "\\N",
        "[\\r]", "[\\b]", "[\\x41]", "[\\1]", "[\\a]",
    ]
    for p in strict:
        _raises(ValueError, lambda: m.compile(p), f"compile({p!r})")
    # ...while their escaped / well-formed counterparts are fine
    _diff_table(m, [
        (r"a\{", ["a{", "a"]),
        (r"\{\}", ["{}"]),
        (r"a{1}\{", ["a{"]),
        (r"x\{1,2\}", ["x{1,2}"]),
        (r"a\*\+", ["a*+"]),
        (r"\+\+", ["++"]),
        (r"\?\+", ["?+"]),
        (r"(?:a\+)+", ["a+a+"]),
        (r"\(\?\:a\)", ["(?:a)"]),
        (r"\\r", ["\\r"]),
        (r"[\\]r", ["r", "\\"]),
        (r"\\b", ["\\b"]),
    ])


# ------------------------------------------------------------------ randomised differential tests
def _gen_strings(rng, alphabet, k, maxlen):
    out = []
    for _ in range(k):
        n = rng.choice([0, 1, 2, 3, 3, 4, 5, 6, maxlen])
        out.append("".join(rng.choice(alphabet) for _ in range(n)))
    return out


def _quant(rng, pq, lazyp=0.3):
    if rng.random() > pq:
        return ""
    q = rng.choice(["*", "+", "?", "*", "+", "?", "{2}", "{0,2}", "{1,}", "{2,3}", "{0}", "{1,2}", "{0,}", "{3}"])
    if rng.random() < lazyp:
        q += "?"
    return q


def _gen_captures(rng, depth):
    """alphabet a/b, groups, alternation of words, quantifiers (greedy/lazy/counted)."""
    def atom(d):
        k = rng.random()
        if k < 0.30:
            return rng.choice(["a", "a", "b", "ab", "ba", "aa", "."])
        if k < 0.38:
            return rng.choice(["[ab]", "[^a]", "\\w"])
        if d <= 0:
            return rng.choice(["a", "b"])
        inner = alt(d - 1)
        return ("(" if k < 0.72 else "(?:") + inner + ")"

    def seq(d):
        return "".join(atom(d) + _quant(rng, 0.55) for _ in range(rng.choice([0, 1, 1, 2, 2, 3])))

    def alt(d):
        return "|".join(seq(d) for _ in range(rng.choice([1, 1, 2, 2, 3])))
    return alt(depth)


def _gen_empty_loops(rng):
    """nullable bodies under quantifiers; the area where re's loop rules differ from textbook engines."""
    bodies = ["a*", "a|", "|a", "a?", "a*|b", "a*b*", "", "a?b?", "(a*)", "a*?", "(?:a|b|)", "b|a*", "a+|", "(a)|", "|(b)", "a?|b"]
    pre = ["", "", "a", "b", "^", "(a)"]
    post = ["", "", "b", "a", "$", "c", "a$", "b*"]

    def loop():
        b = rng.choice(bodies)
        g = "(" if rng.random() < 0.6 else "(?:"
        return g + b + ")" + _quant(rng, 1.0, 0.4)
    parts = [rng.choice(pre)] + [loop() for _ in range(rng.choice([1, 1, 2]))] + [rng.choice(post)]
    if rng.random() < 0.2:
        parts = ["(" + "".join(parts) + ")" + _quant(rng, 0.7)]
    return "".join(parts)


def _gen_classes_anchors(rng, depth):
    atoms = ["a", "b", "_", "1", " ", ".", "\\.", "\\-", "\\n", "\\t", "\\d", "\\D", "\\w", "\\W", "\\s", "\\S", "[ab]", "[^a]", "[a-b1]",
             "[\\d_]", "[]a]", "[^]a]", "[a\\-]", "[-a]", "[\\w ]", "[^\\s]", "[\\S\\n]", "[b-_]", "[\\]a]", "[\\\\a]", "[^\\n]"]

    def atom(d):
        k = rng.random()
        if k < 0.70:
            return rng.choice(atoms) + _quant(rng, 0.45)
        if k < 0.82:
            return rng.choice(["^", "$"])
        if d <= 0:
            return "a"
        return rng.choice(["(", "(?:"]) + alt(d - 1) + ")" + _quant(rng, 0.45)

    def seq(d):
        return "".join(atom(d) for _ in range(rng.choice([1, 2, 2, 3, 4])))

    def alt(d):
        return "|".join(seq(d) for _ in range(rng.choice([1, 1, 2])))
    return alt(depth)


def _random_diff(m, seed, n, gen, alphabet, maxlen=7, maxpat=40):
    rng = random.Random(seed)
    for _ in range(n):
        p = gen(rng)
        while len(p) > maxpat:  # keep patterns small so that `re` itself stays fast
            p = gen(rng)
        try:
            re.compile(p)
        except re.error:
            _raises(ValueError, lambda: m.compile(p), f"compile({p!r})")
            continue
        _diff(m, p, _gen_strings(rng, alphabet, 3, maxlen))


def test_random_captures_diff(m):
    _random_diff(m, 20261014, 3000, lambda r: _gen_captures(r, 3), "aabb", 7, 36)


def test_random_empty_loops_diff(m):
    _random_diff(m, 77001, 4000, _gen_empty_loops, "aab", 6)


def test_random_classes_anchors_diff(m):
    _random_diff(m, 5150, 3000, lambda r: _gen_classes_anchors(r, 2), "ab_1 \n-.\t", 7)


_TOKENS = ["a", "b", "(", ")", "(?:", "[", "]", "[^", "|", "*", "+", "?", ".", "^", "$", "-", "\\d", "\\.", "\\\\", "a-b", ":"]


def test_random_syntax_validity(m):
    """Random token soups: the solution must reject exactly what `re` rejects (restricted to
    constructs where the prompt's dialect agrees with `re`) and agree on matches for the rest."""
    rng = random.Random(424242)
    seen_valid = seen_invalid = 0
    for _ in range(6000):
        p = "".join(rng.choice(_TOKENS) for _ in range(rng.randint(1, 7)))
        if re.search(r"[*+?]\+", p):  # possessive forms: stricter in this dialect
            continue
        try:
            re.compile(p)
            ok = True
        except re.error:
            ok = False
        if ok:
            seen_valid += 1
            _diff(m, p, ["", "ab", "a-b", "ba\n", "a.", "1b"])
        else:
            seen_invalid += 1
            _raises(ValueError, lambda: m.compile(p), f"compile({p!r})")
    assert seen_valid > 800 and seen_invalid > 800


# ------------------------------------------------------------------ scale tests
def test_scale_memoisation(m):
    n = 3000
    # Exponential for naive backtracking; every answer below is derived analytically (re cannot do these).
    a_b = "a" * n + "b"
    # `$` can only match at the very end (or before a final "\n"); the string ends in 'b' preceded by a-run -> never matches.
    _none(m, "(a|aa)+$", a_b, "fullmatch")
    _none(m, "(a|aa)+$", "a" * 400 + "b", "search")
    # 'x' only: there is no 'y' anywhere
    _none(m, "(x+x+)+y", "x" * n, "fullmatch")
    _none(m, "(x+x+)+y", "x" * 300, "search")
    # no 'b' in the subject
    _none(m, "(a*)*b", "a" * n, "fullmatch")
    _none(m, "(a*)*b", "a" * 300, "search")
    _none(m, "(?:a|a)*b", "a" * 2000, "fullmatch")
    _none(m, "(?:a+)+$", "a" * 1000 + "!", "fullmatch")
    # positive scale cases: greedy `a` branch wins every iteration, so group 1 is the last single 'a'
    mt = m.compile("(a|aa)+$").fullmatch("a" * n)
    assert mt is not None and mt.span() == (0, n) and mt.span(1) == (n - 1, n) and mt.group(1) == "a"
    # search: `$` matches before the final "\n"; the match is the a-run
    mt = m.compile("(a|aa)+$").search("a" * 2999 + "\n")
    assert mt is not None and mt.span() == (0, 2999) and mt.group(1) == "a"
    _none(m, "(a|aa)+$", "a" * 2999 + "\n", "fullmatch")
    # (a?){k}a{k} on a^k: the optional parts must all be empty; the last forced iteration is empty at 0
    for k in (6, 10):  # small enough for `re` to confirm the analytic claim in the test itself
        want = re.compile("(a?){%d}a{%d}" % (k, k)).fullmatch("a" * k)
        assert want.span() == (0, k) and want.span(1) == (0, 0)
    for k in (30, 40):
        mt = m.compile("(a?){%d}a{%d}" % (k, k)).fullmatch("a" * k)
        assert mt is not None and mt.span() == (0, k) and mt.span(1) == (0, 0) and mt.group(1) == ""
        _none(m, "(a?){%d}a{%d}" % (k, k), "a" * (k - 1), "fullmatch")
    # nested counted loops with ambiguity: (a{1,3}){2,}$ cannot match a^n b
    _none(m, "(a{1,3}){2,}$", "a" * 600 + "b", "fullmatch")
    _none(m, "(?:a|b|ab)+c", "ab" * 800, "fullmatch")
    mt = m.compile("(?:a|b|ab)+$").fullmatch("ab" * 800)
    assert mt is not None and mt.span() == (0, 1600)


def test_long_input_no_recursion(m):
    n = 5000
    s = "ab" * (n // 2)
    mt = m.compile("(?:ab)*").fullmatch(s)
    assert mt is not None and mt.span() == (0, n)
    mt = m.compile("(a|b)*").fullmatch(s)
    assert mt is not None and mt.span() == (0, n) and mt.groups() == ("b",) and mt.span(1) == (n - 1, n)
    mt = m.compile("(ab)*").fullmatch(s)
    assert mt.groups() == ("ab",) and mt.span(1) == (n - 2, n)
    mt = m.compile("(.)*").fullmatch("a" * n)
    assert mt.span() == (0, n) and mt.span(1) == (n - 1, n)
    mt = m.compile("(a)*?$").fullmatch("a" * n)
    assert mt.span() == (0, n) and mt.span(1) == (n - 1, n)
    mt = m.compile("(?:a|b)*?c").fullmatch("a" * n + "c")
    assert mt is not None and mt.span() == (0, n + 1)
    mt = m.compile("[ab]*c").fullmatch(s + "c")
    assert mt.span() == (0, n + 1)
    mt = m.compile("a*a*a*b").fullmatch("a" * 1500 + "b")
    assert mt is not None and mt.span() == (0, 1501)
    # search over a long string: only index 1 can start the match, and `$` closes it
    mt = m.compile("b(ab)*$").search(s)
    assert mt is not None and mt.span() == (1, n) and mt.span(1) == (n - 2, n)
    mt = m.compile("(x)?c").search("a" * n + "c")
    assert mt.span() == (n, n + 1) and mt.groups() == (None,)
    assert m.compile("c").search("ab" * 2500) is None
    # the failure of a long sequence
    assert m.compile("(?:ab)*c").fullmatch(s) is None
    # a long literal pattern and many groups
    lit = "xy" * 400
    assert m.compile(lit).fullmatch(lit).span() == (0, 800)
    many = m.compile("(a)" * 200).fullmatch("a" * 200)
    assert many.groups() == ("a",) * 200 and many.span(200) == (199, 200)


TESTS = [test_api_and_examples, test_classes_escapes_anchors, test_priority_and_laziness, test_capture_semantics,
         test_empty_iteration_loops, test_invalid_patterns, test_strict_dialect_rejections, test_random_captures_diff,
         test_random_empty_loops_diff, test_random_classes_anchors_diff, test_random_syntax_validity,
         test_scale_memoisation, test_long_input_no_recursion]
