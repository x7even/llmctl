import re
from collections import Counter
from typing import Iterable

_LOG_RE = re.compile(
    r'^(\S+) (\S+) (\S+) \[([^\]]+)\] "(\S+) (\S+) (\S+)" (\d+) (\d+|-)$'
)

_TS_RE = re.compile(
    r'^(\d{1,2})/([A-Za-z]{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2})\s[+-]\d{4}$'
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
    status_counts: Counter = Counter()
    bytes_total = 0
    error_count = 0
    path_counter: Counter = Counter()
    hour_counter: Counter = Counter()

    for line in lines:
        line = line.strip()
        if not line:
            malformed += 1
            continue

        m = _LOG_RE.match(line)
        if not m:
            malformed += 1
            continue

        ip, _ident, _user, timestamp, _method, path, _protocol, status_str, bytes_str = m.groups()

        ts_m = _TS_RE.match(timestamp)
        if not ts_m:
            malformed += 1
            continue

        day, month_abbr, year, hour, _minute, _second = ts_m.groups()
        if month_abbr not in _MONTHS:
            malformed += 1
            continue

        # Valid line
        total_requests += 1
        ips.add(ip)

        status = int(status_str)
        status_counts[status] += 1
        if 400 <= status <= 599:
            error_count += 1

        bytes_total += 0 if bytes_str == '-' else int(bytes_str)

        path_clean = path.split('?', 1)[0]
        path_counter[path_clean] += 1

        hour_key = f"{year}-{_MONTHS[month_abbr]}-{int(day):02d} {hour}"
        hour_counter[hour_key] += 1

    error_rate = round(error_count / total_requests, 4) if total_requests > 0 else 0.0

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
