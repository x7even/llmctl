import re
from collections import Counter
from typing import Iterable

_MONTHS = {
    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12',
}

_LOG_RE = re.compile(
    r'^(\S+) (\S+) (\S+) \[(\d{2}/\w{3}/\d{4}:\d{2}:\d{2}:\d{2} [+\-]\d{4})\] '
    r'"(\S+) (\S+) (\S+)" (\d+) (\d+|-)$'
)


def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0
    ips: set = set()
    status_counts: Counter = Counter()
    bytes_total = 0
    path_counts: Counter = Counter()
    hour_counts: Counter = Counter()

    for line in lines:
        line = line.rstrip('\n\r')
        m = _LOG_RE.match(line)
        if m is None:
            malformed += 1
            continue

        ip = m.group(1)
        timestamp_str = m.group(4)
        path = m.group(6)
        status = int(m.group(8))
        bytes_str = m.group(9)

        total_requests += 1
        ips.add(ip)
        status_counts[status] += 1

        b = 0 if bytes_str == '-' else int(bytes_str)
        bytes_total += b

        # Strip query string for path counting
        clean_path = path.split('?', 1)[0]
        path_counts[clean_path] += 1

        # Parse timestamp "DD/Mon/YYYY:HH:MM:SS +ZZZZ" -> "YYYY-MM-DD HH"
        day_mon_year, time_and_tz = timestamp_str.split(':', 1)
        day, mon, year = day_mon_year.split('/')
        hour = time_and_tz.split(':')[0]
        month_num = _MONTHS[mon]
        hour_key = f"{year}-{month_num}-{day} {hour}"
        hour_counts[hour_key] += 1

    # Error rate: fraction of valid lines with status 400-599
    error_count = sum(c for s, c in status_counts.items() if 400 <= s <= 599)
    if total_requests > 0:
        error_rate = round(error_count / total_requests, 4)
    else:
        error_rate = 0.0

    # Top 3 paths: count descending, then path ascending
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
