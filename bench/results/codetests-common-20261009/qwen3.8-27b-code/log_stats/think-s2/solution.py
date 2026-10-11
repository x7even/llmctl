"""Summarise Common Log Format web server access logs."""

import re
from collections import Counter
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
    r"^\s*(?P<ip>\S+)\s+(?P<ident>\S+)\s+(?P<user>\S+)\s+"
    r"\[(?P<timestamp>[^\]]+)\]\s+"
    r'"(?P<request>[^"]*)"\s+'
    r"(?P<status>\d+)\s+"
    r"(?P<bytes>\d+|-)\s*$"
)

_TIMESTAMP_RE = re.compile(
    r"^(?P<day>\d{1,2})/(?P<month>[A-Za-z]{3})/(?P<year>\d{4}):"
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})"
    r"\s+(?P<offset>[+-]\d{4})$"
)


def _hour_key(timestamp):
    m = _TIMESTAMP_RE.match(timestamp)
    if m is None:
        return None

    day = int(m.group("day"))
    month_name = m.group("month")
    month = _MONTHS.get(month_name)
    if month is None:
        month = _MONTHS.get(month_name.capitalize())
    if month is None:
        return None

    year = int(m.group("year"))
    hour = int(m.group("hour"))
    minute = int(m.group("minute"))
    second = int(m.group("second"))

    if not (
        1 <= day <= 31
        and 0 <= hour <= 23
        and 0 <= minute <= 59
        and 0 <= second <= 59
    ):
        return None

    return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}"


def analyze_log(lines: Iterable[str]) -> dict:
    if lines is None:
        lines = []
    elif isinstance(lines, str):
        lines = lines.splitlines()

    total_requests = 0
    malformed = 0
    ips = set()
    status_counts = Counter()
    bytes_total = 0
    error_count = 0
    path_counts = Counter()
    hour_counts = Counter()

    for line in lines:
        if not isinstance(line, str):
            malformed += 1
            continue

        match = _LOG_RE.fullmatch(line.strip())
        if match is None:
            malformed += 1
            continue

        request_parts = match.group("request").split()
        if len(request_parts) != 3:
            malformed += 1
            continue

        path = request_parts[1]
        hour = _hour_key(match.group("timestamp"))
        if hour is None:
            malformed += 1
            continue

        status = int(match.group("status"))
        raw_bytes = match.group("bytes")
        size = 0 if raw_bytes == "-" else int(raw_bytes)

        total_requests += 1
        ips.add(match.group("ip"))
        status_counts[status] += 1
        bytes_total += size

        if 400 <= status <= 599:
            error_count += 1

        path_counts[path.split("?", 1)[0]] += 1
        hour_counts[hour] += 1

    error_rate = round(error_count / total_requests, 4) if total_requests else 0.0
    top_paths = sorted(
        path_counts.items(),
        key=lambda item: (-item[1], item[0]),
    )[:3]

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
