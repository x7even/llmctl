import re
from collections import Counter
from typing import Iterable, Dict, List, Tuple

# Common Log Format regex
# ip ident user [timestamp] "METHOD path PROTOCOL" status bytes
LOG_PATTERN = re.compile(
    r'^(\S+)\s+'           # IP
    r'(\S+)\s+'            # ident
    r'(\S+)\s+'            # user
    r'\[([^\]]+)\]\s+'     # timestamp
    r'"(\S+)\s+'           # method
    r'(\S+)\s+'            # path (including query string)
    r'(\S+)"\s+'           # protocol
    r'(\d+)\s+'            # status
    r'(\d+|-)$'            # bytes
)

MONTH_MAP = {
    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
}

def _parse_timestamp_to_hour(timestamp: str) -> str:
    """
    Parse timestamp like '10/Oct/2026:13:55:36 +0000' to 'YYYY-MM-DD HH'
    ignoring timezone offset.
    """
    # Format: DD/Mon/YYYY:HH:MM:SS +ZZZZ
    # Extract day, month, year, hour
    try:
        # Split on space to remove timezone part
        date_time_part = timestamp.split()[0]
        # date_time_part is like '10/Oct/2026:13:55:36'
        # Split by '/' and ':'
        parts = date_time_part.split(':')
        date_part = parts[0]  # '10/Oct/2026'
        hour_part = parts[1]  # '13'
        
        date_components = date_part.split('/')
        day = date_components[0]
        month_abbr = date_components[1]
        year = date_components[2]
        
        month_num = MONTH_MAP.get(month_abbr)
        if month_num is None:
            return None
        
        # Ensure day is zero-padded
        day = day.zfill(2)
        
        return f"{year}-{month_num}-{day} {hour_part}"
    except (IndexError, ValueError):
        return None

def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0
    ips = set()
    status_counts = Counter()
    bytes_total = 0
    path_counter = Counter()
    requests_per_hour = Counter()
    
    for line in lines:
        line = line.rstrip('\n').rstrip('\r')
        match = LOG_PATTERN.match(line)
        if not match:
            malformed += 1
            continue
        
        ip = match.group(1)
        # ident = match.group(2)
        # user = match.group(3)
        timestamp = match.group(4)
        # method = match.group(5)
        path_with_query = match.group(6)
        # protocol = match.group(7)
        status_str = match.group(8)
        bytes_str = match.group(9)
        
        # Validate status is numeric
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
        
        # Extract path without query string
        if '?' in path_with_query:
            path = path_with_query.split('?')[0]
        else:
            path = path_with_query
        
        # Parse timestamp for hour
        hour_key = _parse_timestamp_to_hour(timestamp)
        if hour_key is None:
            malformed += 1
            continue
        
        # Valid line
        total_requests += 1
        ips.add(ip)
        status_counts[status] += 1
        bytes_total += bytes_val
        path_counter[path] += 1
        requests_per_hour[hour_key] += 1
    
    # Calculate error_rate
    if total_requests == 0:
        error_rate = 0.0
    else:
        error_count = sum(count for status, count in status_counts.items() if 400 <= status <= 599)
        error_rate = round(error_count / total_requests, 4)
    
    # Top paths: 3 most requested, sorted by count descending then path ascending
    sorted_paths = sorted(path_counter.items(), key=lambda x: (-x[1], x[0]))
    top_paths = sorted_paths[:3]
    
    return {
        "total_requests": total_requests,
        "malformed": malformed,
        "unique_ips": len(ips),
        "status_counts": dict(status_counts),
        "bytes_total": bytes_total,
        "error_rate": error_rate,
        "top_paths": top_paths,
        "requests_per_hour": dict(requests_per_hour)
    }
