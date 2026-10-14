import re
from collections import Counter
from typing import Iterable, Dict, Any

# Common Log Format pattern:
# ip ident user [timestamp] "METHOD path PROTOCOL" status bytes
# Example: 127.0.0.1 - frank [10/Oct/2026:13:55:36 +0000] "GET /index.html?x=1 HTTP/1.1" 200 2326

LOG_PATTERN = re.compile(
    r'^(\S+)\s+'           # ip
    r'(\S+)\s+'            # ident
    r'(\S+)\s+'            # user
    r'\[([^\]]+)\]\s+'     # timestamp
    r'"([A-Z]+)\s+'        # method
    r'(\S+)\s+'            # path (may include query string)
    r'(\S+)"\s+'           # protocol
    r'(\d+)\s+'            # status
    r'(\d+|-)$'            # bytes
)

# Month abbreviation to number mapping
MONTH_MAP = {
    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
}

# Timestamp pattern: DD/Mon/YYYY:HH:MM:SS +ZZZZ or -ZZZZ
TIMESTAMP_PATTERN = re.compile(
    r'^(\d{2})/([A-Za-z]{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2})\s+[+-]\d{4}$'
)


def analyze_log(lines: Iterable[str]) -> Dict[str, Any]:
    total_requests = 0
    malformed = 0
    ips = set()
    status_counts = Counter()
    bytes_total = 0
    path_counts = Counter()
    requests_per_hour = Counter()

    for line in lines:
        line = line.strip()
        if not line:
            malformed += 1
            continue

        match = LOG_PATTERN.match(line)
        if not match:
            malformed += 1
            continue

        ip, ident, user, timestamp, method, path_with_query, protocol, status_str, bytes_str = match.groups()

        # Validate status is numeric (already ensured by \d+ in regex)
        status = int(status_str)

        # Parse bytes
        if bytes_str == '-':
            byte_count = 0
        else:
            byte_count = int(bytes_str)

        # Validate timestamp
        ts_match = TIMESTAMP_PATTERN.match(timestamp)
        if not ts_match:
            malformed += 1
            continue

        day, month_abbr, year, hour, minute, second = ts_match.groups()

        # Validate month abbreviation
        if month_abbr not in MONTH_MAP:
            malformed += 1
            continue

        month_num = MONTH_MAP[month_abbr]

        # Extract path without query string
        if '?' in path_with_query:
            path = path_with_query.split('?')[0]
        else:
            path = path_with_query

        # Valid line
        total_requests += 1
        ips.add(ip)
        status_counts[status] += 1
        bytes_total += byte_count
        path_counts[path] += 1

        # Hour key: YYYY-MM-DD HH
        hour_key = f"{year}-{month_num}-{day} {hour}"
        requests_per_hour[hour_key] += 1

    # Compute error_rate
    if total_requests == 0:
        error_rate = 0.0
    else:
        error_count = sum(count for status, count in status_counts.items() if 400 <= status <= 599)
        error_rate = round(error_count / total_requests, 4)

    # Top 3 paths: sorted by count descending, then path ascending
    # Get all paths with their counts, sort by (-count, path)
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
        "requests_per_hour": dict(requests_per_hour),
    }
