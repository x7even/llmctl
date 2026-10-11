import re
from datetime import date
from typing import Iterable

__all__ = ["analyze_log"]

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

_LOG_RE = re.compile(
    r'^(?P<ip>\S+)\s+(?P<ident>\S+)\s+(?P<user>\S+)\s+'
    r'\[(?P<timestamp>[^\]]+)\]\s+'
    r'"(?P<request>[^"]*)"\s+'
    r'(?P<status>\d+)\s+'
    r'(?P<size>\d+|-)\s*$'
)

_TS_RE = re.compile(
    r'^(\d{1,2})/(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)/(\d{4})'
    r':(\d{2}):(\d{2}):(\d{2})\s+[+-]\d{4}$'
)


def _parse_hour(timestamp):
    match = _TS_RE.match(timestamp)
    if not match:
        return None

    day = int(match.group(1))
    month = _MONTHS[match.group(2)]
    year = int(match.group(3))
    hour = int(match.group(4))
    minute = int(match.group(5))
    second = int(match.group(6))

    if not (1 <= day <= 31):
        return None
    if not (0 <= hour <= 23):
        return None
    if not (0 <= minute <= 59):
        return None
    if not (0 <= second <= 59):
        return None

    try:
        date(year, month, day)
    except ValueError:
        return None

    return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}"


def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0
    ips = set()
    status_counts = {}
    bytes_total = 0
    error_count = 0
    path_counts = {}
    hour_counts = {}

    for line in lines:
        if not isinstance(line, str):
            malformed += 1
            continue

        line = line.strip()
        if not line:
            malformed += 1
            continue

        match = _LOG_RE.match(line)
        if not match:
            malformed += 1
            continue

        request_parts = match.group("request").split()
        if len(request_parts) != 3:
            malformed += 1
            continue

        path = request_parts[1].split("?", 1)[0]
        hour_key = _parse_hour(match.group("timestamp"))
        if hour_key is None:
            malformed += 1
            continue

        status = int(match.group("status"))
        raw_size = match.group("size")
        size = 0 if raw_size == "-" else int(raw_size)

        total_requests += 1
        ips.add(match.group("ip"))
        status_counts[status] = status_counts.get(status, 0) + 1
        bytes_total += size
        if 400 <= status <= 599:
            error_count += 1
        path_counts[path] = path_counts.get(path, 0) + 1
        hour_counts[hour_key] = hour_counts.get(hour_key, 0) + 1

    error_rate = round(error_count / total_requests, 4) if total_requests else 0.0
    top_paths = sorted(
        path_counts.items(),
        key=lambda item: (-item[1], item[0])
    )[:3]

    return {
        "total_requests": total_requests,
        "malformed": malformed,
        "unique_ips": len(ips),
        "status_counts": dict(sorted(status_counts.items())),
        "bytes_total": bytes_total,
        "error_rate": error_rate,
        "top_paths": top_paths,
        "requests_per_hour": dict(sorted(hour_counts.items())),
    }
