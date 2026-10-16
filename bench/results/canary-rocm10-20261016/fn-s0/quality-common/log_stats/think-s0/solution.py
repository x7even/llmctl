"""Module for summarising web server access logs in Common Log Format."""

import re
from collections import Counter
from typing import Iterable

_MONTHS = {
    "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
    "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
    "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
}

_LINE_RE = re.compile(
    r'^(\S+) (\S+) (\S+) \[([^\]]+)\] "(\S+) (\S+) (\S+)" (\d+) (\d+|-)$'
)

_TS_RE = re.compile(
    r'^(\d{1,2})/([A-Za-z]{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2})\s'
)


def _parse_hour(timestamp: str) -> str | None:
    """Convert '10/Oct/2026:13:55:36 +0000' to '2026-10-10 13'."""
    m = _TS_RE.match(timestamp)
    if not m:
        return None
    day, mon, year, hour, _min, _sec = m.groups()
    mon_num = _MONTHS.get(mon)
    if mon_num is None:
        return None
    return f"{year}-{mon_num}-{int(day):02d} {hour}"


def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0
    ips: set[str] = set()
    status_counter: Counter[int] = Counter()
    bytes_total = 0
    path_counter: Counter[str] = Counter()
    hour_counter: Counter[str] = Counter()

    for line in lines:
        line = line.rstrip("\n").rstrip("\r")
        m = _LINE_RE.match(line)
        if m is None:
            malformed += 1
            continue

        ip, _ident, _user, timestamp, _method, path, _protocol, status_s, bytes_s = m.groups()

        # Validate status (regex already ensures digits, but be explicit)
        try:
            status = int(status_s)
        except ValueError:
            malformed += 1
            continue

        # Bytes: '-' means 0
        if bytes_s == "-":
            nbytes = 0
        else:
            try:
                nbytes = int(bytes_s)
            except ValueError:
                malformed += 1
                continue

        # Strip query string from path
        clean_path = path.split("?", 1)[0]

        # Hour bucket
        hour_key = _parse_hour(timestamp)
        if hour_key is None:
            malformed += 1
            continue

        # All good – record
        total_requests += 1
        ips.add(ip)
        status_counter[status] += 1
        bytes_total += nbytes
        path_counter[clean_path] += 1
        hour_counter[hour_key] += 1

    # Error rate
    if total_requests == 0:
        error_rate = 0.0
    else:
        error_count = sum(c for s, c in status_counter.items() if 400 <= s <= 599)
        error_rate = round(error_count / total_requests, 4)

    # Top 3 paths: sort by count desc, then path asc
    sorted_paths = sorted(path_counter.items(), key=lambda x: (-x[1], x[0]))
    top_paths = sorted_paths[:3]

    return {
        "total_requests": total_requests,
        "malformed": malformed,
        "unique_ips": len(ips),
        "status_counts": dict(status_counter),
        "bytes_total": bytes_total,
        "error_rate": error_rate,
        "top_paths": top_paths,
        "requests_per_hour": dict(hour_counter),
    }
