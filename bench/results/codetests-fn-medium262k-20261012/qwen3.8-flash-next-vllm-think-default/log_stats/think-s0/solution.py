import re
from collections import Counter
from datetime import datetime
from typing import Iterable

_LOG_RE = re.compile(
    r'^(\S+) (\S+) (\S+) \[([^\]]+)\] "(\S+) (\S+) (\S+)" (\d+) (\S+)$'
)


def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0
    ips: set[str] = set()
    status_counts: Counter = Counter()
    bytes_total = 0
    path_counts: Counter = Counter()
    hour_counts: Counter = Counter()

    for line in lines:
        line = line.strip()
        m = _LOG_RE.match(line)
        if not m:
            malformed += 1
            continue

        ip = m.group(1)
        timestamp = m.group(4)
        path = m.group(6)
        status_str = m.group(8)
        bytes_str = m.group(9)

        # status is guaranteed numeric by (\d+) in the regex
        status = int(status_str)

        # bytes: '-' means 0, otherwise must be a non-negative integer
        if bytes_str == '-':
            b = 0
        elif bytes_str.isdigit():
            b = int(bytes_str)
        else:
            malformed += 1
            continue

        # parse timestamp (ignore timezone offset for grouping)
        try:
            dt = datetime.strptime(timestamp, "%d/%b/%Y:%H:%M:%S %z")
        except ValueError:
            malformed += 1
            continue

        # strip query string
        path_no_query = path.split('?', 1)[0]

        # accumulate
        total_requests += 1
        ips.add(ip)
        status_counts[status] += 1
        bytes_total += b
        path_counts[path_no_query] += 1
        hour_key = dt.strftime("%Y-%m-%d %H")
        hour_counts[hour_key] += 1

    # error rate (400-599 inclusive)
    error_count = sum(v for k, v in status_counts.items() if 400 <= k <= 599)
    error_rate = round(error_count / total_requests, 4) if total_requests > 0 else 0.0

    # top 3 paths: sort by count desc, then path asc
    top_paths = sorted(path_counts.items(), key=lambda x: (-x[1], x[0]))[:3]

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
