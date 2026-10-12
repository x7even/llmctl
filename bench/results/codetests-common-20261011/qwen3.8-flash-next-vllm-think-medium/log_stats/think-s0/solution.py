"""Module for analysing web-server access logs in Common Log Format."""

from collections import Counter
from typing import Iterable
import re

_MONTHS = {
    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12',
}

# ip ident user [DD/Mon/YYYY:HH:MM:SS +ZZZZ] "METHOD path PROTOCOL" status bytes
_LOG_RE = re.compile(
    r'^(\S+) (\S+) (\S+) '
    r'\[(\d{2})/([A-Za-z]{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2}) [+-]\d{4}\] '
    r'"(\S+) (\S+) (\S+)" '
    r'(\d+) (\d+|-)$'
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
        line = line.rstrip('\r\n')
        m = _LOG_RE.match(line)
        if m is None:
            malformed += 1
            continue

        ip = m.group(1)
        # groups 2 (ident) and 3 (user) are not needed
        day, mon, year, hour, _min, _sec = m.group(4, 5, 6, 7, 8, 9)
        # groups 10 (method), 12 (protocol) not needed
        path = m.group(11)
        status = int(m.group(13))
        bytes_str = m.group(14)

        # Validate month abbreviation
        mon_num = _MONTHS.get(mon)
        if mon_num is None:
            malformed += 1
            continue

        total_requests += 1
        ips.add(ip)
        status_counts[status] += 1

        bytes_val = 0 if bytes_str == '-' else int(bytes_str)
        bytes_total += bytes_val

        if 400 <= status <= 599:
            error_count += 1

        # Strip query string for path counting
        clean_path = path.split('?', 1)[0]
        path_counts[clean_path] += 1

        hour_key = f"{year}-{mon_num}-{day} {hour}"
        hour_counts[hour_key] += 1

    # error_rate
    if total_requests > 0:
        error_rate = round(error_count / total_requests, 4)
    else:
        error_rate = 0.0

    # top_paths: count desc, then path asc
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
