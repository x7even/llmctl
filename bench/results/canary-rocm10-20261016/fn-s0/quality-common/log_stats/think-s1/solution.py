import re
from collections import Counter
from typing import Iterable

_MONTHS = {
    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12',
}

_LOG_RE = re.compile(
    r'^(\S+)\s+(\S+)\s+(\S+)\s+\[([^\]]+)\]\s+"([^"]*)"\s+(\S+)\s+(\S+)$'
)

_TS_RE = re.compile(
    r'^(\d{2})/(\w{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2})\s+\S+$'
)


def analyze_log(lines: Iterable[str]) -> dict:
    total = 0
    malformed = 0
    ips: set = set()
    status_counts: Counter = Counter()
    bytes_total = 0
    path_counts: Counter = Counter()
    hour_counts: Counter = Counter()

    for line in lines:
        line = line.strip()
        if not line:
            malformed += 1
            continue

        m = _LOG_RE.match(line)
        if m is None:
            malformed += 1
            continue

        ip, _ident, _user, timestamp, request, status_str, bytes_str = m.groups()

        # Validate status is numeric
        if not status_str.isdigit():
            malformed += 1
            continue

        # Validate / normalise bytes
        if bytes_str == '-':
            nbytes = 0
        elif bytes_str.isdigit():
            nbytes = int(bytes_str)
        else:
            malformed += 1
            continue

        # Parse the request line: must be "METHOD path PROTOCOL"
        parts = request.split()
        if len(parts) != 3:
            malformed += 1
            continue

        # Strip query string from path
        path = parts[1].split('?')[0]

        # Parse timestamp (ignore timezone offset)
        ts_m = _TS_RE.match(timestamp)
        if ts_m is None:
            malformed += 1
            continue

        day, mon, year, hour, _min, _sec = ts_m.groups()
        if mon not in _MONTHS:
            malformed += 1
            continue

        hour_key = f"{year}-{_MONTHS[mon]}-{day} {hour}"

        # Line is valid – accumulate
        total += 1
        ips.add(ip)
        status = int(status_str)
        status_counts[status] += 1
        bytes_total += nbytes
        path_counts[path] += 1
        hour_counts[hour_key] += 1

    # Error rate: fraction of valid requests with status 400-599
    error_count = sum(c for s, c in status_counts.items() if 400 <= s <= 599)
    error_rate = round(error_count / total, 4) if total > 0 else 0.0

    # Top 3 paths: sort by count descending, then path ascending
    top_paths = sorted(path_counts.items(), key=lambda x: (-x[1], x[0]))[:3]

    return {
        "total_requests": total,
        "malformed": malformed,
        "unique_ips": len(ips),
        "status_counts": dict(status_counts),
        "bytes_total": bytes_total,
        "error_rate": error_rate,
        "top_paths": top_paths,
        "requests_per_hour": dict(hour_counts),
    }
