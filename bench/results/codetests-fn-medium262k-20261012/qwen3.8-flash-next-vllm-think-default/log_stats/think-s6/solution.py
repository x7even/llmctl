import re
from collections import Counter
from typing import Iterable, Tuple

_MONTHS = {
    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12',
}

_LOG_RE = re.compile(
    r'^(\S+) (\S+) (\S+) \[([^\]]+)\] "([^"]*)" (\S+) (\S+)$'
)

_TS_RE = re.compile(
    r'^(\d+)/([A-Za-z]{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2})\s+[+-]\d{4}$'
)


def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0
    ips: set = set()
    status_counts: Counter = Counter()
    bytes_total = 0
    error_count = 0
    path_counts: Counter = Counter()
    hour_counts: Counter = Counter()

    for line in lines:
        m = _LOG_RE.match(line)
        if not m:
            malformed += 1
            continue

        ip, _ident, _user, timestamp, request, status_str, bytes_str = m.groups()

        # Validate status is numeric
        try:
            status = int(status_str)
        except ValueError:
            malformed += 1
            continue

        # Validate bytes field
        if bytes_str == '-':
            nbytes = 0
        else:
            try:
                nbytes = int(bytes_str)
            except ValueError:
                malformed += 1
                continue

        # Validate request line has exactly 3 space-separated tokens
        parts = request.split(' ')
        if len(parts) != 3:
            malformed += 1
            continue

        _method, path, _protocol = parts

        # Strip query string
        path_clean = path.split('?')[0]

        # Parse timestamp
        ts_m = _TS_RE.match(timestamp)
        if not ts_m:
            malformed += 1
            continue

        day, mon_str, year, hour, _min, _sec = ts_m.groups()
        if mon_str not in _MONTHS:
            malformed += 1
            continue

        hour_key = f"{year}-{_MONTHS[mon_str]}-{int(day):02d} {hour}"

        # Line is valid — accumulate
        total_requests += 1
        ips.add(ip)
        status_counts[status] += 1
        bytes_total += nbytes
        if 400 <= status <= 599:
            error_count += 1
        path_counts[path_clean] += 1
        hour_counts[hour_key] += 1

    # error_rate
    if total_requests > 0:
        error_rate = round(error_count / total_requests, 4)
    else:
        error_rate = 0.0

    # top_paths: sorted by count desc, then path asc
    top_paths: list[Tuple[str, int]] = sorted(
        path_counts.items(), key=lambda x: (-x[1], x[0])
    )[:3]

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
