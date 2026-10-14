"""Summarise a web server access log in Common Log Format."""

from __future__ import annotations

import re
from typing import Iterable

_CLF_RE = re.compile(
    r'^(\S+) (\S+) (\S+) \[([^\]]+)\] "(\S+) (\S+) (\S+)" (\d+) (\d+|-)\s*$'
)

_TS_RE = re.compile(
    r'^(\d{2})/([A-Za-z]{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2}) [+-]\d{4}$'
)

_MONTHS = {
    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12',
}


def _parse_hour_key(ts: str) -> str | None:
    """Return 'YYYY-MM-DD HH' or None if the timestamp is unparseable."""
    m = _TS_RE.match(ts)
    if not m:
        return None
    day, mon, year, hour, _min, _sec = m.groups()
    mon_num = _MONTHS.get(mon)
    if mon_num is None:
        return None
    return f"{year}-{mon_num}-{day} {hour}"


def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0
    ips: set[str] = set()
    status_counts: dict[int, int] = {}
    bytes_total = 0
    error_count = 0
    path_counts: dict[str, int] = {}
    hour_counts: dict[str, int] = {}

    for raw_line in lines:
        line = raw_line.strip()
        m = _CLF_RE.match(line)
        if not m:
            malformed += 1
            continue

        ip, _ident, _user, timestamp, _method, path, _proto, status_str, bytes_str = m.groups()

        hour_key = _parse_hour_key(timestamp)
        if hour_key is None:
            malformed += 1
            continue

        status = int(status_str)
        size = 0 if bytes_str == '-' else int(bytes_str)

        # Strip query string
        if '?' in path:
            path = path.split('?', 1)[0]

        total_requests += 1
        ips.add(ip)
        status_counts[status] = status_counts.get(status, 0) + 1
        bytes_total += size
        if 400 <= status <= 599:
            error_count += 1
        path_counts[path] = path_counts.get(path, 0) + 1
        hour_counts[hour_key] = hour_counts.get(hour_key, 0) + 1

    error_rate = round(error_count / total_requests, 4) if total_requests else 0.0

    top_paths = sorted(path_counts.items(), key=lambda x: (-x[1], x[0]))[:3]

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
