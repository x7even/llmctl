import re
from collections import Counter
from typing import Iterable

_MONTH_MAP = {
    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12',
}

_CLF_RE = re.compile(
    r'^(\S+) (\S+) (\S+) \[([^\]]+)\] "(\S+) (\S+) (\S+)" (\d+) (\d+|-)$'
)

_TS_RE = re.compile(
    r'^(\d{2})/([A-Za-z]{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2}) [+-]\d{4}$'
)


def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0
    ips: set = set()
    status_counts: dict = {}
    bytes_total = 0
    error_count = 0
    path_counter: Counter = Counter()
    hour_counter: dict = {}

    for line in lines:
        line = line.rstrip('\r\n')
        m = _CLF_RE.match(line)
        if m is None:
            malformed += 1
            continue

        ip, _ident, _user, timestamp, _method, path, _proto, status_str, bytes_str = m.groups()

        ts = _TS_RE.match(timestamp)
        if ts is None:
            malformed += 1
            continue
        day, mon, year, hour, _min, _sec = ts.groups()
        if mon not in _MONTH_MAP:
            malformed += 1
            continue

        # --- valid line ---
        total_requests += 1
        ips.add(ip)

        status = int(status_str)
        status_counts[status] = status_counts.get(status, 0) + 1
        if 400 <= status <= 599:
            error_count += 1

        bytes_total += 0 if bytes_str == '-' else int(bytes_str)

        path_no_query = path.split('?', 1)[0]
        path_counter[path_no_query] += 1

        hour_key = f"{year}-{_MONTH_MAP[mon]}-{day} {hour}"
        hour_counter[hour_key] = hour_counter.get(hour_key, 0) + 1

    top_paths = sorted(path_counter.items(), key=lambda x: (-x[1], x[0]))[:3]

    error_rate = round(error_count / total_requests, 4) if total_requests else 0.0

    return {
        "total_requests": total_requests,
        "malformed": malformed,
        "unique_ips": len(ips),
        "status_counts": status_counts,
        "bytes_total": bytes_total,
        "error_rate": error_rate,
        "top_paths": top_paths,
        "requests_per_hour": hour_counter,
    }
