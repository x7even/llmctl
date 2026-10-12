import re
from collections import Counter
from typing import Iterable

# Common Log Format regex
# ip ident user [timestamp] "METHOD path PROTOCOL" status bytes
LOG_PATTERN = re.compile(
    r'^(\S+)\s+(\S+)\s+(\S+)\s+\[([^\]]+)\]\s+"(\S+)\s+(\S+)\s+(\S+)"\s+(\d+)\s+(\S+)$'
)

MONTH_MAP = {
    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
}


def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0
    unique_ips = set()
    status_counts = Counter()
    bytes_total = 0
    error_count = 0
    path_counter = Counter()
    hour_counter = Counter()

    for line in lines:
        line = line.rstrip('\n\r')
        match = LOG_PATTERN.match(line)
        if not match:
            malformed += 1
            continue

        ip = match.group(1)
        # ident = match.group(2)
        # user = match.group(3)
        timestamp_str = match.group(4)
        # method = match.group(5)
        path_raw = match.group(6)
        # protocol = match.group(7)
        status_str = match.group(8)
        bytes_str = match.group(9)

        # Validate status is numeric (already ensured by \d+ in regex)
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

        # Valid line
        total_requests += 1
        unique_ips.add(ip)
        status_counts[status] += 1
        bytes_total += bytes_val
        if 400 <= status <= 599:
            error_count += 1

        # Extract path without query string
        if '?' in path_raw:
            path = path_raw.split('?', 1)[0]
        else:
            path = path_raw
        path_counter[path] += 1

        # Parse timestamp for hour
        # Format: 10/Oct/2026:13:55:36 +0000
        # We need YYYY-MM-DD HH
        try:
            # Split off timezone
            ts_without_tz = timestamp_str.split(' ')[0]
            # ts_without_tz is like 10/Oct/2026:13:55:36
            # Split date and time
            date_time = ts_without_tz.split(':')
            # date part is first element: 10/Oct/2026
            date_part = date_time[0]
            # time parts: hour is date_time[1]
            hour = date_time[1]

            # Parse date part: DD/Mon/YYYY
            date_components = date_part.split('/')
            if len(date_components) != 3:
                malformed += 1
                total_requests -= 1
                unique_ips.discard(ip)
                status_counts[status] -= 1
                if status_counts[status] == 0:
                    del status_counts[status]
                bytes_total -= bytes_val
                if 400 <= status <= 599:
                    error_count -= 1
                path_counter[path] -= 1
                if path_counter[path] == 0:
                    del path_counter[path]
                continue

            day, mon_abbr, year = date_components
            if mon_abbr not in MONTH_MAP:
                malformed += 1
                total_requests -= 1
                unique_ips.discard(ip)
                status_counts[status] -= 1
                if status_counts[status] == 0:
                    del status_counts[status]
                bytes_total -= bytes_val
                if 400 <= status <= 599:
                    error_count -= 1
                path_counter[path] -= 1
                if path_counter[path] == 0:
                    del path_counter[path]
                continue

            month = MONTH_MAP[mon_abbr]
            hour_key = f"{year}-{month}-{day} {hour}"
            hour_counter[hour_key] += 1

        except Exception:
            # Timestamp parsing failed, treat as malformed
            malformed += 1
            total_requests -= 1
            unique_ips.discard(ip)
            status_counts[status] -= 1
            if status_counts[status] == 0:
                del status_counts[status]
            bytes_total -= bytes_val
            if 400 <= status <= 599:
                error_count -= 1
            path_counter[path] -= 1
            if path_counter[path] == 0:
                del path_counter[path]
            continue

    # Compute error_rate
    if total_requests == 0:
        error_rate = 0.0
    else:
        error_rate = round(error_count / total_requests, 4)

    # Top paths: top 3 by count descending, then path ascending
    top_paths = sorted(path_counter.items(), key=lambda x: (-x[1], x[0]))[:3]

    # Convert status_counts to regular dict
    status_counts_dict = dict(status_counts)

    return {
        "total_requests": total_requests,
        "malformed": malformed,
        "unique_ips": len(unique_ips),
        "status_counts": status_counts_dict,
        "bytes_total": bytes_total,
        "error_rate": error_rate,
        "top_paths": top_paths,
        "requests_per_hour": dict(hour_counter),
    }
