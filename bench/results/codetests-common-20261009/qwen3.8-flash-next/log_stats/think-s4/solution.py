"""Web server access log analysis for Common Log Format."""

import re
from collections import Counter
from collections.abc import Iterable

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
    r'(?P<ip>\S+) (?P<ident>\S+) (?P<user>\S+) '
    r'\[(?P<timestamp>[^\]]+)\] '
    r'"(?P<request>[^"]*)" '
    r'(?P<status>\d+) (?P<bytes>\d+|-)'
)

_REQUEST_RE = re.compile(r'(?P<method>\S+) (?P<path>\S+) (?P<proto>\S+)')

_TIMESTAMP_RE = re.compile(
    r'(?P<day>\d{2})/(?P<month>[A-Za-z]{3})/(?P<year>\d{4}):'
    r'(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2}) (?P<tz>[+-]\d{4})'
)


def analyze_log(lines: Iterable[str]) -> dict:
    if isinstance(lines, str):
        lines = lines.splitlines()

    total_requests = 0
    malformed = 0
    unique_ips = set()
    status_counts = Counter()
    bytes_total = 0
    error_count = 0
    path_counts = Counter()
    hourly_counts = Counter()

    for line in lines:
        if not isinstance(line, str):
            malformed += 1
            continue

        line = line.rstrip("\r\n")

        log_match = _LOG_RE.fullmatch(line)
        if log_match is None:
            malformed += 1
            continue

        ts_match = _TIMESTAMP_RE.fullmatch(log_match.group("timestamp"))
        if ts_match is None:
            malformed += 1
            continue

        month = _MONTHS.get(ts_match.group("month").capitalize())
        if month is None:
            malformed += 1
            continue

        day = int(ts_match.group("day"))
        year = int(ts_match.group("year"))
        hour = int(ts_match.group("hour"))
        minute = int(ts_match.group("minute"))
        second = int(ts_match.group("second"))

        if not (
            1 <= day <= 31
            and 0 <= hour < 24
            and 0 <= minute < 60
            and 0 <= second < 60
        ):
            malformed += 1
            continue

        request_match = _REQUEST_RE.fullmatch(log_match.group("request"))
        if request_match is None:
            malformed += 1
            continue

        status = int(log_match.group("status"))
        bytes_field = log_match.group("bytes")
        bytes_sent = 0 if bytes_field == "-" else int(bytes_field)

        path = request_match.group("path").split("?", 1)[0]

        total_requests += 1
        unique_ips.add(log_match.group("ip"))
        status_counts[status] += 1
        bytes_total += bytes_sent

        if 400 <= status <= 599:
            error_count += 1

        path_counts[path] += 1
        hourly_counts[f"{year:04d}-{month:02d}-{day:02d} {hour:02d}"] += 1

    error_rate = round(error_count / total_requests, 4) if total_requests else 0.0
    top_paths = sorted(path_counts.items(), key=lambda item: (-item[1], item[0]))[:3]

    return {
        "total_requests": total_requests,
        "malformed": malformed,
        "unique_ips": len(unique_ips),
        "status_counts": dict(sorted(status_counts.items())),
        "bytes_total": bytes_total,
        "error_rate": error_rate,
        "top_paths": top_paths,
        "requests_per_hour": dict(sorted(hourly_counts.items())),
    }
