"""Module to summarise a web server access log in Common Log Format."""

from __future__ import annotations

import re
from typing import Iterable

_CLF_RE = re.compile(
    r'^(\S+) (\S+) (\S+) \[([^\]]+)\] "(\S+) (\S+) (\S+)" (\d+) (\d+|-)\s*$'
)

_TS_RE = re.compile(
    r'^(\d{1,2})/([A-Za-z]{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2}) [+-]\d{4}$'
)

_MONTHS = {
    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12',
}


def analyze_log(lines: Iterable[str]) -> dict:
    """Summarise a web server access log in Common Log Format.

    Parameters
    ----------
    lines : Iterable[str]
        An iterable of log lines (one CLF entry per line).

    Returns
    -------
    dict
        A summary dict with keys: total_requests, malformed, unique_ips,
        status_counts, bytes_total, error_rate, top_paths, requests_per_hour.
    """
    total_requests = 0
    malformed = 0
    ips: set[str] = set()
    status_counts: dict[int, int] = {}
    bytes_total = 0
    error_count = 0
    path_counts: dict[str, int] = {}
    hour_counts: dict[str, int] = {}

    for raw_line in lines:
        line = raw_line.rstrip('\r\n')

        m = _CLF_RE.match(line)
        if m is None:
            malformed += 1
            continue

        ip, _ident, _user, timestamp, _method, path, _proto, status_str, bytes_str = m.groups()

        # Validate timestamp structure
        ts_m = _TS_RE.match(timestamp)
        if ts_m is None:
            malformed += 1
            continue

        day_s, mon_s, year_s, hour_s, _min, _sec = ts_m.groups()

        if mon_s not in _MONTHS:
            malformed += 1
            continue

        status = int(status_str)
        nbytes = 0 if bytes_str == '-' else int(bytes_str)

        # --- accumulate ---
        total_requests += 1
        ips.add(ip)
        status_counts[status] = status_counts.get(status, 0) + 1
        bytes_total += nbytes

        if 400 <= status <= 599:
            error_count += 1

        # Path without query string
        clean_path = path.split('?', 1)[0]
        path_counts[clean_path] = path_counts.get(clean_path, 0) + 1

        # Hour bucket: "YYYY-MM-DD HH"
        hour_key = f"{year_s}-{_MONTHS[mon_s]}-{int(day_s):02d} {hour_s}"
        hour_counts[hour_key] = hour_counts.get(hour_key, 0) + 1

    # Error rate
    if total_requests > 0:
        error_rate = round(error_count / total_requests, 4)
    else:
        error_rate = 0.0

    # Top 3 paths: sort by count desc, then path asc
    sorted_paths = sorted(path_counts.items(), key=lambda x: (-x[1], x[0]))
    top_paths = sorted_paths[:3]

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
