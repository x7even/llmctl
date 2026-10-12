"""Module to summarise a web server access log in Common Log Format."""

from collections import Counter
from typing import Iterable, Dict, List, Tuple
import re

_CLF_RE = re.compile(
    r'^(\S+) (\S+) (\S+) \[([^\]]+)\] "([^"]*)" (\S+) (\S+)\s*$'
)

_TS_RE = re.compile(
    r'^(\d{1,2})/([A-Za-z]{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2})'
)

_MONTHS = {
    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12',
}

_INT_RE = re.compile(r'^\d+$')


def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0
    ips: set = set()
    status_counts: Counter = Counter()
    bytes_total = 0
    paths: Counter = Counter()
    requests_per_hour: Counter = Counter()

    for line in lines:
        line = line.rstrip('\r\n')
        if not line.strip():
            malformed += 1
            continue

        m = _CLF_RE.match(line)
        if not m:
            malformed += 1
            continue

        ip, _ident, _user, timestamp, request, status_str, bytes_str = m.groups()

        # Validate status is a non-negative integer
        if not _INT_RE.match(status_str):
            malformed += 1
            continue
        status = int(status_str)

        # Validate bytes: integer or '-'
        if bytes_str != '-' and not _INT_RE.match(bytes_str):
            malformed += 1
            continue
        bytes_val = 0 if bytes_str == '-' else int(bytes_str)

        # Request must contain at least method and path
        req_parts = request.split()
        if len(req_parts) < 2:
            malformed += 1
            continue
        path_full = req_parts[1]
        path = path_full.split('?', 1)[0]

        # Parse timestamp
        ts_m = _TS_RE.match(timestamp)
        if not ts_m:
            malformed += 1
            continue
        day, mon, year, hour = ts_m.group(1), ts_m.group(2), ts_m.group(3), ts_m.group(4)
        if mon not in _MONTHS:
            malformed += 1
            continue
        month_num = _MONTHS[mon]
        hour_key = f"{year}-{month_num}-{day} {hour}"

        # All checks passed – record the valid request
        total_requests += 1
        ips.add(ip)
        status_counts[status] += 1
        bytes_total += bytes_val
        paths[path] += 1
        requests_per_hour[hour_key] += 1

    # Error rate
    error_count = sum(c for s, c in status_counts.items() if 400 <= s <= 599)
    error_rate = round(error_count / total_requests, 4) if total_requests else 0.0

    # Top 3 paths: count descending, then path ascending
    top_paths: List[Tuple[str, int]] = sorted(
        paths.items(), key=lambda x: (-x[1], x[0])
    )[:3]

    return {
        "total_requests": total_requests,
        "malformed": malformed,
        "unique_ips": len(ips),
        "status_counts": dict(status_counts),
        "bytes_total": bytes_total,
        "error_rate": error_rate,
        "top_paths": top_paths,
        "requests_per_hour": dict(requests_per_hour),
    }
