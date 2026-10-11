"""Hidden tests for log_stats. Each test takes the loaded solution module `m`."""

LOG = [
    '127.0.0.1 - frank [10/Oct/2026:13:55:36 +0000] "GET /index.html HTTP/1.1" 200 2326',
    '127.0.0.1 - - [10/Oct/2026:13:58:01 +0000] "GET /about?ref=nav HTTP/1.1" 200 512',
    '10.0.0.7 - - [10/Oct/2026:14:02:11 +0000] "POST /api/login HTTP/1.1" 401 -',
    '10.0.0.7 - - [10/Oct/2026:14:03:45 +0000] "POST /api/login HTTP/1.1" 200 150',
    '192.168.1.5 - bob [11/Oct/2026:00:00:05 +0200] "GET /index.html HTTP/1.1" 404 0',
    '192.168.1.5 - bob [11/Oct/2026:00:10:05 +0200] "GET /missing HTTP/1.1" 500 99',
]


def test_totals(m):
    r = m.analyze_log(LOG)
    assert r["total_requests"] == 6
    assert r["malformed"] == 0
    assert r["unique_ips"] == 3
    assert r["bytes_total"] == 2326 + 512 + 0 + 150 + 0 + 99


def test_status_counts(m):
    r = m.analyze_log(LOG)
    assert r["status_counts"] == {200: 3, 401: 1, 404: 1, 500: 1}


def test_error_rate(m):
    assert m.analyze_log(LOG)["error_rate"] == 0.5
    one_bad = LOG[:2] + [LOG[2]]
    assert m.analyze_log(one_bad)["error_rate"] == 0.3333


def test_top_paths(m):
    r = m.analyze_log(LOG)
    assert r["top_paths"] == [("/api/login", 2), ("/index.html", 2), ("/about", 1)]


def test_query_string_stripped(m):
    lines = [
        '1.1.1.1 - - [01/Jan/2026:10:00:00 +0000] "GET /a?x=1 HTTP/1.1" 200 1',
        '1.1.1.1 - - [01/Jan/2026:10:00:01 +0000] "GET /a?x=2 HTTP/1.1" 200 1',
        '1.1.1.1 - - [01/Jan/2026:10:00:02 +0000] "GET /a HTTP/1.1" 200 1',
    ]
    assert m.analyze_log(lines)["top_paths"] == [("/a", 3)]


def test_requests_per_hour(m):
    r = m.analyze_log(LOG)
    assert r["requests_per_hour"] == {
        "2026-10-10 13": 2, "2026-10-10 14": 2, "2026-10-11 00": 2,
    }


def test_malformed_lines(m):
    lines = LOG[:2] + ["", "garbage", '1.2.3.4 - - [bad] "GET / HTTP/1.1" 200 5',
                       '1.2.3.4 - - [10/Oct/2026:13:55:36 +0000] "GET / HTTP/1.1" abc 5'] + LOG[2:3]
    r = m.analyze_log(lines)
    assert r["total_requests"] == 3
    assert r["malformed"] == 4


def test_empty_input(m):
    r = m.analyze_log([])
    assert r["total_requests"] == 0 and r["malformed"] == 0 and r["unique_ips"] == 0
    assert r["status_counts"] == {} and r["bytes_total"] == 0
    assert r["error_rate"] == 0.0 and r["top_paths"] == [] and r["requests_per_hour"] == {}


def test_fewer_than_three_paths(m):
    r = m.analyze_log(LOG[:1])
    assert r["top_paths"] == [("/index.html", 1)]


def test_accepts_generator_and_newlines(m):
    r = m.analyze_log(l + "\n" for l in LOG)
    assert r["total_requests"] == 6 and r["malformed"] == 0


def test_return_keys(m):
    r = m.analyze_log(LOG)
    assert set(r) == {"total_requests", "malformed", "unique_ips", "status_counts",
                      "bytes_total", "error_rate", "top_paths", "requests_per_hour"}


TESTS = [test_totals, test_status_counts, test_error_rate, test_top_paths, test_query_string_stripped,
         test_requests_per_hour, test_malformed_lines, test_empty_input, test_fewer_than_three_paths,
         test_accepts_generator_and_newlines, test_return_keys]
