import re
from collections import defaultdict
from typing import Iterable


def analyze_log(lines: Iterable[str]) -> dict:
    """
    Summarise a web server access log in Common Log Format.
    
    Each valid line: ip ident user [timestamp] "METHOD path PROTOCOL" status bytes
    Bytes field is '-' when no body was sent (count as 0).
    Malformed lines are skipped and counted.
    """
    # Pattern for Common Log Format
    # ip ident user [timestamp] "METHOD path PROTOCOL" status bytes
    pattern = re.compile(
        r'^(\S+)\s+(\S+)\s+(\S+)\s+\[([^\]]+)\]\s+"(\S+)\s+(\S+)\s+(\S+)"\s+(\d+)\s+(\S+)$'
    )
    
    total_requests = 0
    malformed = 0
    unique_ips = set()
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
        line = line.strip()
        if not line:
            malformed += 1
            continue
        
        match = pattern.match(line)
        if not match:
            malformed += 1
            continue
        
        ip = match.group(1)
        # ident = match.group(2)  # not used
        # user = match.group(3)  # not used
        timestamp_str = match.group(4)
        # method = match.group(5)  # not used
        path = match.group(6)
        # protocol = match.group(7)  # not used
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
        
        # Validate timestamp format: DD/Mon/YYYY:HH:MM:SS +ZZZZ or -ZZZZ
        # We need to extract date and hour for requests_per_hour
        # Timestamp format: 10/Oct/2026:13:55:36 +0000
        ts_match = re.match(r'^(\d{2})/([A-Za-z]{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2})\s+[+-]\d{4}$', timestamp_str)
        if not ts_match:
            malformed += 1
            continue
        
        day = ts_match.group(1)
        month_abbr = ts_match.group(2)
        year = ts_match.group(3)
        hour = ts_match.group(4)
        
        if month_abbr not in month_map:
            malformed += 1
            continue
        
        month_num = month_map[month_abbr]
        date_hour_key = f"{year}-{month_num}-{day} {hour}"
        
        # Extract path without query string
        if '?' in path:
            path = path.split('?')[0]
        
        # All valid
        total_requests += 1
        unique_ips.add(ip)
        status_counts[status] += 1
        bytes_total += bytes_val
        path_counts[path] += 1
        requests_per_hour[date_hour_key] += 1
    
    # Calculate error rate
    error_count = sum(count for status, count in status_counts.items() if 400 <= status <= 599)
    if total_requests > 0:
        error_rate = round(error_count / total_requests, 4)
    else:
        error_rate = 0.0
    
    # Top 3 paths sorted by count descending, then path ascending
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
        "requests_per_hour": dict(requests_per_hour)
    }
