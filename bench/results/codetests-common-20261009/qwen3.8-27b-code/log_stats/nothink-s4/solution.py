"""Module for analysing web server access logs in Common Log Format."""

from collections import Counter
from typing import Dict, Iterable, List, Tuple
import re
from datetime import datetime

# Regex for a Common Log Format line:
# ip ident user [timestamp] "METHOD path PROTOCOL" status bytes
_CLF_PATTERN = re.compile(
    r'^(\S+)\s+'          # ip
    r'(\S+)\s+'           # ident
    r'(\S+)\s+'           # user
    r'\[([^\]]+)\]\s+'    # timestamp
    r'"(\S+)\s+'          # method
    r'(\S+)\s+'           # path
    r'(\S+)"\s+'          # protocol
    r'(\d{3})\s+'         # status (3 digits)
    r'(\S+)\s*$'          # bytes
)

_MONTH_MAP = {
    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4,
    'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8,
    'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12,
}


def _parse_timestamp(ts: str) -> str:
    """
    Parse a timestamp like '10/Oct/2026:13:55:36 +0000'
    and return 'YYYY-MM-DD HH' ignoring the timezone offset.
    Returns None if parsing fails.
    """
    # Expected format: DD/Mon/YYYY:HH:MM:SS +ZZZZ
    parts = ts.split(' ')
    if len(parts) < 1:
        return None
    date_part = parts[0]
    # date_part should be like 10/Oct/2026:13:55:36
    try:
        # Split by '/' and ':'
        # Format: day/month/year:hour:minute:second
        slash_parts = date_part.split('/')
        if len(slash_parts) != 3:
            return None
        day_str = slash_parts[0]
        month_str = slash_parts[1]
        year_time_str = slash_parts[2]
        
        if month_str not in _MONTH_MAP:
            return None
        
        month = _MONTH_MAP[month_str]
        
        colon_parts = year_time_str.split(':')
        if len(colon_parts) != 4:
            return None
        
        year_str = colon_parts[0]
        hour_str = colon_parts[1]
        
        day = int(day_str)
        year = int(year_str)
        hour = int(hour_str)
        
        if not (1 <= day <= 31):
            return None
        if not (1 <= month <= 12):
            return None
        if not (0 <= hour <= 23):
            return None
        
        return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}"
    except (ValueError, IndexError):
        return None


def analyze_log(lines: Iterable[str]) -> dict:
    """
    Summarise a web server access log in Common Log Format.
    
    Args:
        lines: An iterable of log lines.
        
    Returns:
        A dict with keys:
        - "total_requests": number of valid lines.
        - "malformed": number of malformed lines.
        - "unique_ips": number of distinct client IPs among valid lines.
        - "status_counts": dict mapping each integer status code to count.
        - "bytes_total": sum of the bytes fields of valid lines.
        - "error_rate": fraction of valid lines with status 400-599, rounded to 4 decimals.
        - "top_paths": list of 3 most requested (path, count) tuples.
        - "requests_per_hour": dict mapping "YYYY-MM-DD HH" to count.
    """
    total_requests = 0
    malformed = 0
    ips = set()
    status_counts: Dict[int, int] = {}
    bytes_total = 0
    error_count = 0
    path_counter: Counter = Counter()
    hour_counter: Dict[str, int] = {}

    for line in lines:
        line = line.strip()
        if not line:
            malformed += 1
            continue

        match = _CLF_PATTERN.match(line)
        if not match:
            malformed += 1
            continue

        ip, ident, user, timestamp, method, path, protocol, status_str, bytes_str = match.groups()

        # Validate status is numeric (regex already ensures 3 digits, but let's be safe)
        try:
            status = int(status_str)
        except ValueError:
            malformed += 1
            continue

        # Validate bytes field
        if bytes_str == '-':
            bytes_val = 0
        else:
            try:
                bytes_val = int(bytes_str)
            except ValueError:
                malformed += 1
                continue

        # Validate timestamp
        hour_key = _parse_timestamp(timestamp)
        if hour_key is None:
            malformed += 1
            continue

        # All validations passed
        total_requests += 1
        ips.add(ip)
        
        status_counts[status] = status_counts.get(status, 0) + 1
        bytes_total += bytes_val
        
        if 400 <= status <= 599:
            error_count += 1
        
        # Strip query string from path
        if '?' in path:
            clean_path = path.split('?', 1)[0]
        else:
            clean_path = path
        
        path_counter[clean_path] += 1
        hour_counter[hour_key] = hour_counter.get(hour_key, 0) + 1

    # Calculate error rate
    if total_requests > 0:
        error_rate = round(error_count / total_requests, 4)
    else:
        error_rate = 0.0

    # Top 3 paths: sort by count descending, then path ascending
    sorted_paths = sorted(path_counter.items(), key=lambda x: (-x[1], x[0]))
    top_paths: List[Tuple[str, int]] = sorted_paths[:3]

    return {
        "total_requests": total_requests,
        "malformed": malformed,
        "unique_ips": len(ips),
        "status_counts": status_counts,
        "bytes_total": bytes_total,
        "error_rate": error_rate,
        "top_paths": top_paths,
        "requests_per_hour": hour_counter,
    }
