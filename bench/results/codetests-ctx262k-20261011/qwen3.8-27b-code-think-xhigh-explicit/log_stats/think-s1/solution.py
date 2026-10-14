from collections import Counter
from datetime import datetime
from typing import Iterable
import re

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
    r'^(?P<ip>\S+) (?P<ident>\S+) (?P<user>\S+) '
    r'\[(?P<timestamp>[^\]]*)\] '
    r'"(?P<request>[^"]*)" '
    r'(?P<status>\d+) (?P<bytes>\d+|-)$'
)

_TS_RE = re.compile(
    r'^(?P<day>\d{1,2})/(?P<month>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'
    r'/(?P<year>\d{4}):(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2}) '
    r'[+-]\d{4}$'
)


def _hour_key(timestamp: str):
    match = _TS_RE.match(timestamp)
    if match is None:
        return None

    month = _MONTHS[match.group("month")]
    try:
        dt = datetime(
            int(match.group("year")),
            month,
            int(match.group("day")),
            int(match.group("hour")),
            int(match.group("minute")),
            int(match.group("second")),
        )
    except ValueError:
        return None

    return f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d} {dt.hour:02d}"


def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0
    unique_ips = set()
    status_counts = {}
    bytes_total = 0
    error_count = 0
    path_counts = Counter()
    hour_counts = Counter()

    for raw_line in lines:
        if isinstance(raw_line, bytes):
            try:
                line = raw_line.decode("utf-8")
            except UnicodeDecodeError:
                malformed += 1
                continue
        elif isinstance(raw_line, str):
            line = raw_line
        else:
            malformed += 1
            continue

        line = line.strip()
        if not line:
            malformed += 1
            continue

        match = _LOG_RE.match(line)
        if match is None:
            malformed += 1
            continue

        request_parts = match.group("request").split()
        if len(request_parts) != 3:
            malformed += 1
            continue

        _, path, _ = request_parts

        hour = _hour_key(match.group("timestamp"))
        if hour is None:
            malformed += 1
            continue

        status = int(match.group("status"))
        bytes_field = match.group("bytes")
        bytes_sent = 0 if bytes_field == "-" else int(bytes_field)

        total_requests += 1
        unique_ips.add(match.group("ip"))
        status_counts[status] = status_counts.get(status, 0) + 1
        bytes_total += bytes_sent

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
        "unique_ips": len(unique_ips),
        "status_counts": status_counts,
        "bytes_total": bytes_total,
        "error_rate": error_rate,
        "top_paths": top_paths,
        "requests_per_hour": dict(hour_counts),
    }
