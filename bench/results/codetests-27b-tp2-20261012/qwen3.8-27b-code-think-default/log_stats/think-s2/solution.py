from collections import Counter
from typing import Iterable

import re


def analyze_log(lines: Iterable[str]) -> dict:
    pattern = re.compile(
        r'^(\S+) (\S+) (\S+) \[([^\]]+)\] "(\S+) (\S+) (\S+)" (\S+) (\S+)$'
    )

    month_map = {
        'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
        'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
        'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12',
    }

    total_requests = 0
    malformed = 0
    ips = set()
    status_counts: dict[int, int] = {}
    bytes_total = 0
    error_count = 0
    path_counts: Counter = Counter()
    hour_counts: dict[str, int] = {}

    for raw_line in lines:
        line = raw_line.strip()

        if not line:
            malformed += 1
            continue

        m = pattern.match(line)
        if not m:
            malformed += 1
            continue

        ip, _ident, _user, timestamp, _method, path, _protocol, status_str, bytes_str = m.groups()

        # Status must be a non-negative integer
        if not status_str.isdigit():
            malformed += 1
            continue

        # Bytes must be a non-negative integer or '-'
        if bytes_str != '-' and not bytes_str.isdigit():
            malformed += 1
            continue

        # Validate timestamp: DD/Mon/YYYY:HH:MM:SS +ZZZZ
        ts_parts = timestamp.split(' ')
        if len(ts_parts) != 2:
            malformed += 1
            continue
        date_part = ts_parts[0]
        date_fields = date_part.split('/')
        if len(date_fields) != 3:
            malformed += 1
            continue
        day, mon, rest = date_fields
        rest_parts = rest.split(':')
        if len(rest_parts) != 3:
            malformed += 1
            continue
        year, hour, minute = rest_parts
        if not (day.isdigit() and year.isdigit() and hour.isdigit() and minute.isdigit()):
            malformed += 1
            continue
        if mon not in month_map:
            malformed += 1
            continue

        # --- All valid; accumulate statistics ---
        status = int(status_str)
        bytes_val = 0 if bytes_str == '-' else int(bytes_str)

        total_requests += 1
        ips.add(ip)
        status_counts[status] = status_counts.get(status, 0) + 1
        bytes_total += bytes_val

        if 400 <= status <= 599:
            error_count += 1

        clean_path = path.split('?', 1)[0]
        path_counts[clean_path] += 1

        hour_key = f"{year}-{month_map[mon]}-{day} {hour}"
        hour_counts[hour_key] = hour_counts.get(hour_key, 0) + 1

    error_rate = round(error_count / total_requests, 4) if total_requests else 0.0

    top_paths = sorted(path_counts.items(), key=lambda x: (-x[1], x[0]))[:3]

    return {
        "total_requests": total_requests,
        "malformed": malformed,
        "unique_ips": len(ips),
        "status_counts": status_counts,
        "bytes_total": bytes_total,
        "error_rate": error_rate,
        "top_paths": top_paths,
        "requests_per_hour": hour_counts,
    }
