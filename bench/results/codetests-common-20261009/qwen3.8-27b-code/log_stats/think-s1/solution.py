from typing import Iterable
from datetime import date
import re

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
    r'^(?P<ip>\S+) '
    r'(?P<ident>\S+) '
    r'(?P<user>\S+) '
    r'\[(?P<timestamp>\d{1,2}/[A-Z][a-z]{2}/\d{4}:\d{2}:\d{2}:\d{2} [+-]\d{4})\] '
    r'"(?P<method>\S+) (?P<path>\S+) (?P<protocol>\S+)" '
    r'(?P<status>\d+) '
    r'(?P<bytes>\d+|-)$'
)


def _hour_key(timestamp: str):
    try:
        day_s, month_s, rest = timestamp.split("/", 2)
        date_time, _ = rest.split(" ", 1)
        year_s, hour_s, minute_s, second_s = date_time.split(":")

        day = int(day_s)
        month = _MONTHS[month_s]
        year = int(year_s)
        hour = int(hour_s)
        minute = int(minute_s)
        second = int(second_s)

        if not (1 <= day <= 31):
            return None
        if not (0 <= hour <= 23) or not (0 <= minute <= 59) or not (0 <= second <= 59):
            return None

        date(year, month, day)
    except (ValueError, KeyError, OverflowError):
        return None

    return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}"


def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0
    unique_ips = set()
    status_counts = {}
    bytes_total = 0
    path_counts = {}
    hour_counts = {}

    for line in lines:
        if not isinstance(line, str):
            malformed += 1
            continue

        match = _LOG_RE.match(line.strip())
        if match is None:
            malformed += 1
            continue

        hour_key = _hour_key(match.group("timestamp"))
        if hour_key is None:
            malformed += 1
            continue

        total_requests += 1
        unique_ips.add(match.group("ip"))

        status = int(match.group("status"))
        status_counts[status] = status_counts.get(status, 0) + 1

        bytes_field = match.group("bytes")
        if bytes_field != "-":
            bytes_total += int(bytes_field)

        path = match.group("path").split("?", 1)[0]
        path_counts[path] = path_counts.get(path, 0) + 1

        hour_counts[hour_key] = hour_counts.get(hour_key, 0) + 1

    error_count = sum(count for status, count in status_counts.items() if 400 <= status <= 599)
    error_rate = round(error_count / total_requests, 4) if total_requests else 0.0

    top_paths = sorted(path_counts.items(), key=lambda item: (-item[1], item[0]))[:3]

    return {
        "total_requests": total_requests,
        "malformed": malformed,
        "unique_ips": len(unique_ips),
        "status_counts": status_counts,
        "bytes_total": bytes_total,
        "error_rate": error_rate,
        "top_paths": top_paths,
        "requests_per_hour": hour_counts,
    }
