from typing import Iterable
from collections import Counter
import re
from datetime import date

__all__ = ["analyze_log"]

_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

_LOG_RE = re.compile(
    r"^\s*(?P<ip>\S+)\s+(?P<ident>\S+)\s+(?P<user>\S+)\s+"
    r"\[(?P<day>\d{2})/(?P<month>[A-Za-z]{3})/(?P<year>\d{4}):"
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})\s+[+-]\d{4}\]\s+"
    r'"(?P<request>[^"]*)"\s+'
    r"(?P<status>\d+)\s+"
    r"(?P<bytes>\d+|-)\s*$"
)


def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0

    unique_ips = set()
    status_counts = Counter()
    path_counts = Counter()
    hour_counts = Counter()

    bytes_total = 0
    error_count = 0

    for raw_line in lines:
        if not isinstance(raw_line, str):
            malformed += 1
            continue

        line = raw_line.strip()
        if not line:
            malformed += 1
            continue

        match = _LOG_RE.match(line)
        if not match:
            malformed += 1
            continue

        month = _MONTHS.get(match.group("month").lower())
        if month is None:
            malformed += 1
            continue

        day = int(match.group("day"))
        year = int(match.group("year"))
        hour = int(match.group("hour"))
        minute = int(match.group("minute"))
        second = int(match.group("second"))

        if not (1 <= day <= 31 and 0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
            malformed += 1
            continue

        try:
            date(year, month, day)
        except ValueError:
            malformed += 1
            continue

        request_parts = match.group("request").split()
        if len(request_parts) != 3:
            malformed += 1
            continue

        path = request_parts[1].split("?", 1)[0]

        status = int(match.group("status"))
        raw_bytes = match.group("bytes")
        size = 0 if raw_bytes == "-" else int(raw_bytes)

        total_requests += 1
        unique_ips.add(match.group("ip"))
        status_counts[status] += 1
        bytes_total += size

        if 400 <= status <= 599:
            error_count += 1

        path_counts[path] += 1
        hour_key = f"{year:04d}-{month:02d}-{day:02d} {hour:02d}"
        hour_counts[hour_key] += 1

    error_rate = 0.0 if total_requests == 0 else round(error_count / total_requests, 4)

    top_paths = sorted(path_counts.items(), key=lambda item: (-item[1], item[0]))[:3]

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
