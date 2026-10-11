import re
from collections import Counter
from typing import Iterable

# Regular expression to match Common Log Format
# ip ident user [timestamp] "METHOD path PROTOCOL" status bytes
CLF_PATTERN = re.compile(
    r'^(\S+)\s+'           # ip
    r'(\S+)\s+'            # ident
    r'(\S+)\s+'            # user
    r'\[([^\]]+)\]\s+'     # timestamp
    r'"(\S+)\s+(\S+)\s+(\S+)"\s+'  # method, path, protocol
    r'(\d{3})\s+'          # status
    r'(\S+)$'              # bytes (could be '-' or a number)
)

MONTH_MAP = {
    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12',
}


def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0
    unique_ips = set()
    status_counts = Counter()
    bytes_total = 0
    error_count = 0
    path_counter = Counter()
    requests_per_hour = Counter()

    for line in lines:
        # Strip trailing newline but don't strip leading spaces (they could be part of the format)
        line = line.rstrip('\n\r')
        
        match = CLF_PATTERN.match(line)
        if not match:
            malformed += 1
            continue

        ip = match.group(1)
        ident = match.group(2)
        user = match.group(3)
        timestamp = match.group(4)
        method = match.group(5)
        path = match.group(6)
        protocol = match.group(7)
        status_str = match.group(8)
        bytes_str = match.group(9)

        # Validate status is numeric (the regex already ensures 3 digits, but double-check)
        try:
            status = int(status_str)
        except ValueError:
            malformed += 1
            continue

        # Validate bytes: either '-' or a non-negative integer
        if bytes_str == '-':
            bytes_val = 0
        else:
            try:
                bytes_val = int(bytes_str)
                if bytes_val < 0:
                    malformed += 1
                    continue
            except ValueError:
                malformed += 1
                continue

        # Parse timestamp: format is DD/Mon/YYYY:HH:MM:SS +ZZZZ
        # We need to extract date and hour, ignoring timezone
        # timestamp looks like: 10/Oct/2026:13:55:36 +0000
        # Split off the timezone part
        if ' ' in timestamp:
            timestamp_part, tz_part = timestamp.rsplit(' ', 1)
        else:
            # No timezone? Still might be valid format-wise, but let's try to parse
            timestamp_part = timestamp
            tz_part = ''

        # Parse timestamp_part: DD/Mon/YYYY:HH:MM:SS
        # Split on '/'
        parts = timestamp_part.split('/')
        if len(parts) != 3:
            malformed += 1
            continue
        
        day_str, mon_str, rest = parts
        # rest is YYYY:HH:MM:SS
        if ':' not in rest:
            malformed += 1
            continue
        
        year_hour_min_sec = rest.split(':')
        if len(year_hour_min_sec) != 4:
            malformed += 1
            continue
        
        year_str, hour_str, min_str, sec_str = year_hour_min_sec

        # Validate components
        try:
            day = int(day_str)
            year = int(year_str)
            hour = int(hour_str)
            min_val = int(min_str)
            sec_val = int(sec_str)
        except ValueError:
            malformed += 1
            continue

        if mon_str not in MONTH_MAP:
            malformed += 1
            continue

        # Basic validation of ranges (optional but good for catching malformed)
        if not (1 <= day <= 31):
            malformed += 1
            continue
        if not (0 <= hour <= 23):
            malformed += 1
            continue
        if not (0 <= min_val <= 59):
            malformed += 1
            continue
        if not (0 <= sec_val <= 60):  # leap second
            malformed += 1
            continue

        mon_num = MONTH_MAP[mon_str]
        hour_key = f"{year:04d}-{mon_num}-{day:02d} {hour:02d}"

        # This line is valid
        total_requests += 1
        unique_ips.add(ip)
        status_counts[status] += 1
        bytes_total += bytes_val

        if 400 <= status <= 599:
            error_count += 1

        # Extract path without query string
        if '?' in path:
            clean_path = path.split('?', 1)[0]
        else:
            clean_path = path
        path_counter[clean_path] += 1

        requests_per_hour[hour_key] += 1

    # Compute error_rate
    if total_requests > 0:
        error_rate = round(error_count / total_requests, 4)
    else:
        error_rate = 0.0

    # Compute top_paths: 3 most requested, sorted by count desc, then path asc
    # Get all paths with counts
    path_items = list(path_counter.items())
    # Sort by count descending, then path ascending
    path_items.sort(key=lambda x: (-x[1], x[0]))
    top_paths = path_items[:3]

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
