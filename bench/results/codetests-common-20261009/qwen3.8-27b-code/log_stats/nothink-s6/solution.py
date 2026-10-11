import re
from collections import defaultdict
from typing import Iterable, Dict, List, Tuple

# Common Log Format regex
# ip ident user [timestamp] "METHOD path PROTOCOL" status bytes
_LOG_PATTERN = re.compile(
    r'^(\S+)\s+'          # ip
    r'(\S+)\s+'           # ident
    r'(\S+)\s+'           # user
    r'\[([^\]]+)\]\s+'    # timestamp
    r'"([^"]*)"\s+'       # request line
    r'(\d{3})\s+'         # status
    r'(\d+|-)\s*$'        # bytes
)

# Timestamp format: 10/Oct/2026:13:55:36 +0000
_TS_PATTERN = re.compile(
    r'^(\d{2})/([A-Za-z]{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2})\s+[+-]\d{4}$'
)

_MONTH_MAP = {
    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
}


def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0
    unique_ips = set()
    status_counts: Dict[int, int] = defaultdict(int)
    bytes_total = 0
    error_count = 0
    path_counts: Dict[str, int] = defaultdict(int)
    requests_per_hour: Dict[str, int] = defaultdict(int)

    for line in lines:
        line = line.rstrip('\n').rstrip('\r')
        if not line:
            malformed += 1
            continue

        m = _LOG_PATTERN.match(line)
        if not m:
            malformed += 1
            continue

        ip, ident, user, timestamp, request_line, status_str, bytes_str = m.groups()

        # Validate timestamp
        ts_match = _TS_PATTERN.match(timestamp)
        if not ts_match:
            malformed += 1
            continue

        # Validate request line: should have METHOD path PROTOCOL
        parts = request_line.split()
        if len(parts) < 2:
            malformed += 1
            continue

        # status is already validated as 3 digits by regex
        status = int(status_str)

        # bytes
        if bytes_str == '-':
            byte_val = 0
        else:
            byte_val = int(bytes_str)

        # Count valid
        total_requests += 1
        unique_ips.add(ip)
        status_counts[status] += 1
        bytes_total += byte_val

        if 400 <= status <= 599:
            error_count += 1

        # Extract path (without query string)
        # parts[1] is the path
        raw_path = parts[1]
        if '?' in raw_path:
            path = raw_path.split('?', 1)[0]
        else:
            path = raw_path
        path_counts[path] += 1

        # Extract hour from timestamp
        day, mon, year, hour, minute, second = ts_match.groups()
        mon_str = _MONTH_MAP.get(mon)
        if mon_str is None:
            malformed += 1
            total_requests -= 1
            # We already incremented total_requests, so we need to revert
            # But this shouldn't happen since _TS_PATTERN matches [A-Za-z]{3}
            # and we check against the map. Let's handle it properly.
            # Actually, let's restructure: validate month before counting.
            # For now, continue to next iteration logic
            # We need to undo the increments above
            unique_ips.discard(ip)
            status_counts[status] -= 1
            if status_counts[status] == 0:
                del status_counts[status]
            bytes_total -= byte_val
            if 400 <= status <= 599:
                error_count -= 1
            path_counts[path] -= 1
            if path_counts[path] == 0:
                del path_counts[path]
            malformed += 1
            continue

        hour_key = f"{year}-{mon_str}-{day} {hour}"
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
        "unique_ips": len(unique_ips),
        "status_counts": dict(status_counts),
        "bytes_total": bytes_total,
        "error_rate": error_rate,
        "top_paths": top_paths,
        "requests_per_hour": dict(requests_per_hour),
    }
