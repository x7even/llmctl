import re
from collections import Counter
from typing import Iterable

_LOG_RE = re.compile(
    r'^(\S+) (\S+) (\S+) \[([^\]]+)\] "([^"]*)" (\d+) (\d+|-)\s*$'
)

_TS_RE = re.compile(
    r'^(\d{1,2})/([A-Za-z]{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2})$'
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
    path_counts: Counter[str] = Counter()
    hour_counts: Counter[str] = Counter()

    for raw in lines:
        line = raw.rstrip('\r\n')
        if not line.strip():
            malformed += 1
            continue

        m = _LOG_RE.match(line)
        if not m:
            malformed += 1
            continue

        ip, _ident, _user, timestamp, request, status_str, bytes_str = m.groups()

        # --- request: METHOD path PROTOCOL ---
        parts = request.split(' ')
        if len(parts) != 3:
            malformed += 1
            continue
        _method, path, _protocol = parts

        # --- timestamp: DD/Mon/YYYY:HH:MM:SS (+TZ) ---
        ts_fields = timestamp.split(' ')
        ts_main = ts_fields[0]
        ts_m = _TS_RE.match(ts_main)
        if not ts_m:
            malformed += 1
            continue
        day, mon, year, hour, _min, _sec = ts_m.groups()
        if mon not in _MONTHS:
            malformed += 1
            continue

        hour_key = f"{year}-{_MONTHS[mon]}-{int(day):02d} {hour}"

        # --- status & bytes ---
        status = int(status_str)
        nbytes = 0 if bytes_str == '-' else int(bytes_str)

        # --- accumulate ---
        total_requests += 1
        ips.add(ip)
        status_counts[status] = status_counts.get(status, 0) + 1
        bytes_total += nbytes
        if 400 <= status <= 599:
            error_count += 1

        path_no_query = path.split('?', 1)[0]
        path_counts[path_no_query] += 1

        hour_counts[hour_key] += 1

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
