import re
from collections import defaultdict
from datetime import datetime
from typing import Iterable

# Pattern for Common Log Format
# ip ident user [timestamp] "METHOD path PROTOCOL" status bytes
LOG_PATTERN = re.compile(
    r'^(\S+)\s+'           # ip
    r'(\S+)\s+'            # ident
    r'(\S+)\s+'            # user
    r'\[([^\]]+)\]\s+'     # timestamp
    r'"(\S+)\s+(\S+)\s+(\S+)"\s+'  # method, path, protocol
    r'(\d{3})\s+'          # status
    r'(-|\d+)$'            # bytes
)

MONTH_MAP = {
    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4,
    'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8,
    'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
}


def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0
    ips = set()
    status_counts = defaultdict(int)
    bytes_total = 0
    path_counts = defaultdict(int)
    hour_counts = defaultdict(int)

    for line in lines:
        line = line.strip()
        if not line:
            malformed += 1
            continue

        match = LOG_PATTERN.match(line)
        if not match:
            malformed += 1
            continue

        ip, ident, user, timestamp, method, path, protocol, status_str, bytes_str = match.groups()

        # Validate status is numeric (already ensured by regex \d{3}, but double-check)
        try:
            status = int(status_str)
        except ValueError:
            malformed += 1
            continue

        # Parse bytes
        if bytes_str == '-':
            bytes_sent = 0
        else:
            try:
                bytes_sent = int(bytes_str)
            except ValueError:
                malformed += 1
                continue

        # Parse timestamp to extract hour
        # Format: 10/Oct/2026:13:55:36 +0000
        try:
            # Extract date and time part before timezone
            ts_no_tz = timestamp.split()[0]  # e.g., "10/Oct/2026:13:55:36"
            # Parse: DD/Mon/YYYY:HH:MM:SS
            day_str, rest = ts_no_tz.split('/', 1)
            month_str, rest2 = rest.split('/', 1)
            year_str, time_str = rest2.split(':', 1)

            day = int(day_str)
            month = MONTH_MAP.get(month_str)
            if month is None:
                malformed += 1
                continue
            year = int(year_str)
            hour_str, minute_str, second_str = time_str.split(':')
            hour = int(hour_str)
            minute = int(minute_str)
            second = int(second_str)

            # Validate ranges roughly
            if not (1 <= day <= 31 and 1 <= month <= 12 and 0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 60):
                malformed += 1
                continue

            hour_key = f"{year:04d}-{month:02d}-{day:02d} {hour:02d}"
        except (ValueError, KeyError):
            malformed += 1
            continue

        # Extract path without query string
        if '?' in path:
            path_clean = path.split('?', 1)[0]
        else:
            path_clean = path

        # Valid line
        total_requests += 1
        ips.add(ip)
        status_counts[status] += 1
        bytes_total += bytes_sent
        path_counts[path_clean] += 1
        hour_counts[hour_key] += 1

    # Calculate error rate
    if total_requests == 0:
        error_rate = 0.0
    else:
        error_count = sum(count for status, count in status_counts.items() if 400 <= status <= 599)
        error_rate = round(error_count / total_requests, 4)

    # Top paths: sort by count descending, then path ascending
    sorted_paths = sorted(path_counts.items(), key=lambda x: (-x[1], x[0]))
    top_paths = sorted_paths[:3]

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
