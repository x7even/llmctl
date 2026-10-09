import re
from collections import Counter
from typing import Iterable

_MONTHS = {
    "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
    "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
    "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
}

_LOG_RE = re.compile(
    r'^(\S+) (\S+) (\S+) \[([^\]]+)\] "(\S+) (\S+) (\S+)" (\d+) (\d+|-)$'
)

_TS_RE = re.compile(r'^(\d{2})/([A-Za-z]{3})/(\d{4}):(\d{2}):\d{2}:\d{2}')


def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0
    ips = set()
    status_counts = Counter()
    bytes_total = 0
    path_counts = Counter()
    hour_counts = Counter()

    for line in lines:
        line = line.rstrip("\n").rstrip("\r")
        m = _LOG_RE.match(line)
        if not m:
            malformed += 1
            continue

        ip, _ident, _user, timestamp, _method, raw_path, _proto, status_str, bytes_str = m.groups()

        # Validate timestamp structure and month
        ts_match = _TS_RE.match(timestamp)
        if not ts_match:
            malformed += 1
            continue
        day, mon, year, hour = ts_match.groups()
        mon_key = mon.capitalize()
        if mon_key not in _MONTHS:
            malformed += 1
            continue

        status = int(status_str)
        b = 0 if bytes_str == "-" else int(bytes_str)

        total_requests += 1
        ips.add(ip)
        status_counts[status] += 1
        bytes_total += b

        # Strip query string
        path = raw_path.split("?", 1)[0]
        path_counts[path] += 1

        hour_key = f"{year}-{_MONTHS[mon_key]}-{day} {hour}"
        hour_counts[hour_key] += 1

    # Error rate
    if total_requests == 0:
        error_rate = 0.0
    else:
        error_count = sum(c for s, c in status_counts.items() if 400 <= s <= 599)
        error_rate = round(error_count / total_requests, 4)

    # Top 3 paths: count descending, then path ascending
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
