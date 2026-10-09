import re
from collections import defaultdict
from typing import Iterable, Dict, List, Tuple


def analyze_log(lines: Iterable[str]) -> dict:
    """
    Analyse a web server access log in Common Log Format.

    Each valid line looks like:
        ip ident user [timestamp] "METHOD path PROTOCOL" status bytes

    Returns a dict with summary statistics.
    """
    # Regex to match Common Log Format lines
    # ip: \S+
    # ident: \S+
    # user: \S+
    # timestamp: [10/Oct/2026:13:55:36 +0000]
    # request: "GET /index.html?x=1 HTTP/1.1"
    # status: 200
    # bytes: 2326 or -
    log_pattern = re.compile(
        r'^(\S+)\s+(\S+)\s+(\S+)\s+'
        r'\[([^\]]+)\]\s+'
        r'"(\S+)\s+(\S+)\s+(\S+)"\s+'
        r'(\d+)\s+'
        r'(\d+|-)\s*$'
    )

    month_map = {
        'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4,
        'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8,
        'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
    }

    total_requests = 0
    malformed = 0
    ips = set()
    status_counts = defaultdict(int)
    bytes_total = 0
    error_count = 0
    path_counts = defaultdict(int)
    requests_per_hour = defaultdict(int)

    for line in lines:
        line = line.rstrip('\n').rstrip('\r')
        if not line.strip():
            malformed += 1
            continue

        match = log_pattern.match(line)
        if not match:
            malformed += 1
            continue

        ip, ident, user, timestamp, method, path, protocol, status_str, bytes_str = match.groups()

        # Validate status is numeric (already ensured by regex \d+, but let's be safe)
        try:
            status = int(status_str)
        except ValueError:
            malformed += 1
            continue

        # Parse bytes
        if bytes_str == '-':
            byte_count = 0
        else:
            try:
                byte_count = int(bytes_str)
            except ValueError:
                malformed += 1
                continue

        # Parse timestamp to get hour
        # Format: 10/Oct/2026:13:55:36 +0000
        # We need YYYY-MM-DD HH
        try:
            # Split the timestamp
            # e.g., "10/Oct/2026:13:55:36 +0000"
            # Remove the timezone part
            ts_part = timestamp.split(' ')[0] if ' ' in timestamp else timestamp
            # ts_part is like "10/Oct/2026:13:55:36"
            # Split by / and :
            parts = ts_part.split('/')
            if len(parts) != 3:
                malformed += 1
                continue
            day_str = parts[0]
            month_str = parts[1]
            rest = parts[2]
            # rest is like "2026:13:55:36"
            rest_parts = rest.split(':')
            if len(rest_parts) != 3:
                malformed += 1
                continue
            year_str = rest_parts[0]
            hour_str = rest_parts[1]
            minute_str = rest_parts[2]

            # Validate day, year, hour, minute are numeric
            if not day_str.isdigit() or not year_str.isdigit() or not hour_str.isdigit() or not minute_str.isdigit():
                malformed += 1
                continue

            if month_str not in month_map:
                malformed += 1
                continue

            year = int(year_str)
            month = month_map[month_str]
            day = int(day_str)
            hour = int(hour_str)

            # Basic validation
            if not (1 <= day <= 31) or not (0 <= hour <= 23) or not (0 <= int(minute_str) <= 59):
                malformed += 1
                continue

            hour_key = f"{year:04d}-{month:02d}-{day:02d} {hour:02d}"
        except (ValueError, IndexError):
            malformed += 1
            continue

        # All validations passed
        total_requests += 1
        ips.add(ip)
        status_counts[status] += 1
        bytes_total += byte_count

        if 400 <= status <= 599:
            error_count += 1

        # Extract path without query string
        if '?' in path:
            clean_path = path.split('?', 1)[0]
        else:
            clean_path = path
        path_counts[clean_path] += 1

        requests_per_hour[hour_key] += 1

    # Calculate error rate
    if total_requests > 0:
        error_rate = round(error_count / total_requests, 4)
    else:
        error_rate = 0.0

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
        "requests_per_hour": dict(requests_per_hour),
    }
