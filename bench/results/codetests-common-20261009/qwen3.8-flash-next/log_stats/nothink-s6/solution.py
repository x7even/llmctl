import re
from collections import Counter
from datetime import datetime
from typing import Iterable


def analyze_log(lines: Iterable[str]) -> dict:
    """Summarise a web server access log in Common Log Format."""
    
    # Pattern to match Common Log Format lines
    # ip ident user [timestamp] "METHOD path PROTOCOL" status bytes
    pattern = re.compile(
        r'^(\S+)\s+'          # IP
        r'(\S+)\s+'           # ident
        r'(\S+)\s+'           # user
        r'\[([^\]]+)\]\s+'    # timestamp
        r'"(\S+)\s+(\S+)\s+(\S+)"\s+'  # "METHOD path PROTOCOL"
        r'(\d+)\s+'           # status
        r'(\S+)$'             # bytes
    )
    
    total_requests = 0
    malformed = 0
    unique_ips = set()
    status_counts = Counter()
    bytes_total = 0
    path_counts = Counter()
    requests_per_hour = Counter()
    
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
        # user = match.group(3)   # not used
        timestamp_str = match.group(4)
        # method = match.group(5)
        path = match.group(6)
        # protocol = match.group(7)
        status_str = match.group(8)
        bytes_str = match.group(9)
        
        # Validate status is numeric
        if not status_str.isdigit():
            malformed += 1
            continue
        
        status = int(status_str)
        
        # Parse bytes: '-' means 0
        if bytes_str == '-':
            bytes_sent = 0
        else:
            if not bytes_str.isdigit():
                malformed += 1
                continue
            bytes_sent = int(bytes_str)
        
        # Parse timestamp: format like "10/Oct/2026:13:55:36 +0000"
        # We need to extract the hour part: "10/Oct/2026:13" -> "2026-10-10 13"
        try:
            # Extract the date and time part before the timezone
            # Format: DD/Mon/YYYY:HH:MM:SS +ZZZZ
            ts_match = re.match(r'(\d{2})/(\w{3})/(\d{4}):(\d{2}):\d{2}:\d{2}\s+[+\-]\d{4}', timestamp_str)
            if not ts_match:
                malformed += 1
                continue
            
            day = ts_match.group(1)
            month_abbr = ts_match.group(2)
            year = ts_match.group(3)
            hour = ts_match.group(4)
            
            # Map month abbreviation to number
            month_map = {
                'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
                'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
                'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
            }
            
            if month_abbr not in month_map:
                malformed += 1
                continue
            
            month_num = month_map[month_abbr]
            hour_key = f"{year}-{month_num}-{day} {hour}"
            
        except Exception:
            malformed += 1
            continue
        
        # Remove query string from path
        if '?' in path:
            path = path.split('?')[0]
        
        # Valid line
        total_requests += 1
        unique_ips.add(ip)
        status_counts[status] += 1
        bytes_total += bytes_sent
        path_counts[path] += 1
        requests_per_hour[hour_key] += 1
    
    # Calculate error rate
    if total_requests == 0:
        error_rate = 0.0
    else:
        error_count = sum(count for status, count in status_counts.items() if 400 <= status <= 599)
        error_rate = round(error_count / total_requests, 4)
    
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
        "requests_per_hour": dict(requests_per_hour),
    }
