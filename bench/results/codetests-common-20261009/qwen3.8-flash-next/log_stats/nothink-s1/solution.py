import re
from collections import Counter
from typing import Iterable


def analyze_log(lines: Iterable[str]) -> dict:
    """
    Summarise a web server access log in Common Log Format.
    """
    # Regex for Common Log Format:
    # ip ident user [timestamp] "METHOD path PROTOCOL" status bytes
    # ip: \S+
    # ident: \S+ or -
    # user: \S+ or -
    # timestamp: [date]
    # request: "METHOD path PROTOCOL"
    # status: \d+
    # bytes: \d+ or -
    
    # Pattern: ip ident user [timestamp] "METHOD path PROTOCOL" status bytes
    log_pattern = re.compile(
        r'^(\S+)\s+'           # ip
        r'(\S+)\s+'            # ident
        r'(\S+)\s+'            # user
        r'\[([^\]]+)\]\s+'     # timestamp
        r'"([^"]*)"\s+'        # request line
        r'(\d+)\s+'            # status
        r'(\S+)$'              # bytes (could be - or number)
    )
    
    month_map = {
        'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
        'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
        'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
    }
    
    total_requests = 0
    malformed = 0
    unique_ips = set()
    status_counts = Counter()
    bytes_total = 0
    error_count = 0
    path_counts = Counter()
    requests_per_hour = Counter()
    
    for line in lines:
        line = line.rstrip('\n\r')
        if not line:
            malformed += 1
            continue
        
        match = log_pattern.match(line)
        if not match:
            malformed += 1
            continue
        
        ip = match.group(1)
        timestamp = match.group(4)
        request_line = match.group(5)
        status_str = match.group(6)
        bytes_str = match.group(7)
        
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
        
        # Parse timestamp: format like 10/Oct/2026:13:55:36 +0000
        # We need to extract date and hour for requests_per_hour
        # Format: DD/Mon/YYYY:HH:MM:SS +ZZZZ
        ts_match = re.match(r'^(\d{2})/([A-Za-z]{3})/(\d{4}):(\d{2}):\d{2}:\d{2}', timestamp)
        if not ts_match:
            malformed += 1
            continue
        
        day = ts_match.group(1)
        mon_str = ts_match.group(2)
        year = ts_match.group(3)
        hour = ts_match.group(4)
        
        if mon_str not in month_map:
            malformed += 1
            continue
        
        mon = month_map[mon_str]
        hour_key = f"{year}-{mon}-{day} {hour}"
        
        # Parse request line: "METHOD path PROTOCOL"
        # We need to extract the path (without query string)
        req_match = re.match(r'^(\S+)\s+(\S+)\s+(\S+)$', request_line)
        if not req_match:
            malformed += 1
            continue
        
        method = req_match.group(1)
        path = req_match.group(2)
        protocol = req_match.group(3)
        
        # Remove query string from path
        if '?' in path:
            path = path.split('?')[0]
        
        # All good, this is a valid line
        total_requests += 1
        unique_ips.add(ip)
        status_counts[status] += 1
        bytes_total += bytes_val
        
        if 400 <= status <= 599:
            error_count += 1
        
        path_counts[path] += 1
        requests_per_hour[hour_key] += 1
    
    # Calculate error_rate
    if total_requests > 0:
        error_rate = round(error_count / total_requests, 4)
    else:
        error_rate = 0.0
    
    # Get top 3 paths
    # Sort by count descending, then path ascending
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
