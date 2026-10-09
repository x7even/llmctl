import re
from collections import Counter, defaultdict
from typing import Iterable


def analyze_log(lines: Iterable[str]) -> dict:
    """Summarise a web server access log in Common Log Format."""

    # Regex for Common Log Format:
    # ip ident user [timestamp] "METHOD path PROTOCOL" status bytes
    log_pattern = re.compile(
        r'^(\S+)\s+'          # IP
        r'(\S+)\s+'           # ident
        r'(\S+)\s+'           # user
        r'\[([^\]]+)\]\s+'    # timestamp
        r'"(\S+)\s+(\S+)\s+(\S+)"\s+'  # request: method path protocol
        r'(\d{3})\s+'         # status (3 digits)
        r'(\S+)\s*$'          # bytes
    )

    # Month abbreviation to number mapping
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
        line = line.rstrip('\n').rstrip('\r')
        if not line.strip():
            malformed += 1
            continue

        match = log_pattern.match(line)
        if not match:
            malformed += 1
            continue

        ip, ident, user, timestamp, method, path, protocol, status_str, bytes_str = match.groups()

        # Validate status is a valid 3-digit number
        try:
            status = int(status_str)
        except ValueError:
            malformed += 1
            continue

        # Validate bytes: either a number or '-'
        if bytes_str == '-':
            bytes_val = 0
        else:
            try:
                bytes_val = int(bytes_str)
            except ValueError:
                malformed += 1
                continue

        # Validate timestamp format: DD/Mon/YYYY:HH:MM:SS +ZZZZ
        ts_match = re.match(r'^(\d{2})/([A-Za-z]{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2})\s+([+-]\d{4})$', timestamp)
        if not ts_match:
            malformed += 1
            continue

        day = int(ts_match.group(1))
        mon = ts_match.group(2)
        year = int(ts_match.group(3))
        hour = int(ts_match.group(4))
        minute = int(ts_match.group(5))
        second = int(ts_match.group(6))

        if mon not in month_map:
            malformed += 1
            continue

        month = month_map[mon]

        # Validate date/time ranges
        if not (1 <= month <= 12):
            malformed += 1
            continue
        if not (1 <= day <= 31):
            malformed += 1
            continue
        if not (0 <= hour <= 23):
            malformed += 1
            continue
        if not (0 <= minute <= 59):
            malformed += 1
            continue
        if not (0 <= second <= 59):
            malformed += 1
            continue

        # All validations passed - this is a valid line
        total_requests += 1
        unique_ips.add(ip)
        status_counts[status] += 1
        bytes_total += bytes_val

        # Error rate: status 400-599
        if 400 <= status <= 599:
            error_count += 1

        # Path without query string
        clean_path = path.split('?', 1)[0]
        path_counts[clean_path] += 1

        # Requests per hour: "YYYY-MM-DD HH"
        hour_key = f"{year:04d}-{month:02d}-{day:02d} {hour:02d}"
        requests_per_hour[hour_key] += 1

    # Error rate
    if total_requests > 0:
        error_rate = round(error_count / total_requests, 4)
    else:
        error_rate = 0.0

    # Top paths: 3 most requested, sorted by count desc then path asc
    top_paths = sorted(path_counts.items(), key=lambda x: (-x[1], x[0]))[:3]

    # Build status_counts as a plain dict
    status_counts_dict = dict(status_counts)

    # Build requests_per_hour as a plain dict
    requests_per_hour_dict = dict(requests_per_hour)

    return {
        "total_requests": total_requests,
        "malformed": malformed,
        "unique_ips": len(unique_ips),
        "status_counts": status_counts_dict,
        "bytes_total": bytes_total,
        "error_rate": error_rate,
        "top_paths": top_paths,
        "requests_per_hour": requests_per_hour_dict,
    }
