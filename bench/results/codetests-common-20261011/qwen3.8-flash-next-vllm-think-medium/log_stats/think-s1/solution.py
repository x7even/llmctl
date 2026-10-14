"""Analyse web-server access logs in Common Log Format (stdlib only)."""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

_MONTH_MAP: dict[str, str] = {
    "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
    "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
    "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
}

# ip ident user [timestamp] "METHOD path PROTOCOL" status bytes
_LOG_RE = re.compile(
    r'^(\S+)'       # ip
    r' (\S+)'       # ident
    r' (\S+)'       # user
    r' \[([^\]]+)\]'  # [timestamp]
    r' "(\S+) (\S+) (\S+)"'  # "METHOD path PROTOCOL"
    r' (\d+)'       # status (must be numeric)
    r' (-|\d+)'     # bytes (number or '-')
    r'$'
)


def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0
    ips: set[str] = set()
    status_counts: Counter[int] = Counter()
    bytes_total: int = 0
    path_counts: Counter[str] = Counter()
    hour_counts: Counter[str] = Counter()

    for line in lines:
        line = line.rstrip("\n\r")
        m = _LOG_RE.match(line)
        if m is None:
            malformed += 1
            continue

        ip, _ident, _user, timestamp, _method, path, _proto, status_str, bytes_str = m.groups()

        total_requests += 1
        ips.add(ip)

        status = int(status_str)
        status_counts[status] += 1

        bytes_total += 0 if bytes_str == "-" else int(bytes_str)

        # Strip query-string for path counting
        path_no_qs = path.split("?", 1)[0]
        path_counts[path_no_qs] += 1

        # Parse timestamp "10/Oct/2026:13:55:36 +0000" → "2026-10-10 13"
        date_time = timestamp.split()[0]  # "10/Oct/2026:13:55:36"
        day_str, rest = date_time.split("/", 1)
        month_str, rest = rest.split("/", 1)
        year_str, time_part = rest.split(":", 1)
        hour_str = time_part.split(":")[0]

        month_num = _MONTH_MAP.get(month_str)
        if month_num is not None:
            hour_key = f"{year_str}-{month_num}-{day_str} {hour_str}"
            hour_counts[hour_key] += 1

    # Top 3 paths: count desc, path asc
    top_paths = sorted(path_counts.items(), key=lambda x: (-x[1], x[0]))[:3]

    # Error rate (400-599)
    if total_requests > 0:
        error_count = sum(v for k, v in status_counts.items() if 400 <= k <= 599)
        error_rate = round(error_count / total_requests, 4)
    else:
        error_rate = 0.0

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
