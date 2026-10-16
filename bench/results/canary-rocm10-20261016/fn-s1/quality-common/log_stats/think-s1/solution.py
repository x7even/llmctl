import re
from collections import Counter
from typing import Iterable


def analyze_log(lines: Iterable[str]) -> dict:
    _LOG_RE = re.compile(
        r'^(\S+) (\S+) (\S+) \[([^\]]+)\] "(\S+) (\S+) (\S+)" (\S+) (\S+)$'
    )
    _TS_RE = re.compile(
        r'^(\d{2})/([A-Za-z]{3})/(\d{4}):(\d{2}):\d{2}:\d{2}\s+\S+$'
    )
    _MONTH_MAP = {
        'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
        'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
        'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12',
    }

    total_requests = 0
    malformed = 0
    ips = set()
    status_counts: Counter = Counter()
    bytes_total = 0
    error_count = 0
    path_counts: Counter = Counter()
    requests_per_hour: Counter = Counter()

    for line in lines:
        line = line.rstrip('\r\n')
        m = _LOG_RE.match(line)
        if m is None:
            malformed += 1
            continue

        ip, _ident, _user, timestamp, _method, path, _proto, status_str, bytes_str = m.groups()

        # Validate status code
        try:
            status = int(status_str)
        except ValueError:
            malformed += 1
            continue

        # Validate bytes field
        if bytes_str == '-':
            byte_val = 0
        else:
            try:
                byte_val = int(bytes_str)
            except ValueError:
                malformed += 1
                continue

        # Parse timestamp
        ts_m = _TS_RE.match(timestamp)
        if ts_m is None:
            malformed += 1
            continue

        day, mon, year, hour = ts_m.groups()
        mon_lower = mon.capitalize()
        if mon_lower not in _MONTH_MAP:
            malformed += 1
            continue

        # All fields valid — accumulate
        total_requests += 1
        ips.add(ip)
        status_counts[status] += 1
        bytes_total += byte_val

        if 400 <= status <= 599:
            error_count += 1

        path_no_query = path.split('?', 1)[0]
        path_counts[path_no_query] += 1

        hour_key = f"{year}-{_MONTH_MAP[mon_lower]}-{day} {hour}"
        requests_per_hour[hour_key] += 1

    # Derived metrics
    if total_requests > 0:
        error_rate = round(error_count / total_requests, 4)
    else:
        error_rate = 0.0

    top_paths = sorted(path_counts.items(), key=lambda x: (-x[1], x[0]))[:3]

    return {
        "total_requests": total_requests,
        "malformed": malformed,
        "unique_ips": len(ips),
        "status_counts": dict(status_counts),
        "bytes_total": bytes_total,
        "error_rate": error_rate,
        "top_paths": top_paths,
        "requests_per_hour": dict(requests_per_hour),
    }
