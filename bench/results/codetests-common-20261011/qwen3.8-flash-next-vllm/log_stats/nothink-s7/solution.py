import re
from collections import Counter
from typing import Iterable, Dict, List, Tuple

# Common Log Format regex
# ip ident user [timestamp] "METHOD path PROTOCOL" status bytes
_LOG_PATTERN = re.compile(
    r'^(\S+)\s+'           # ip
    r'(\S+)\s+'            # ident
    r'(\S+)\s+'            # user
    r'\[([^\]]+)\]\s+'     # timestamp
    r'"([^"]*)"\s+'        # request line
    r'(\d+)\s+'            # status
    r'(\S+)$'              # bytes
)

_MONTH_MAP = {
    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
}


def analyze_log(lines: Iterable[str]) -> dict:
    """
    Summarise a web server access log in Common Log Format.
    
    Args:
        lines: Iterable of log lines.
        
    Returns:
        A dict with summary statistics.
    """
    total_requests = 0
    malformed = 0
    ip_set = set()
    status_counter = Counter()
    bytes_total = 0
    path_counter = Counter()
    hour_counter = Counter()

    for line in lines:
        # Strip trailing newline/whitespace for matching but keep original structure
        line_stripped = line.rstrip('\n\r')
        
        match = _LOG_PATTERN.match(line_stripped)
        if not match:
            malformed += 1
            continue
        
        ip, ident, user, timestamp, request_line, status_str, bytes_str = match.groups()
        
        # Validate status is numeric (regex already ensures digits, but double-check)
        try:
            status = int(status_str)
        except ValueError:
            malformed += 1
            continue
        
        # Parse bytes
        if bytes_str == '-':
            bytes_sent = 0
        else:
            try:
                bytes_sent = int(bytes_str)
            except ValueError:
                malformed += 1
                continue
        
        # Parse timestamp: e.g., 10/Oct/2026:13:55:36 +0000
        # Format: DD/Mon/YYYY:HH:MM:SS +ZZZZ
        ts_match = re.match(r'^(\d{2})/([A-Za-z]{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2})', timestamp)
        if not ts_match:
            malformed += 1
            continue
        
        day, month_abbr, year, hour, minute, second = ts_match.groups()
        if month_abbr not in _MONTH_MAP:
            malformed += 1
            continue
        
        month_num = _MONTH_MAP[month_abbr]
        hour_key = f"{year}-{month_num}-{day} {hour}"
        
        # Parse request line: "METHOD path PROTOCOL"
        req_match = re.match(r'^(\S+)\s+(\S+)\s+(\S+)$', request_line)
        if not req_match:
            malformed += 1
            continue
        
        method, path_with_query, protocol = req_match.groups()
        
        # Extract path without query string
        if '?' in path_with_query:
            path = path_with_query.split('?', 1)[0]
        else:
            path = path_with_query
        
        # All fields parsed successfully
        total_requests += 1
        ip_set.add(ip)
        status_counter[status] += 1
        bytes_total += bytes_sent
        path_counter[path] += 1
        hour_counter[hour_key] += 1

    # Compute error_rate
    if total_requests > 0:
        error_count = sum(count for status, count in status_counter.items() if 400 <= status <= 599)
        error_rate = round(error_count / total_requests, 4)
    else:
        error_rate = 0.0

    # Compute top_paths: 3 most requested, sorted by count desc, then path asc
    # Counter.most_common sorts by count desc, but for ties we need path asc
    # So we sort manually
    sorted_paths = sorted(path_counter.items(), key=lambda x: (-x[1], x[0]))
    top_paths = sorted_paths[:3]

    return {
        "total_requests": total_requests,
        "malformed": malformed,
        "unique_ips": len(ip_set),
        "status_counts": dict(status_counter),
        "bytes_total": bytes_total,
        "error_rate": error_rate,
        "top_paths": top_paths,
        "requests_per_hour": dict(hour_counter),
    }
