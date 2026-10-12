"""Summarise a web server access log in Common Log Format."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

_CLF_RE = re.compile(
    r'^(\S+) (\S+) (\S+) \[([^\]]+)\] "(\S+) (\S+) (\S+)" (\d+) (\d+|-)\s*$'
)

_MONTHS: dict[str, int] = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def analyze_log(lines: Iterable[str]) -> dict:
    """Parse CLF log *lines* and return a summary dictionary."""
    total_requests = 0
    malformed = 0
    ips: set[str] = set()
    status_counts: Counter[int] = Counter()
    bytes_total = 0
    path_counts: Counter[str] = Counter()
    hour_counts: Counter[str] = Counter()
    error_count = 0

    for line in lines:
        m = _CLF_RE.match(line)
        if m is None:
            malformed += 1
            continue

        ip = m.group(1)
        timestamp = m.group(4)
        path = m.group(6)
        status = int(m.group(8))
        size = 0 if m.group(9) == "-" else int(m.group(9))

        total_requests += 1
        ips.add(ip)
        status_counts[status] += 1
        bytes_total += size

        if 400 <= status <= 599:
            error_count += 1

        # Strip query string for path aggregation
        clean_path = path.split("?", 1)[0]
        path_counts[clean_path] += 1

        # Parse timestamp: DD/Mon/YYYY:HH:MM:SS +ZZZZ
        try:
            date_part, _tz = timestamp.rsplit(" ", 1)
            day_s, mon_s, rest = date_part.split("/", 2)
            year_s, time_s = rest.split(":", 1)
            hour_s = time_s.split(":", 1)[0]

            mon_num = _MONTHS.get(mon_s)
            if mon_num is not None:
                hour_key = f"{year_s}-{mon_num:02d}-{int(day_s):02d} {hour_s}"
                hour_counts[hour_key] += 1
        except (ValueError, IndexError):
            pass

    error_rate = round(error_count / total_requests, 4) if total_requests else 0.0

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
