from collections import Counter
from typing import Iterable
import re

LOG_PATTERN = re.compile(
    r'^(\S+) (\S+) (\S+) \[([^\]]+)\] "(\S+) (\S+) (\S+)" (\d+) (\d+|-)$'
)

_MONTHS = {
    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12',
}


def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0
    ips: set[str] = set()
    status_counts: dict[int, int] = {}
    bytes_total = 0
    error_count = 0
    path_counts: Counter = Counter()
    hour_counts: Counter = Counter()

    for line in lines:
        line = line.rstrip()

        if not line:
            malformed += 1
            continue

        m = LOG_PATTERN.match(line)
        if not m:
            malformed += 1
            continue

        ip, _ident, _user, timestamp, _method, path, _protocol, status_str, bytes_str = m.groups()

        # Validate timestamp: DD/Mon/YYYY:HH:MM:SS +ZZZZ
        try:
            date_part = timestamp.split(' ')[0]
            day, mon, rest = date_part.split('/', 2)
            time_parts = rest.split(':')
            year, hour = time_parts[0], time_parts[1]
            mon_num = _MONTHS[mon]
            int(day)
            int(year)
            int(hour)
        except (ValueError, IndexError, KeyError):
            malformed += 1
            continue

        status = int(status_str)
        bytes_val = 0 if bytes_str == '-' else int(bytes_str)

        total_requests += 1
        ips.add(ip)
        status_counts[status] = status_counts.get(status, 0) + 1
        bytes_total += bytes_val

        if 400 <= status <= 599:
            error_count += 1

        clean_path = path.split('?', 1)[0]
        path_counts[clean_path] += 1

        hour_key = f"{year}-{mon_num}-{day} {hour}"
        hour_counts[hour_key] += 1

    error_rate = round(error_count / total_requests, 4) if total_requests > 0 else 0.0
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
