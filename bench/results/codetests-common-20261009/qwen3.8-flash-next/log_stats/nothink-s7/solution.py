import re
from collections import defaultdict
from typing import Iterable


def analyze_log(lines: Iterable[str]) -> dict:
    # Regex to parse Common Log Format
    # ip ident user [timestamp] "METHOD path PROTOCOL" status bytes
    log_pattern = re.compile(
        r'^(\S+)\s+'           # ip
        r'(\S+)\s+'            # ident
        r'(\S+)\s+'            # user
        r'\[([^\]]+)\]\s+'     # timestamp
        r'"(\S+)\s+(\S+)\s+(\S+)"\s+'  # METHOD, path, PROTOCOL
        r'(\d+)\s+'            # status
        r'(\d+|-)\s*$'         # bytes
    )

    total_requests = 0
    malformed = 0
    unique_ips = set()
    status_counts = defaultdict(int)
    bytes_total = 0
    path_counts = defaultdict(int)
    requests_per_hour = defaultdict(int)

    # Month mapping
    month_map = {
        'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
        'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
        'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
    }

    for line in lines:
        line = line.strip()
        if not line:
            malformed += 1
            continue

        match = log_pattern.match(line)
        if not match:
            malformed += 1
            continue

        ip, ident, user, timestamp, method, path, protocol, status_str, bytes_str = match.groups()

        # Validate status is numeric (regex already ensures digits, but just in case)
        try:
            status = int(status_str)
        except ValueError:
            malformed += 1
            continue

        # Parse bytes
        if bytes_str == '-':
            bytes_val = 0
        else:
            try:
                bytes_val = int(bytes_str)
            except ValueError:
                malformed += 1
                continue

        # Parse timestamp: e.g., 10/Oct/2026:13:55:36 +0000
        # Format: DD/Mon/YYYY:HH:MM:SS +ZZZZ
        ts_match = re.match(r'^(\d{2})/(\w{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2})\s+[+-]\d{4}$', timestamp)
        if not ts_match:
            malformed += 1
            continue

        day, mon_str, year, hour, minute, second = ts_match.groups()
        mon = month_map.get(mon_str)
        if mon is None:
            malformed += 1
            continue

        # Build hour key: YYYY-MM-DD HH
        hour_key = f"{year}-{mon}-{day} {hour}"
        requests_per_hour[hour_key] += 1

        # Process path: remove query string
        if '?' in path:
            clean_path = path.split('?', 1)[0]
        else:
            clean_path = path

        path_counts[clean_path] += 1
        unique_ips.add(ip)
        status_counts[status] += 1
        bytes_total += bytes_val
        total_requests += 1

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
        "unique_ips": len(unique_ips),
        "status_counts": dict(status_counts),
        "bytes_total": bytes_total,
        "error_rate": error_rate,
        "top_paths": top_paths,
        "requests_per_hour": dict(requests_per_hour),
    }
