"""Web server access log analyser (Common Log Format)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Iterable

_CLF_RE = re.compile(
    r'^(\S+) (\S+) (\S+) \[([^\]]+)\] "(\S+) (\S+) (\S+)" (\d+) (\d+|-)\s*$'
)


def analyze_log(lines: Iterable[str]) -> dict:
    """Summarise a web server access log in Common Log Format.

    Parameters
    ----------
    lines : Iterable[str]
        An iterable of log lines (one entry per line).

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
    requests_per_hour: dict[str, int] = {}

    for raw_line in lines:
        line = raw_line.rstrip('\r\n')

        # Blank / whitespace-only lines are malformed
        if not line.strip():
            malformed += 1
            continue

        m = _CLF_RE.match(line)
        if m is None:
            malformed += 1
            continue

        ip, _ident, _user, timestamp, _method, path, _protocol, status_str, bytes_str = m.groups()

        # Validate the timestamp (must be parseable as DD/Mon/YYYY:HH:MM:SS)
        try:
            date_part = timestamp.split(' ', 1)[0]
            dt = datetime.strptime(date_part, '%d/%b/%Y:%H:%M:%S')
            hour_key = dt.strftime('%Y-%m-%d %H')
        except (ValueError, IndexError):
            malformed += 1
            continue

        status = int(status_str)
        size = 0 if bytes_str == '-' else int(bytes_str)

        # --- accumulate statistics ---
        total_requests += 1
        ips.add(ip)
        status_counts[status] = status_counts.get(status, 0) + 1
        bytes_total += size

        if 400 <= status <= 599:
            error_count += 1

        clean_path = path.split('?', 1)[0]
        path_counts[clean_path] = path_counts.get(clean_path, 0) + 1

        requests_per_hour[hour_key] = requests_per_hour.get(hour_key, 0) + 1

    # Error rate
    error_rate = round(error_count / total_requests, 4) if total_requests else 0.0

    # Top 3 paths: count descending, then path ascending
    sorted_paths = sorted(path_counts.items(), key=lambda item: (-item[1], item[0]))
    top_paths: list[tuple[str, int]] = sorted_paths[:3]

    return {
        "total_requests": total_requests,
        "malformed": malformed,
        "unique_ips": len(ips),
        "status_counts": status_counts,
        "bytes_total": bytes_total,
        "error_rate": error_rate,
        "top_paths": top_paths,
        "requests_per_hour": requests_per_hour,
    }
