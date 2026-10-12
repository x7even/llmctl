"""Module to summarise a web-server access log in Common Log Format."""

import re
from collections import Counter
from typing import Iterable

_MONTHS = {
    "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
    "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
    "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
}

_LOG_RE = re.compile(
    r'^(\S+) (\S+) (\S+) \[([^\]]+)\] "(\S+) (\S+) (\S+)" (\d+) (\d+|-)$'
)


def _parse_hour_key(timestamp: str) -> str | None:
    """Convert '10/Oct/2026:13:55:36 +0000' → '2026-10-10 13', or None."""
    parts = timestamp.split(":")
    if len(parts) < 2:
        return None
    date_part = parts[0]
    hour_str = parts[1]

    date_components = date_part.split("/")
    if len(date_components) != 3:
        return None

    day_str, month_abbr, year = date_components
    month_num = _MONTHS.get(month_abbr)
    if month_num is None:
        return None

    try:
        day = int(day_str)
        hour = int(hour_str)
    except ValueError:
        return None

    return f"{year}-{month_num}-{day:02d} {hour:02d}"


def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0
    ips: set[str] = set()
    status_counts: Counter[int] = Counter()
    bytes_total = 0
    error_count = 0
    path_counts: Counter[str] = Counter()
    hour_counts: Counter[str] = Counter()

    for line in lines:
        line = line.rstrip("\n\r")
        m = _LOG_RE.match(line)
        if m is None:
            malformed += 1
            continue

        ip, _ident, _user, timestamp, _method, path, _proto, status_str, bytes_str = m.groups()

        # Validate / parse timestamp
        hour_key = _parse_hour_key(timestamp)
        if hour_key is None:
            malformed += 1
            continue

        status = int(status_str)
        nbytes = 0 if bytes_str == "-" else int(bytes_str)

        # Strip query string from path
        path_no_query = path.split("?", 1)[0]

        total_requests += 1
        ips.add(ip)
        status_counts[status] += 1
        bytes_total += nbytes
        if 400 <= status <= 599:
            error_count += 1
        path_counts[path_no_query] += 1
        hour_counts[hour_key] += 1

    # Error rate
    if total_requests > 0:
        error_rate = round(error_count / total_requests, 4)
    else:
        error_rate = 0.0

    # Top 3 paths: count desc, then path asc
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
