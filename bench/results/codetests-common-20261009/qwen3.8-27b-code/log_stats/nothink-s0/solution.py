import re
from collections import Counter
from typing import Iterable, Dict, List, Tuple
from datetime import datetime


def analyze_log(lines: Iterable[str]) -> dict:
    """Summarise a web server access log in Common Log Format."""
    
    # Regex for Common Log Format:
    # ip ident user [timestamp] "METHOD path PROTOCOL" status bytes
    # ip: \S+
    # ident: \S+
    # user: \S+
    # [timestamp]: \[([^\]]+)\]
    # "METHOD path PROTOCOL": "(\S+) (\S+) (\S+)"
    # status: (\d+)
    # bytes: (\d+|-)
    
    log_pattern = re.compile(
        r'^(\S+) (\S+) (\S+) \[([^\]]+)\] "(\S+) (\S+) (\S+)" (\d+) (\d+|-)\s*$'
    )
    
    month_map = {
        'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4,
        'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8,
        'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
    }
    
    total_requests = 0
    malformed = 0
    unique_ips = set()
    status_counts: Dict[int, int] = {}
    bytes_total = 0
    path_counts: Counter = Counter()
    hour_counts: Dict[str, int] = {}
    error_count = 0
    
    for line in lines:
        line = line.strip()
        if not line:
            malformed += 1
            continue
        
        match = log_pattern.match(line)
        if not match:
            malformed += 1
            continue
        
        ip, ident, user, timestamp, method, path_with_query, protocol, status_str, bytes_str = match.groups()
        
        # Validate timestamp format
        try:
            # timestamp looks like: 10/Oct/2026:13:55:36 +0000
            # We need to extract date and time for the hour key
            # Format: DD/Mon/YYYY:HH:MM:SS +ZZZZ
            ts_parts = timestamp.split(' ')
            if len(ts_parts) != 2:
                malformed += 1
                continue
            
            date_time_part = ts_parts[0]
            # date_time_part: 10/Oct/2026:13:55:36
            # Split by '/' and ':'
            # Format: DD/Mon/YYYY:HH:MM:SS
            dt_parts = date_time_part.split(':')
            if len(dt_parts) != 4:
                malformed += 1
                continue
            
            date_part = dt_parts[0]  # DD/Mon/YYYY
            time_part = dt_parts[1]  # HH
            minute_part = dt_parts[2]  # MM
            second_part = dt_parts[3]  # SS
            
            # Validate time parts are numeric
            if not (time_part.isdigit() and minute_part.isdigit() and second_part.isdigit()):
                malformed += 1
                continue
            
            # Parse date part: DD/Mon/YYYY
            date_components = date_part.split('/')
            if len(date_components) != 3:
                malformed += 1
                continue
            
            day_str, mon_str, year_str = date_components
            if not (day_str.isdigit() and year_str.isdigit()):
                malformed += 1
                continue
            
            if mon_str not in month_map:
                malformed += 1
                continue
            
            day = int(day_str)
            month = month_map[mon_str]
            year = int(year_str)
            hour = int(time_part)
            
            # Validate ranges
            if not (1 <= day <= 31 and 1 <= month <= 12 and 0 <= hour <= 23):
                malformed += 1
                continue
            
        except (ValueError, IndexError):
            malformed += 1
            continue
        
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
        
        # All valid, now accumulate
        total_requests += 1
        unique_ips.add(ip)
        status_counts[status] = status_counts.get(status, 0) + 1
        bytes_total += bytes_val
        
        if 400 <= status <= 599:
            error_count += 1
        
        # Extract path without query string
        if '?' in path_with_query:
            path = path_with_query.split('?', 1)[0]
        else:
            path = path_with_query
        
        path_counts[path] += 1
        
        # Build hour key: YYYY-MM-DD HH
        hour_key = f"{year:04d}-{month:02d}-{day:02d} {hour:02d}"
        hour_counts[hour_key] = hour_counts.get(hour_key, 0) + 1
    
    # Calculate error rate
    if total_requests > 0:
        error_rate = round(error_count / total_requests, 4)
    else:
        error_rate = 0.0
    
    # Get top 3 paths sorted by count descending, then path ascending
    sorted_paths = sorted(path_counts.items(), key=lambda x: (-x[1], x[0]))
    top_paths = [(p, c) for p, c in sorted_paths[:3]]
    
    return {
        "total_requests": total_requests,
        "malformed": malformed,
        "unique_ips": len(unique_ips),
        "status_counts": status_counts,
        "bytes_total": bytes_total,
        "error_rate": error_rate,
        "top_paths": top_paths,
        "requests_per_hour": hour_counts
    }
