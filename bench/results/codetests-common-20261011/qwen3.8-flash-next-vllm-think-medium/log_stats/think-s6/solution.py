import re
from collections import Counter
from typing import Iterable

_MONTHS = {
    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12',
}

_LOG_RE = re.compile(
    r'^(\S+) (\S+) (\S+) \[([^\]]+)\] "(\S+) (\S+) (\S+)" (\S+) (\S+)$'
)

_TS_RE = re.compile(r'(\d+)/(\w+)/(\d+):(\d+):(\d+):(\d+)')


def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0
    ips: set = set()
    status_counter: Counter = Counter()
    bytes_total = 0
    path_counter: Counter = Counter()
    hour_counter: Counter = Counter()

    for line in lines:
        line = line.rstrip('\r\n')
        m = _LOG_RE.match(line)
        if m is None:
            malformed += 1
            continue

        ip, _ident, _user, timestamp, _method, path, _protocol, status_str, bytes_str = m.groups()

        # Validate status is a proper integer
        try:
            status = int(status_str)
        except ValueError:
            malformed += 1
            continue

        # Validate / parse bytes
        if bytes_str == '-':
            nbytes = 0
        else:
            try:
                nbytes = int(bytes_str)
            except ValueError:
                malformed += 1
                continue

        # Parse timestamp: "10/Oct/2026:13:55:36 +0000"
        ts_m = _TS_RE.match(timestamp)
        if ts_m is None:
            malformed += 1
            continue

        day, mon_str, year, hour, _min, _sec = ts_m.groups()
        mon_num = _MONTHS.get(mon_str)
        if mon_num is None:
            malformed += 1
            continue

        hour_key = f"{year}-{mon_num}-{int(day):02d} {hour}"

        # Strip query string from path
        path_clean = path.split('?', 1)[0]

        # Accumulate
        total_requests += 1
        ips.add(ip)
        status_counter[status] += 1
        bytes_total += nbytes
        path_counter[path_clean] += 1
        hour_counter[hour_key] += 1

    # Error rate (400–599 inclusive)
    if total_requests > 0:
        error_count = sum(c for s, c in status_counter.items() if 400 <= s <= 599)
        error_rate = round(error_count / total_requests, 4)
    else:
        error_rate = 0.0

    # Top 3 paths: count desc, then path asc
    top_paths = sorted(path_counter.items(), key=lambda x: (-x[1], x[0]))[:3]

    return {
        "total_requests": total_requests,
        "malformed": malformed,
        "unique_ips": len(ips),
        "status_counts": dict(status_counter),
        "bytes_total": bytes_total,
        "error_rate": error_rate,
        "top_paths": top_paths,
        "requests_per_hour": dict(hour_counter),
    }
