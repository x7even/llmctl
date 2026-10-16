"""Summarise a web server access log in Common Log Format (standard library only)."""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Tuple

_MONTHS: Dict[str, int] = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

_LOG_RE = re.compile(
    r'^(\S+)\s+(\S+)\s+(\S+)\s+'
    r'\[([^\]]+)\]\s+'
    r'"(\S+)\s+(\S+)\s+(\S+)"\s+'
    r'(\d+)\s+'
    r'(\d+|-)\s*$'
)

_TS_RE = re.compile(
    r'^(\d{2})/([A-Za-z]{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2})\s+[+-]\d{4}$'
)


def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0
    ips: set = set()
    status_counts: Dict[int, int] = {}
    bytes_total = 0
    error_count = 0
    path_counts: Dict[str, int] = {}
    hour_counts: Dict[str, int] = {}

    for raw_line in lines:
        line = raw_line.strip()

        if not line:
            malformed += 1
            continue

        m = _LOG_RE.match(line)
        if m is None:
            malformed += 1
            continue

        ip, _ident, _user, timestamp, _method, path, _protocol, status_str, bytes_str = m.groups()

        # Validate / parse timestamp
        ts_m = _TS_RE.match(timestamp)
        if ts_m is None:
            malformed += 1
            continue
        day, mon, year, hour, _min, _sec = ts_m.groups()
        if mon not in _MONTHS:
            malformed += 1
            continue

        status = int(status_str)
        size = 0 if bytes_str == "-" else int(bytes_str)

        # Accumulate
        total_requests += 1
        ips.add(ip)
        status_counts[status] = status_counts.get(status, 0) + 1
        bytes_total += size

        if 400 <= status <= 599:
            error_count += 1

        clean_path = path.split("?", 1)[0]
        path_counts[clean_path] = path_counts.get(clean_path, 0) + 1

        hour_key = f"{year}-{_MONTHS[mon]:02d}-{day} {hour}"
        hour_counts[hour_key] = hour_counts.get(hour_key, 0) + 1

    error_rate = round(error_count / total_requests, 4) if total_requests else 0.0

    top_paths: List[Tuple[str, int]] = sorted(
        path_counts.items(), key=lambda item: (-item[1], item[0])
    )[:3]

    return {
        "total_requests": total_requests,
        "malformed": malformed,
        "unique_ips": len(ips),
        "status_counts": status_counts,
        "bytes_total": bytes_total,
        "error_rate": error_rate,
        "top_paths": top_paths,
        "requests_per_hour": hour_counts,
    }
