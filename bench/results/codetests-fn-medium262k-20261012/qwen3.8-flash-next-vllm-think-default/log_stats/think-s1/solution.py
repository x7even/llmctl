import re
from collections import Counter
from typing import Iterable

_MONTHS = {
    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12',
}

_LOG_RE = re.compile(
    r'^(\S+) (\S+) (\S+) \[(\d{2})/([A-Za-z]{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2}) [+-]\d{4}\]'
    r' "(\S+) (\S+) (\S+)" (\d{3}) (\d+|-)$'
)


def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0
    ips: set = set()
    status_counts: Counter = Counter()
    bytes_total = 0
    error_count = 0
    path_counter: Counter = Counter()
    hour_counter: Counter = Counter()

    for raw in lines:
        line = raw.strip()
        m = _LOG_RE.match(line)
        if not m:
            malformed += 1
            continue

        ip = m.group(1)
        month_abbr = m.group(5)
        if month_abbr not in _MONTHS:
            malformed += 1
            continue

        day = m.group(4)
        year = m.group(6)
        hour = m.group(7)
        path = m.group(11)
        status = int(m.group(13))
        bytes_field = m.group(14)

        # Strip query string from path
        path = path.split('?', 1)[0]

        # Bytes
        nbytes = 0 if bytes_field == '-' else int(bytes_field)

        # Accumulate
        total_requests += 1
        ips.add(ip)
        status_counts[status] += 1
        bytes_total += nbytes
        if 400 <= status <= 599:
            error_count += 1
        path_counter[path] += 1

        hour_key = f"{year}-{_MONTHS[month_abbr]}-{day} {hour}"
        hour_counter[hour_key] += 1

    # error_rate
    if total_requests == 0:
        error_rate = 0.0
    else:
        error_rate = round(error_count / total_requests, 4)

    # top_paths: sort by count desc, then path asc; take up to 3
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
