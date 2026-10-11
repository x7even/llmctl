import re
from collections import Counter
from datetime import datetime
from typing import Iterable, Optional

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
    r'^(\S+)[ \t]+(\S+)[ \t]+(\S+)[ \t]+'
    r'\[([^\]]+)\][ \t]+'
    r'"(\S+)[ \t]+(\S+)[ \t]+(\S+)"[ \t]+'
    r'(\d+)[ \t]+'
    r'(\d+|-)$'
)

_TIMESTAMP_RE = re.compile(
    r'^(\d{1,2})/([A-Za-z]{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2})'
    r'[ \t]+([+-])(\d{2})(\d{2})$'
)


def _hour_key(timestamp: str) -> Optional[str]:
    match = _TIMESTAMP_RE.match(timestamp)
    if match is None:
        return None

    day_str, month_str, year_str, hour_str, minute_str, second_str, _sign, offset_hour_str, offset_minute_str = match.groups()

    month = _MONTHS.get(month_str.capitalize())
    if month is None:
        return None

    try:
        day = int(day_str)
        year = int(year_str)
        hour = int(hour_str)
        minute = int(minute_str)
        second = int(second_str)
        offset_hour = int(offset_hour_str)
        offset_minute = int(offset_minute_str)

        datetime.datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None

    if offset_hour > 23 or offset_minute > 59:
        return None

    return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}"


def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0

    unique_ips = set()
    status_counts = Counter()
    path_counts = Counter()
    hour_counts = Counter()

    bytes_total = 0

    for line in lines:
        if not isinstance(line, str):
            malformed += 1
            continue

        match = _LOG_RE.match(line.rstrip())
        if match is None:
            malformed += 1
            continue

        ip, _ident, _user, timestamp, _method, path, _protocol, status_str, bytes_str = match.groups()

        hour = _hour_key(timestamp)
        if hour is None:
            malformed += 1
            continue

        try:
            status = int(status_str)
        except ValueError:
            malformed += 1
            continue

        if bytes_str == "-":
            nbytes = 0
        else:
            try:
                nbytes = int(bytes_str)
            except ValueError:
                malformed += 1
                continue

        total_requests += 1
        unique_ips.add(ip)
        status_counts[status] += 1
        bytes_total += nbytes

        clean_path = path.split("?", 1)[0]
        path_counts[clean_path] += 1

        hour_counts[hour] += 1

    error_count = sum(
        count
        for status, count in status_counts.items()
        if 400 <= status <= 599
    )

    error_rate = 0.0 if total_requests == 0 else round(error_count / total_requests, 4)

    top_paths = sorted(
        path_counts.items(),
        key=lambda item: (-item[1], item[0])
    )[:3]

    return {
        "total_requests": total_requests,
        "malformed": malformed,
        "unique_ips": len(unique_ips),
        "status_counts": dict(status_counts),
        "bytes_total": bytes_total,
        "error_rate": error_rate,
        "top_paths": top_paths,
        "requests_per_hour": dict(hour_counts),
    }
