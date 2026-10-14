"""Summarise a web server access log in Common Log Format (CLF)."""

import re
from collections import Counter
from typing import Iterable

_CLF_RE = re.compile(
    r'^(\S+) (\S+) (\S+) \[([^\]]+)\] "(\S+) (\S+) (\S+)" (\d+) (\d+|-)\s*$'
)

_TS_RE = re.compile(
    r'^(\d{1,2})/(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'
    r'/(\d{4}):(\d{2}):(\d{2}):(\d{2}) [+-]\d{4}$'
)

_MONTHS = {
    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12',
}


def _parse_timestamp(ts: str) -> str | None:
    """Return 'YYYY-MM-DD HH' or None if the timestamp is not valid CLF."""
    m = _TS_RE.match(ts)
    if not m:
        return None
    day, mon, year, hour, _min, _sec = m.groups()
    return f"{year}-{_MONTHS[mon]}-{day.zfill(2)} {hour}"


def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0
    ips: set[str] = set()
    status_counts: dict[int, int] = {}
    bytes_total = 0
    error_count = 0
    path_counts: Counter[str] = Counter()
    hour_counts: Counter[str] = Counter()

    for line in lines:
        m = _CLF_RE.match(line)
        if not m:
            malformed += 1
            continue

        ip = m.group(1)
        timestamp = m.group(4)
        path = m.group(6)
        status = int(m.group(8))
        bytes_field = m.group(9)
        bytes_val = 0 if bytes_field == '-' else int(bytes_field)

        hour_key = _parse_timestamp(timestamp)
        if hour_key is None:
            malformed += 1
            continue

        # --- valid line ---
        total_requests += 1
        ips.add(ip)
        status_counts[status] = status_counts.get(status, 0) + 1
        bytes_total += bytes_val

        if 400 <= status <= 599:
            error_count += 1

        clean_path = path.split('?', 1)[0]
        path_counts[clean_path] += 1
        hour_counts[hour_key] += 1

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
        "requests_per_hour": dict(hour_counts),
    }
