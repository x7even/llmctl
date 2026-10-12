"""Web server access log analyser (Common Log Format)."""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

_CLF_RE = re.compile(
    r'^(\S+) (\S+) (\S+) '
    r'\[([^\]]+)\] '
    r'"(\S+) (\S+) (\S+)" '
    r'(\S+) (\S+)$'
)

_TS_RE = re.compile(
    r'^(\d{2})/([A-Za-z]{3})/(\d{4}):(\d{2}):\d{2}:\d{2}'
)

_MONTHS = {
    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12',
}


def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0
    ips: set[str] = set()
    status_counts: Counter[int] = Counter()
    bytes_total = 0
    path_counts: Counter[str] = Counter()
    hour_counts: Counter[str] = Counter()

    for raw in lines:
        line = raw.rstrip('\r\n')

        m = _CLF_RE.match(line)
        if m is None:
            malformed += 1
            continue

        ip, _ident, _user, timestamp, _method, path, _proto, status_str, bytes_str = m.groups()

        # status must be a non-negative integer
        if not status_str.isdigit():
            malformed += 1
            continue
        status = int(status_str)

        # bytes must be '-' or a non-negative integer
        if bytes_str == '-':
            bytes_val = 0
        elif bytes_str.isdigit():
            bytes_val = int(bytes_str)
        else:
            malformed += 1
            continue

        # ---- valid line ----
        total_requests += 1
        ips.add(ip)
        status_counts[status] += 1
        bytes_total += bytes_val

        # path without query string
        clean_path = path.split('?', 1)[0]
        path_counts[clean_path] += 1

        # hour bucket
        ts_m = _TS_RE.match(timestamp)
        if ts_m:
            day, mon, year, hour = ts_m.groups()
            mon_str = _MONTHS.get(mon)
            if mon_str is not None:
                hour_counts[f"{year}-{mon_str}-{day} {hour}"] += 1

    # error rate
    if total_requests > 0:
        error_count = sum(c for s, c in status_counts.items() if 400 <= s <= 599)
        error_rate = round(error_count / total_requests, 4)
    else:
        error_rate = 0.0

    # top 3 paths: count desc, then path asc
    top_paths = sorted(path_counts.items(), key=lambda x: (-x[1], x[0]))[:3]

    return {
        "total_requests": total_requests,
        "malformed": malformed,
        "unique_ips": len(ips),
        "status_counts": dict(status_counts),
        "bytes_total": bytes_total,
        "error_rate": error_rate,
        "top_paths": top_paths,
        "requests_per_hour": dict(hour_counts),
    }
