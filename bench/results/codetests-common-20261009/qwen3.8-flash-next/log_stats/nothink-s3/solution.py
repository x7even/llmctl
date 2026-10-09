import re
from collections import defaultdict
from typing import Iterable, Dict, List, Tuple

def analyze_log(lines: Iterable[str]) -> dict:
    """
    Summarise a web server access log in Common Log Format.
    
    Format: ip ident user [timestamp] "METHOD path PROTOCOL" status bytes
    """
    # Pattern to match Common Log Format
    # ip ident user [timestamp] "METHOD path PROTOCOL" status bytes
    log_pattern = re.compile(
        r'^(\S+)\s+'          # IP
        r'(\S+)\s+'           # ident
        r'(\S+)\s+'           # user
        r'\[([^\]]+)\]\s+'    # timestamp
        r'"(\S+)\s+'          # METHOD
        r'(\S+)\s+'           # path (with query string potentially)
        r'(\S+)"\s+'          # PROTOCOL
        r'(\d+)\s+'           # status (must be numeric)
        r'(\S+)$'             # bytes (can be '-' or number)
    )
    
    total_requests = 0
    malformed = 0
    ips = set()
    status_counts = defaultdict(int)
    bytes_total = 0
    path_counts = defaultdict(int)
    requests_per_hour = defaultdict(int)
    
    month_map = {
        'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
        'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
        'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
    }
    
    for line in lines:
        # Strip trailing newline but don't strip leading/trailing spaces for matching
        line = line.rstrip('\n\r')
        
        # Try to match the pattern
        match = log_pattern.match(line)
        if not match:
            malformed += 1
            continue
        
        ip = match.group(1)
        ident = match.group(2)
        user = match.group(3)
        timestamp = match.group(4)
        method = match.group(5)
        path_with_query = match.group(6)
        protocol = match.group(7)
        status_str = match.group(8)
        bytes_str = match.group(9)
        
        # Validate status is numeric (already ensured by regex \d+, but double-check)
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
        ips.add(ip)
        status_counts[status] += 1
        bytes_total += bytes_val
        
        # Extract path without query string
        if '?' in path_with_query:
            path = path_with_query.split('?')[0]
        else:
            path = path_with_query
        path_counts[path] += 1
        
        # Parse timestamp for hour bucket
        # Format: 10/Oct/2026:13:55:36 +0000
        # We need: YYYY-MM-DD HH
        try:
            # Split off timezone
            ts_no_tz = timestamp.split()[0]
            # Format: DD/Mon/YYYY:HH:MM:SS
            day_mon_year_time = ts_no_tz.split(':')
            date_part = day_mon_year_time[0]  # DD/Mon/YYYY
            hour_part = day_mon_year_time[1]   # HH
            
            date_components = date_part.split('/')
            day = date_components[0]
            mon = date_components[1]
            year = date_components[2]
            
            mon_str = month_map.get(mon)
            if mon_str is None:
                malformed += 1
                total_requests -= 1
                ips.discard(ip)
                status_counts[status] -= 1
                bytes_total -= bytes_val
                path_counts[path] -= 1
                if path_counts[path] == 0:
                    del path_counts[path]
                continue
            
            hour_key = f"{year}-{mon_str}-{day} {hour_part}"
            requests_per_hour[hour_key] += 1
        except (IndexError, ValueError):
            malformed += 1
            total_requests -= 1
            ips.discard(ip)
            status_counts[status] -= 1
            bytes_total -= bytes_val
            path_counts[path] -= 1
            if path_counts[path] == 0:
                del path_counts[path]
            continue
    
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
        "unique_ips": len(ips),
        "status_counts": dict(status_counts),
        "bytes_total": bytes_total,
        "error_rate": error_rate,
        "top_paths": top_paths,
        "requests_per_hour": dict(requests_per_hour)
    }
