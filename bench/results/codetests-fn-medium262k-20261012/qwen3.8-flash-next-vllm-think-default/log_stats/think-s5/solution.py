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
        line = line.strip()
        if not line:
            malformed += 1
            continue

        m = _LOG_RE.match(line)
        if not m:
            malformed += 1
            continue

        ip, ident, user, timestamp, method, path, protocol, status_str, bytes_str = m.groups()

        # Parse timestamp: DD/Mon/YYYY:HH:MM:SS +ZZZZ
        try:
            date_part, time_part = timestamp.split(':', 1)
            day_str, mon_str, year_str = date_part.split('/')
            hour_str = time_part.split(':')[0]
            month_num = _MONTHS[mon_str]
            hour_key = f"{year_str}-{month_num}-{day_str.zfill(2)} {hour_str.zfill(2)}"
        except (ValueError, KeyError):
            malformed += 1
            continue

        status = int(status_str)
        nbytes = 0 if bytes_str == '-' else int(bytes_str)

        total_requests += 1
        ips.add(ip)
        status_counts[status] += 1
        bytes_total += nbytes

        if 400 <= status <= 599:
            error_count += 1

        clean_path = path.split('?')[0]
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
