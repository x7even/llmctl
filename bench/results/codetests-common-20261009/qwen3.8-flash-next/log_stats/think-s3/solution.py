import re
from collections import Counter
from datetime import datetime
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
    r"(?P<ip>\S+) (?P<ident>\S+) (?P<user>\S+) "
    r"\[(?P<timestamp>[^\]]+)\] "
    r'"(?P<method>[^"\s]+) (?P<path>[^"\s]+) (?P<protocol>[^"\s]+)" '
    r"(?P<status>\d+) (?P<bytes>\d+|-)"
)

_TIMESTAMP_RE = re.compile(
    r"(?P<day>\d{2})/"
    r"(?P<month>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)/"
    r"(?P<year>\d{4}):(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2}) "
    r"(?P<tz>[+-]\d{4})"
)


def _hour_key(timestamp: str) -> str | None:
    match = _TIMESTAMP_RE.fullmatch(timestamp)
    if not match:
        return None

    month = _MONTHS.get(match.group("month"))
    if month is None:
        return None

    try:
        year = int(match.group("year"))
        day = int(match.group("day"))
        hour = int(match.group("hour"))
        minute = int(match.group("minute"))
        second = int(match.group("second"))
        datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None

    return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}"


def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0
    bytes_total = 0
    error_requests = 0

    unique_ips = set()
    status_counts = Counter()
    path_counts = Counter()
    requests_per_hour = Counter()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            malformed += 1
            continue

        match = _LINE_RE.fullmatch(stripped)
        if not match:
            malformed += 1
            continue

        hour_key = _hour_key(match.group("timestamp"))
        if hour_key is None:
            malformed += 1
            continue

        status_text = match.group("status")
        bytes_text = match.group("bytes")

        try:
            status = int(status_text)
            bytes_sent = 0 if bytes_text == "-" else int(bytes_text)
        except ValueError:
            malformed += 1
            continue

        total_requests += 1
        unique_ips.add(match.group("ip"))
        status_counts[status] += 1
        bytes_total += bytes_sent

        if 400 <= status <= 599:
            error_requests += 1

        path = match.group("path").split("?", 1)[0]
        path_counts[path] += 1
        requests_per_hour[hour_key] += 1

    error_rate = round(error_requests / total_requests, 4) if total_requests else 0.0
    top_paths = sorted(path_counts.items(), key=lambda item: (-item[1], item[0]))[:3]

    return {
        "total_requests": total_requests,
        "malformed": malformed,
        "unique_ips": len(unique_ips),
        "status_counts": dict(sorted(status_counts.items())),
        "bytes_total": bytes_total,
        "error_rate": error_rate,
        "top_paths": top_paths,
        "requests_per_hour": dict(sorted(requests_per_hour.items())),
    }
