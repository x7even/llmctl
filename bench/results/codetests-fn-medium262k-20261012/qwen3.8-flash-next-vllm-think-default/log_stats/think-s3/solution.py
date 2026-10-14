import re
from collections import Counter
from typing import Iterable, Dict, List, Tuple

_MONTHS: Dict[str, str] = {
    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12',
}

_LOG_RE = re.compile(
    r'^(\S+) (\S+) (\S+) \[([^\]]+)\] "(\S+) (\S+) (\S+)" (\d+) (\d+|-)\s*$'
)

_TS_RE = re.compile(r'^(\d{2})/([A-Za-z]{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2})$')


def analyze_log(lines: Iterable[str]) -> dict:
    total = 0
    malformed = 0
    ips: set = set()
    status_counts: Counter = Counter()
    bytes_total = 0
    errors = 0
    path_counter: Counter = Counter()
    hour_counter: Counter = Counter()

    for line in lines:
        line = line.rstrip('\n\r')
        m = _LOG_RE.match(line)
        if not m:
            malformed += 1
            continue

        ip, _ident, _user, timestamp, _method, path, _protocol, status_s, bytes_s = m.groups()

        # Validate and parse timestamp
        ts_str = timestamp.split()[0]  # ignore timezone offset part
        ts_m = _TS_RE.match(ts_str)
        if not ts_m:
            malformed += 1
            continue
        day, mon, year, hour, _min, _sec = ts_m.groups()
        if mon not in _MONTHS:
            malformed += 1
            continue

        status = int(status_s)
        nbytes = 0 if bytes_s == '-' else int(bytes_s)

        hour_key = f"{year}-{_MONTHS[mon]}-{day} {hour}"
        clean_path = path.split('?')[0]

        total += 1
        ips.add(ip)
        status_counts[status] += 1
        bytes_total += nbytes
        if 400 <= status <= 599:
            errors += 1
        path_counter[clean_path] += 1
        hour_counter[hour_key] += 1

    error_rate = round(errors / total, 4) if total > 0 else 0.0

    top_paths: List[Tuple[str, int]] = sorted(
        path_counter.items(), key=lambda x: (-x[1], x[0])
    )[:3]

    return {
        "total_requests": total,
        "malformed": malformed,
        "unique_ips": len(ips),
        "status_counts": dict(status_counts),
        "bytes_total": bytes_total,
        "error_rate": error_rate,
        "top_paths": top_paths,
        "requests_per_hour": dict(hour_counter),
    }
