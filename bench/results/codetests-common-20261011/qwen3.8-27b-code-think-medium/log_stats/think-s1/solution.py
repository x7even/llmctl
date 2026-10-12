"""Module to summarise a web server access log in Common Log Format."""

import re
from collections import Counter
from typing import Iterable, Optional

_MONTHS = {
    "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
    "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
    "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
}

_LOG_RE = re.compile(
    r'^(\S+) (\S+) (\S+) \[([^\]]+)\] "(\S+) (\S+) (\S+)" (\d+) (\d+|-)\s*$'
)


def _parse_hour(timestamp: str) -> Optional[str]:
    """Parse a CLF timestamp (e.g. '10/Oct/2026:13:55:36 +0000') into 'YYYY-MM-DD HH'."""
    try:
        parts = timestamp.split(" ")
        if len(parts) != 2:
            return None
        date_part = parts[0]
        segs = date_part.split("/")
        if len(segs) != 3:
            return None
        day, mon, rest = segs
        time_segs = rest.split(":")
        if len(time_segs) != 4:
            return None
        year, hour, _minute, _second = time_segs
        mon_str = _MONTHS.get(mon)
        if mon_str is None:
            return None
        if not (day.isdigit() and year.isdigit() and hour.isdigit()):
            return None
        return f"{year}-{mon_str}-{day} {hour}"
    except (ValueError, IndexError):
        return None


def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0
    ips = set()
    status_counts: Counter = Counter()
    bytes_total = 0
    path_counts: Counter = Counter()
    hour_counts: Counter = Counter()
    error_count = 0

    for line in lines:
        stripped = line.strip()
        m = _LOG_RE.match(stripped)
        if m is None:
            malformed += 1
            continue

        ip, _ident, _user, timestamp, _method, path, _protocol, status_str, bytes_str = m.groups()

        hour_key = _parse_hour(timestamp)
        if hour_key is None:
            malformed += 1
            continue

        status = int(status_str)
        bytes_val = 0 if bytes_str == "-" else int(bytes_str)

        total_requests += 1
        ips.add(ip)
        status_counts[status] += 1
        bytes_total += bytes_val

        if 400 <= status <= 599:
            error_count += 1

        clean_path = path.split("?", 1)[0]
        path_counts[clean_path] += 1
        hour_counts[hour_key] += 1

    error_rate = round(error_count / total_requests, 4) if total_requests > 0 else 0.0
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
