from __future__ import annotations

import re
from collections import Counter
from typing import Iterable


def analyze_log(lines: Iterable[str]) -> dict:
    pattern = re.compile(
        r'^(\S+) (\S+) (\S+) \[([^\]]+)\] "(\S+) (\S+) (\S+)" (\d+) (\d+|-)\s*$'
    )

    month_map = {
        'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
        'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
        'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12',
    }

    total_requests = 0
    malformed = 0
    ips: set[str] = set()
    status_counts: dict[int, int] = {}
    bytes_total = 0
    error_count = 0
    path_counts: Counter[str] = Counter()
    hour_counts: dict[str, int] = {}

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            malformed += 1
            continue

        m = pattern.match(line)
        if m is None:
            malformed += 1
            continue

        ip, _ident, _user, timestamp, _method, path, _protocol, status_str, bytes_str = m.groups()

        status = int(status_str)
        size = 0 if bytes_str == '-' else int(bytes_str)

        total_requests += 1
        ips.add(ip)
        status_counts[status] = status_counts.get(status, 0) + 1
        bytes_total += size

        if 400 <= status <= 599:
            error_count += 1

        clean_path = path.split('?', 1)[0]
        path_counts[clean_path] += 1

        # Parse timestamp: "10/Oct/2026:13:55:36 +0000"
        try:
            date_part = timestamp.split(' ', 1)[0]
            day_str, month_str, rest = date_part.split('/', 2)
            year_str, time_str = rest.split(':', 1)
            hour_str = time_str.split(':', 1)[0]

            month_num = month_map.get(month_str)
            if month_num is not None:
                hour_key = f"{year_str}-{month_num}-{day_str.zfill(2)} {hour_str}"
                hour_counts[hour_key] = hour_counts.get(hour_key, 0) + 1
        except (ValueError, IndexError):
            pass

    error_rate = round(error_count / total_requests, 4) if total_requests > 0 else 0.0

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
