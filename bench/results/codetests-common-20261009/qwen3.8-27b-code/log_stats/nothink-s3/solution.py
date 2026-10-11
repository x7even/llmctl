import re
from collections import Counter
from typing import Iterable


def analyze_log(lines: Iterable[str]) -> dict:
    """
    Summarise a web server access log in Common Log Format.

    Each valid line looks like:
    127.0.0.1 - frank [10/Oct/2026:13:55:36 +0000] "GET /index.html?x=1 HTTP/1.1" 200 2326

    Returns a dict with keys:
      - "total_requests"
      - "malformed"
      - "unique_ips"
      - "status_counts"
      - "bytes_total"
      - "error_rate"
      - "top_paths"
      - "requests_per_hour"
    """
    # Regex to match Common Log Format
    # ip ident user [timestamp] "METHOD path PROTOCOL" status bytes
    # ip: one or more non-space chars
    # ident: one or more non-space chars (or -)
    # user: one or more non-space chars (or -)
    # timestamp: inside brackets
    # request: inside quotes, with method, path, protocol
    # status: integer
    # bytes: integer or -

    pattern = re.compile(
        r'^(\S+)\s+(\S+)\s+(\S+)\s+\[([^\]]+)\]\s+"(\S+)\s+(\S+)\s+(\S+)"\s+(\d+)\s+(\d+|-)\s*$'
    )

    # Month mapping
    month_map = {
        'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4,
        'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8,
        'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
    }

    total_requests = 0
    malformed = 0
    unique_ips = set()
    status_counts = Counter()
    bytes_total = 0
    path_counts = Counter()
    requests_per_hour = Counter()
    error_count = 0

    for line in lines:
        line = line.rstrip('\n\r')
        if not line.strip():
            malformed += 1
            continue

        match = pattern.match(line)
        if not match:
            malformed += 1
            continue

        ip, ident, user, timestamp, method, path, protocol, status_str, bytes_str = match.groups()

        # Validate status is numeric (already ensured by regex \d+)
        status = int(status_str)

        # Parse bytes
        if bytes_str == '-':
            bytes_val = 0
        else:
            bytes_val = int(bytes_str)

        # Parse timestamp: e.g., 10/Oct/2026:13:55:36 +0000
        # We need to extract YYYY-MM-DD HH
        ts_match = re.match(r'^(\d{2})/(\w{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2})\s+([+-]\d{4})$', timestamp)
        if not ts_match:
            malformed += 1
            continue

        day_str, mon_str, year_str, hour_str, min_str, sec_str, tz = ts_match.groups()

        if mon_str not in month_map:
            malformed += 1
            continue

        month_num = month_map[mon_str]
        day = int(day_str)
        year = int(year_str)
        hour = int(hour_str)

        # Format hour key: "YYYY-MM-DD HH"
        hour_key = f"{year:04d}-{month_num:02d}-{day:02d} {hour:02d}"

        # Strip query string from path
        if '?' in path:
            path_only = path.split('?', 1)[0]
        else:
            path_only = path

        # Update counters
        total_requests += 1
        unique_ips.add(ip)
        status_counts[status] += 1
        bytes_total += bytes_val
        path_counts[path_only] += 1
        requests_per_hour[hour_key] += 1

        if 400 <= status <= 599:
            error_count += 1

    # Compute error rate
    if total_requests > 0:
        error_rate = round(error_count / total_requests, 4)
    else:
        error_rate = 0.0

    # Top paths: 3 most requested, sorted by count desc then path asc
    top_paths_list = sorted(path_counts.items(), key=lambda x: (-x[1], x[0]))
    top_paths = top_paths_list[:3]

    # Status counts as dict with int keys
    status_counts_dict = dict(status_counts)

    return {
        "total_requests": total_requests,
        "malformed": malformed,
        "unique_ips": len(unique_ips),
        "status_counts": status_counts_dict,
        "bytes_total": bytes_total,
        "error_rate": error_rate,
        "top_paths": top_paths,
        "requests_per_hour": dict(requests_per_hour),
    }
