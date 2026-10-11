import re
from collections import defaultdict
from datetime import datetime
from typing import Iterable, Dict, List, Tuple, Optional

# Pattern for Common Log Format
# ip ident user [timestamp] "METHOD path PROTOCOL" status bytes
CLF_PATTERN = re.compile(
    r'^(\S+)\s+'          # ip
    r'(\S+)\s+'           # ident
    r'(\S+)\s+'           # user
    r'\[([^\]]+)\]\s+'    # [timestamp]
    r'"(\S+)\s+(\S+)\s+(\S+)"\s+'  # "METHOD path PROTOCOL"
    r'(\d{3})\s+'         # status (must be 3 digits)
    r'(\d+|-)$'           # bytes (digits or -)
)

MONTH_MAP = {
    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4,
    'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8,
    'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
}


def parse_timestamp(ts_str: str) -> Optional[datetime]:
    """Parse timestamp like '10/Oct/2026:13:55:36 +0000' ignoring timezone."""
    # Format: DD/Mon/YYYY:HH:MM:SS +ZZZZ
    # We need to extract date and time parts
    try:
        # Split off the timezone part
        # The format is: 10/Oct/2026:13:55:36 +0000
        # Find the last space before the timezone
        # Actually, let's use strptime with a custom approach
        
        # Remove timezone: everything after the last space that looks like +ZZZZ or -ZZZZ
        # But simpler: use regex to extract date/time
        match = re.match(r'(\d{2})/(\w{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2})', ts_str)
        if not match:
            return None
        day, month_str, year, hour, minute, second = match.groups()
        month = MONTH_MAP.get(month_str)
        if month is None:
            return None
        return datetime(int(year), month, int(day), int(hour), int(minute), int(second))
    except (ValueError, TypeError):
        return None


def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0
    unique_ips = set()
    status_counts = defaultdict(int)
    bytes_total = 0
    path_counts = defaultdict(int)
    requests_per_hour = defaultdict(int)
    
    for line in lines:
        # Strip trailing newline/carriage return but not leading/trailing whitespace that might be part of the format
        # Actually, we should strip the line of leading/trailing whitespace for matching
        stripped = line.rstrip('\r\n')
        
        # Check if the line is empty after stripping
        if not stripped:
            malformed += 1
            continue
        
        match = CLF_PATTERN.match(stripped)
        if not match:
            malformed += 1
            continue
        
        ip, ident, user, timestamp_str, method, path, protocol, status_str, bytes_str = match.groups()
        
        # Parse status
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
        
        # Parse timestamp
        dt = parse_timestamp(timestamp_str)
        if dt is None:
            malformed += 1
            continue
        
        # Extract path without query string
        if '?' in path:
            clean_path = path.split('?')[0]
        else:
            clean_path = path
        
        # Valid line
        total_requests += 1
        unique_ips.add(ip)
        status_counts[status] += 1
        bytes_total += bytes_val
        path_counts[clean_path] += 1
        
        # Requests per hour
        hour_key = dt.strftime('%Y-%m-%d %H')
        requests_per_hour[hour_key] += 1
    
    # Calculate error rate
    if total_requests == 0:
        error_rate = 0.0
    else:
        error_count = sum(count for status, count in status_counts.items() if 400 <= status <= 599)
        error_rate = round(error_count / total_requests, 4)
    
    # Top paths: 3 most requested, sorted by count desc then path asc
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
