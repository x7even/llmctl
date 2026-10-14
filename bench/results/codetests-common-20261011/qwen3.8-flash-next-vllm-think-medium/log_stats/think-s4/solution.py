import re
from collections import Counter
from typing import Iterable

_MONTHS = {
    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12',
}

_LOG_RE = re.compile(
    r'^(\S+) (\S+) (\S+) \[([^\]]+)\] "(\S+) (\S+) (\S+)" (\d+) (\d+|-)\s*$'
)

_TS_RE = re.compile(r'(\d+)/(\w+)/(\d+):(\d+):\d+:\d+')


def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0
    ips: set = set()
    status_counts: Counter = Counter()
    bytes_total = 0
    error_count = 0
    path_counter: Counter = Counter()
    hour_counter: Counter = Counter()

    for line in lines:
        m = _LOG_RE.match(line)
        if not m:
            malformed += 1
            continue

        ip = m.group(1)
        timestamp = m.group(4)
        path = m.group(6)
        status = int(m.group(8))
        bytes_str = m.group(9)

        total_requests += 1
        ips.add(ip)
        status_counts[status] += 1

        nbytes = 0 if bytes_str == '-' else int(bytes_str)
        bytes_total += nbytes

        if 400 <= status <= 599:
            error_count += 1

        path_no_query = path.split('?', 1)[0]
        path_counter[path_no_query] += 1

        ts_m = _TS_RE.match(timestamp)
        if ts_m:
            day, mon_abbr, year, hour = ts_m.group(1), ts_m.group(2), ts_m.group(3), ts_m.group(4)
            mon_num = _MONTHS.get(mon_abbr)
            if mon_num is not None:
                hour_key = f"{year}-{mon_num}-{day.zfill(2)} {hour}"
                hour_counter[hour_key] += 1

    if total_requests > 0:
        error_rate = round(error_count / total_requests, 4)
    else:
        error_rate = 0.0

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
