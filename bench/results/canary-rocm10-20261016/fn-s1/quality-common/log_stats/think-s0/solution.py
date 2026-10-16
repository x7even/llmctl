import re
from collections import Counter
from typing import Iterable

_MONTHS = {
    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12',
}

_LOG_RE = re.compile(
    r'^(\S+) (\S+) (\S+) \[([^\]]+)\] "([^"]*)" (\d+) (\S+)$'
)


def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0
    ips: set = set()
    status_counts: Counter = Counter()
    bytes_total = 0
    path_counter: Counter = Counter()
    hour_counter: Counter = Counter()

    for line in lines:
        line = line.rstrip('\n\r')
        if not line:
            malformed += 1
            continue

        m = _LOG_RE.match(line)
        if m is None:
            malformed += 1
            continue

        ip, _ident, _user, timestamp, request, status_str, bytes_str = m.groups()

        # The quoted request must split into exactly three tokens
        req_parts = request.split(' ')
        if len(req_parts) != 3:
            malformed += 1
            continue

        # Bytes field: '-' means 0, otherwise must be a valid integer
        if bytes_str == '-':
            nbytes = 0
        else:
            try:
                nbytes = int(bytes_str)
            except ValueError:
                malformed += 1
                continue

        # Parse timestamp: "10/Oct/2026:13:55:36 +0000"
        ts_date_time = timestamp.split(' ')[0]
        ts_parts = ts_date_time.split('/')
        if len(ts_parts) != 3:
            malformed += 1
            continue
        day, month_str, rest = ts_parts
        rest_parts = rest.split(':')
        if len(rest_parts) != 4:
            malformed += 1
            continue
        year, hour, _min, _sec = rest_parts
        if month_str not in _MONTHS:
            malformed += 1
            continue
        hour_key = f"{year}-{_MONTHS[month_str]}-{day.zfill(2)} {hour.zfill(2)}"

        # --- valid line ---
        total_requests += 1
        ips.add(ip)
        status = int(status_str)
        status_counts[status] += 1
        bytes_total += nbytes

        path = req_parts[1].split('?')[0]
        path_counter[path] += 1

        hour_counter[hour_key] += 1

    # Error rate (400-599)
    if total_requests > 0:
        error_count = sum(v for k, v in status_counts.items() if 400 <= k <= 599)
        error_rate = round(error_count / total_requests, 4)
    else:
        error_rate = 0.0

    # Top 3 paths: count desc, then path asc
    top_paths = sorted(path_counter.items(), key=lambda x: (-x[1], x[0]))[:3]

    return {
        "total_requests": total_requests,
        "malformed": malformed,
        "unique_ips": len(ips),
        "status_counts": dict(status_counts),
        "bytes_total": bytes_total,
        "error_rate": error_rate,
        "top_paths": top_paths,
        "requests_per_hour": dict(hour_counter),
    }
