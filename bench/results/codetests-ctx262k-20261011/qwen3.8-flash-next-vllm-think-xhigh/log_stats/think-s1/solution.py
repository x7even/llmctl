import re
from collections import Counter
from datetime import date
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
    r"""
    ^(?P<ip>\S+)
    \s+(?P<ident>\S+)
    \s+(?P<user>\S+)
    \s+\[(?P<timestamp>[^\]]+)\]
    \s+"(?P<request>[^"]*)"
    \s+(?P<status>[0-9]+)
    \s+(?P<bytes>[0-9]+|-)
    \s*$
    """,
    re.VERBOSE,
)

_TIMESTAMP_RE = re.compile(
    r"""
    ^(?P<day>[0-9]{2})/
    (?P<month>[A-Za-z]{3})/
    (?P<year>[0-9]{4}):
    (?P<hour>[0-9]{2}):(?P<minute>[0-9]{2}):(?P<second>[0-9]{2})
    (?:\s*(?P<tz>[+-][0-9]{4}))?
    \s*$
    """,
    re.VERBOSE,
)


def _parse_hour(timestamp: str) -> Optional[str]:
    m = _TIMESTAMP_RE.match(timestamp)
    if not m:
        return None

    month = _MONTHS.get(m.group("month").capitalize())
    if month is None:
        return None

    try:
        year = int(m.group("year"))
        day = int(m.group("day"))
        hour = int(m.group("hour"))
        minute = int(m.group("minute"))
        second = int(m.group("second"))
    except ValueError:
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

    return "{:04d}-{:02d}-{:02d} {:02d}".format(year, month, day, hour)


def analyze_log(lines: Iterable[str]) -> dict:
    if lines is None:
        lines = []
    elif isinstance(lines, (bytes, bytearray)):
        lines = lines.decode("utf-8", "replace").splitlines()
    elif isinstance(lines, str):
        lines = lines.splitlines()

    total_requests = 0
    malformed = 0
    ips = set()
    status_counts = {}
    bytes_total = 0
    errors = 0
    path_counter = Counter()
    hourly = Counter()

    for line in lines:
        if isinstance(line, (bytes, bytearray)):
            line = line.decode("utf-8", "replace")
        elif not isinstance(line, str):
            malformed += 1
            continue

        line = line.rstrip("\r\n")
        if not line.strip():
            malformed += 1
            continue

        m = _LOG_RE.match(line)
        if not m:
            malformed += 1
            continue

        hour = _parse_hour(m.group("timestamp"))
        if hour is None:
            malformed += 1
            continue

        parts = m.group("request").split()
        if len(parts) != 3:
            malformed += 1
            continue

        path = parts[1].split("?", 1)[0]

        try:
            status = int(m.group("status"))
        except ValueError:
            malformed += 1
            continue

        bytes_field = m.group("bytes")
        if bytes_field == "-":
            bytes_sent = 0
        else:
            try:
                bytes_sent = int(bytes_field)
            except ValueError:
                malformed += 1
                continue

        total_requests += 1
        ips.add(m.group("ip"))
        status_counts[status] = status_counts.get(status, 0) + 1
        bytes_total += bytes_sent
        if 400 <= status <= 599:
            errors += 1
        path_counter[path] += 1
        hourly[hour] += 1

    error_rate = round(errors / total_requests, 4) if total_requests else 0.0
    top_paths = sorted(path_counter.items(), key=lambda item: (-item[1], item[0]))[:3]

    return {
        "total_requests": total_requests,
        "malformed": malformed,
        "unique_ips": len(ips),
        "status_counts": {status: status_counts[status] for status in sorted(status_counts)},
        "bytes_total": bytes_total,
        "error_rate": error_rate,
        "top_paths": top_paths,
        "requests_per_hour": {hour: hourly[hour] for hour in sorted(hourly)},
    }
