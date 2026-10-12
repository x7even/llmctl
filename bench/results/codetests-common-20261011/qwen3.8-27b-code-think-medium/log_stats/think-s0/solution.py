from collections import Counter
from typing import Iterable


def analyze_log(lines: Iterable[str]) -> dict:
    import re

    pattern = re.compile(
        r'^(\S+) (\S+) (\S+) \[([^\]]*)\] "([^"]*)" (\S+) (\S+)$'
    )

    month_map = {
        'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4,
        'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8,
        'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12,
    }

    total_requests = 0
    malformed = 0
    ips: set = set()
    status_counts: dict = {}
    bytes_total = 0
    path_counts: Counter = Counter()
    hour_counts: Counter = Counter()
    error_count = 0

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            malformed += 1
            continue

        m = pattern.match(line)
        if not m:
            malformed += 1
            continue

        ip, _ident, _user, timestamp, request, status_str, bytes_str = m.groups()

        # status must be a non-negative integer
        if not status_str.isdigit():
            malformed += 1
            continue
        status = int(status_str)

        # bytes must be a non-negative integer or '-'
        if bytes_str == '-':
            size = 0
        elif bytes_str.isdigit():
            size = int(bytes_str)
        else:
            malformed += 1
            continue

        # request must have exactly three space-separated tokens
        req_parts = request.split(' ')
        if len(req_parts) != 3:
            malformed += 1
            continue
        _method, path_full, _protocol = req_parts

        # ---- valid line ----
        total_requests += 1
        ips.add(ip)
        status_counts[status] = status_counts.get(status, 0) + 1
        bytes_total += size

        if 400 <= status <= 599:
            error_count += 1

        path = path_full.split('?', 1)[0]
        path_counts[path] += 1

        # Parse timestamp: DD/Mon/YYYY:HH:MM:SS +ZZZZ
        try:
            ts_main = timestamp.split(' ', 1)[0]  # drop timezone
            day_s, mon_s, rest = ts_main.split('/')
            year_s, hour_s, _min_s, _sec_s = rest.split(':')
            day = int(day_s)
            month = month_map[mon_s]
            year = int(year_s)
            hour = int(hour_s)
            hour_key = f"{year:04d}-{month:02d}-{day:02d} {hour:02d}"
            hour_counts[hour_key] += 1
        except (ValueError, KeyError, IndexError):
            pass  # line is still valid; just can't bucket by hour

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
