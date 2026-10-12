import re
from collections import Counter
from typing import Iterable

_MONTHS = {
    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12',
}

_LOG_RE = re.compile(
    r'^(\S+) (\S+) (\S+) \[([^\]]+)\] "(\S+) (\S+) (\S+)" (\d+) (\d+|-)$'
)

_TS_RE = re.compile(r'^(\d{2})/([A-Za-z]{3})/(\d{4}):(\d{2}):\d{2}:\d{2}')


def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0
    ips: set = set()
    status_counts: Counter = Counter()
    bytes_total = 0
    path_counts: Counter = Counter()
    hour_counts: Counter = Counter()
    error_count = 0

    for line in lines:
        line = line.rstrip('\r\n')
        m = _LOG_RE.match(line)
        if not m:
            malformed += 1
            continue

        _ip, _ident, _user, timestamp, _method, path, _proto, status_str, bytes_str = m.groups()

        # Parse and validate timestamp
        ts = _TS_RE.match(timestamp)
        if not ts:
            malformed += 1
            continue
        day, mon_str, year, hour = ts.groups()
        mon_str = mon_str.capitalize()
        if mon_str not in _MONTHS:
            malformed += 1
            continue
        hour_key = f"{year}-{_MONTHS[mon_str]}-{day} {hour}"

        # Parse bytes
        nbytes = 0 if bytes_str == '-' else int(bytes_str)

        # Strip query string
        path_clean = path.split('?', 1)[0]

        # Valid line
        status = int(status_str)
        total_requests += 1
        ips.add(_ip)
        status_counts[status] += 1
        bytes_total += nbytes
        path_counts[path_clean] += 1
        hour_counts[hour_key] += 1

        if 400 <= status <= 599:
            error_count += 1

    # Error rate
    if total_requests > 0:
        error_rate = round(error_count / total_requests, 4)
    else:
        error_rate = 0.0

    # Top 3 paths: count desc, then path asc
    sorted_paths = sorted(path_counts.items(), key=lambda x: (-x[1], x[0]))
    top_paths = sorted_paths[:3]

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
