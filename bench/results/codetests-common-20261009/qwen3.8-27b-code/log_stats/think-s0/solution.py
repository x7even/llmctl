import re
from typing import Iterable

_CLF_RE = re.compile(
    r'^(?P<ip>\S+) (?P<ident>\S+) (?P<user>\S+) '
    r'\[(?P<timestamp>[^\]]+)\] '
    r'"(?P<method>\S+) (?P<path>\S+) (?P<protocol>\S+)" '
    r'(?P<status>\d+) (?P<bytes>\d+|-)$',
    re.ASCII,
)

_TS_RE = re.compile(
    r'^(?P<day>\d{1,2})/(?P<month>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'
    r'/(?P<year>\d{4}):(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2}) '
    r'(?P<tz>[+-]\d{4})$',
    re.ASCII,
)

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


def _parse_hour(timestamp: str):
    match = _TS_RE.fullmatch(timestamp)
    if match is None:
        return None

    day = int(match.group("day"))
    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    second = int(match.group("second"))
    year = int(match.group("year"))
    month = _MONTHS[match.group("month")]

    if not (
        1 <= day <= 31
        and 0 <= hour <= 23
        and 0 <= minute <= 59
        and 0 <= second <= 59
    ):
        return None

    return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}"


def analyze_log(lines: Iterable[str]) -> dict:
    if isinstance(lines, str):
        lines = lines.splitlines()

    total_requests = 0
    malformed = 0
    unique_ips = set()
    status_counts = {}
    bytes_total = 0
    error_count = 0
    path_counts = {}
    requests_per_hour = {}

    for raw in lines:
        if not isinstance(raw, str):
            malformed += 1
            continue

        line = raw.strip()
        if not line:
            malformed += 1
            continue

        match = _CLF_RE.fullmatch(line)
        if match is None:
            malformed += 1
            continue

        hour = _parse_hour(match.group("timestamp"))
        if hour is None:
            malformed += 1
            continue

        total_requests += 1
        unique_ips.add(match.group("ip"))

        status = int(match.group("status"))
        status_counts[status] = status_counts.get(status, 0) + 1
        if 400 <= status <= 599:
            error_count += 1

        bytes_field = match.group("bytes")
        if bytes_field != "-":
            bytes_total += int(bytes_field)

        path = match.group("path").split("?", 1)[0]
        path_counts[path] = path_counts.get(path, 0) + 1

        requests_per_hour[hour] = requests_per_hour.get(hour, 0) + 1

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
        "requests_per_hour": requests_per_hour,
    }
