"""Summarise a web-server access log in Common Log Format (standard library only)."""

import re
from collections import Counter
from typing import Iterable

__all__ = ["analyze_log"]

_LOG_RE = re.compile(
    r'^(\S+) (\S+) (\S+) \[([^\]]+)\] "(\S+) (\S+) (\S+)" (\d+) (\d+|-)$'
)

_TS_RE = re.compile(
    r'^(\d{2})/([A-Za-z]{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2}) [+-]\d{4}$'
)

_MONTHS: dict[str, str] = {
    "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
    "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
    "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
}


def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0
    ips: set[str] = set()
    status_counts: Counter[int] = Counter()
    bytes_total = 0
    error_count = 0
    path_counter: Counter[str] = Counter()
    hour_counter: Counter[str] = Counter()

    for raw in lines:
        line = raw.rstrip("\r\n")
        m = _LOG_RE.match(line)
        if m is None:
            malformed += 1
            continue

        ip = m.group(1)
        timestamp_str = m.group(4)
        path_raw = m.group(6)
        status = int(m.group(8))
        bytes_str = m.group(9)

        # --- validate & parse timestamp ---
        ts = _TS_RE.match(timestamp_str)
        if ts is None:
            malformed += 1
            continue
        day, mon_abbr, year, hour, _min, _sec = ts.groups()
        mon = _MONTHS.get(mon_abbr)
        if mon is None:
            malformed += 1
            continue

        # --- valid line: accumulate ---
        total_requests += 1
        ips.add(ip)
        status_counts[status] += 1

        nbytes = 0 if bytes_str == "-" else int(bytes_str)
        bytes_total += nbytes

        if 400 <= status <= 599:
            error_count += 1

        # strip query string
        path_clean = path_raw.split("?", 1)[0]
        path_counter[path_clean] += 1

        # "YYYY-MM-DD HH"
        hour_key = f"{year}-{mon}-{day} {hour}"
        hour_counter[hour_key] += 1

    # --- derived metrics ---
    error_rate = (
        round(error_count / total_requests, 4) if total_requests else 0.0
    )

    top_paths = sorted(
        path_counter.items(), key=lambda x: (-x[1], x[0])
    )[:3]

    return {
        "total_requests": total_requests,
        "malformed": malformed,
        "unique_ips": len(ips),
        "status_counts": dict(status_counts),
        "bytes_total": bytes_total,
        "error_rate": error_rate,
        "top_paths": top_paths,
        "requests_per_hour": dict(hour_counter),
    }
