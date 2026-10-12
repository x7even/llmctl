"""Module for summarising web-server access logs in Common Log Format."""

import re
from collections import Counter
from typing import Iterable

_LOG_RE = re.compile(
    r'^(\S+)\s+(\S+)\s+(\S+)\s+\[([^\]]+)\]\s+"(\S+)\s+(\S+)\s+(\S+)"\s+(\d+)\s+(-|\d+)$'
)

_TS_RE = re.compile(
    r'^(\d{2})/([A-Za-z]{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2})\s+[+-]\d{4}$'
)

_MONTHS = {
    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12',
}


def analyze_log(lines: Iterable[str]) -> dict:
    """Summarise a CLF access log.

    Parameters
    ----------
    lines : Iterable[str]
        Each element is one log line (may or may not include a trailing newline).

    Returns
    -------
    dict
        Summary with keys: total_requests, malformed, unique_ips,
        status_counts, bytes_total, error_rate, top_paths, requests_per_hour.
    """
    total_requests = 0
    malformed = 0
    ips: set = set()
    status_counts: Counter = Counter()
    bytes_total = 0
    error_count = 0
    path_counter: Counter = Counter()
    hour_counter: Counter = Counter()

    for raw_line in lines:
        line = raw_line.rstrip('\n\r')

        # Blank / whitespace-only lines are malformed.
        if not line or line.isspace():
            malformed += 1
            continue

        m = _LOG_RE.match(line)
        if m is None:
            malformed += 1
            continue

        ip, _ident, _user, timestamp, _method, path, _protocol, status_str, bytes_str = m.groups()

        # Status is guaranteed numeric by the regex (\d+), but guard anyway.
        try:
            status = int(status_str)
        except ValueError:
            malformed += 1
            continue

        # Bytes: '-' means 0, otherwise must be a non-negative integer.
        if bytes_str == '-':
            nbytes = 0
        else:
            try:
                nbytes = int(bytes_str)
            except ValueError:
                malformed += 1
                continue

        # Validate timestamp structure and month abbreviation.
        ts_m = _TS_RE.match(timestamp)
        if ts_m is None:
            malformed += 1
            continue

        day, mon, year, hour, _min, _sec = ts_m.groups()
        mon_num = _MONTHS.get(mon)
        if mon_num is None:
            malformed += 1
            continue

        # --- This line is valid ---
        total_requests += 1
        ips.add(ip)
        status_counts[status] += 1
        bytes_total += nbytes

        if 400 <= status <= 599:
            error_count += 1

        # Strip query string for path counting.
        clean_path = path.split('?', 1)[0]
        path_counter[clean_path] += 1

        hour_key = f"{year}-{mon_num}-{day} {hour}"
        hour_counter[hour_key] += 1

    # Derived metrics
    if total_requests > 0:
        error_rate = round(error_count / total_requests, 4)
    else:
        error_rate = 0.0

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
