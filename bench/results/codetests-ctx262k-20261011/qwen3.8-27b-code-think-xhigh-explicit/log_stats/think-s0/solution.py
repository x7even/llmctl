import re
from collections import Counter
from typing import Iterable

_MONTHS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}

_LINE_RE = re.compile(
    r'^(\S+)[ \t]+(\S+)[ \t]+(\S+)[ \t]+\[([^\]]+)\][ \t]+'
    r'"(\S+)[ \t]+(\S+)[ \t]+(\S+)[ \t]*"[ \t]+'
    r'(\d+)[ \t]+(\d+|-)[ \t]*$'
)

_TS_RE = re.compile(
    r'^(\d{1,2})/(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)/'
    r'(\d{4}):(\d{2}):(\d{2}):(\d{2})[ \t]+[+-]\d{4}$'
)


def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0
    ips = set()
    status_counts = Counter()
    bytes_total = 0
    error_requests = 0
    path_counts = Counter()
    requests_per_hour = Counter()

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            malformed += 1
            continue

        match = _LINE_RE.match(line)
        if match is None:
            malformed += 1
            continue

        ip, _ident, _user, timestamp, _method, path, _protocol, status_str, bytes_str = match.groups()

        ts_match = _TS_RE.match(timestamp)
        if ts_match is None:
            malformed += 1
            continue

        day = int(ts_match.group(1))
        month_num = _MONTHS[ts_match.group(2)]
        year = int(ts_match.group(3))
        hour = int(ts_match.group(4))
        minute = int(ts_match.group(5))
        second = int(ts_match.group(6))

        if not (1 <= day <= 31 and 0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
            malformed += 1
            continue

        status = int(status_str)
        size = 0 if bytes_str == "-" else int(bytes_str)

        total_requests += 1
        ips.add(ip)
        status_counts[status] += 1
        bytes_total += size

        if 400 <= status <= 599:
            error_requests += 1

        clean_path = path.split("?", 1)[0]
        path_counts[clean_path] += 1

        hour_key = f"{year:04d}-{month_num:02d}-{day:02d} {hour:02d}"
        requests_per_hour[hour_key] += 1

    error_rate = round(error_requests / total_requests, 4) if total_requests else 0.0
    top_paths = sorted(path_counts.items(), key=lambda item: (-item[1], item[0]))[:3]

    return {
        "total_requests": total_requests,
        "malformed": malformed,
        "unique_ips": len(ips),
        "status_counts": dict(status_counts),
        "bytes_total": bytes_total,
        "error_rate": error_rate,
        "top_paths": top_paths,
        "requests_per_hour": dict(requests_per_hour),
    }
