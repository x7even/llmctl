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

_TS_RE = re.compile(r'(\d+)/(\w+)/(\d+):(\d+):\d+:\d+')


def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0
    ips: set = set()
    status_counts: Counter = Counter()
    bytes_total = 0
    path_counts: Counter = Counter()
    hour_counts: Counter = Counter()

    for line in lines:
        line = line.strip()
        m = _LOG_RE.match(line)
        if m is None:
            malformed += 1
            continue

        ip, _ident, _user, timestamp, _method, path, _protocol, status_str, bytes_str = m.groups()

        status = int(status_str)
        b = 0 if bytes_str == '-' else int(bytes_str)

        total_requests += 1
        ips.add(ip)
        status_counts[status] += 1
        bytes_total += b

        clean_path = path.split('?', 1)[0]
        path_counts[clean_path] += 1

        ts_m = _TS_RE.match(timestamp)
        if ts_m:
            day, mon, year, hour = ts_m.groups()
            if mon in _MONTHS:
                key = f"{year}-{_MONTHS[mon]}-{day.zfill(2)} {hour}"
                hour_counts[key] += 1

    error_count = sum(v for k, v in status_counts.items() if 400 <= k <= 599)
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
