import re
from collections import Counter
from typing import Iterable


def analyze_log(lines: Iterable[str]) -> dict:
    """
    Summarise a web server access log in Common Log Format.
    
    Args:
        lines: An iterable of log lines.
        
    Returns:
        A dictionary with log analysis results.
    """
    # Regex to match Common Log Format
    # ip ident user [timestamp] "METHOD path PROTOCOL" status bytes
    log_pattern = re.compile(
        r'^(\S+) (\S+) (\S+) \[([^\]]+)\] "(\S+) (\S+) (\S+)" (\d{3}) (\S+)$'
    )
    
    # Month abbreviation to number mapping
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
        
        ip, ident, user, timestamp, method, path, protocol, status_str, bytes_str = match.groups()
        
        # Validate status is numeric (regex already ensures 3 digits, but double-check)
        try:
            status = int(status_str)
        except ValueError:
            malformed += 1
            continue
        
        # Validate bytes
        if bytes_str == '-':
            bytes_val = 0
        else:
            try:
                bytes_val = int(bytes_str)
            except ValueError:
                malformed += 1
                continue
        
        # Parse timestamp to extract hour info
        # Format: 10/Oct/2026:13:55:36 +0000
        # We need to extract day, month, year, hour
        ts_match = re.match(r'(\d+)/(\w+)/(\d+):(\d+):\d+:\d+\s+[+-]\d+', timestamp)
        if not ts_match:
            malformed += 1
            continue
        
        day, month_abbr, year, hour = ts_match.groups()
        
        if month_abbr not in month_map:
            malformed += 1
            continue
        
        month = month_map[month_abbr]
        hour_key = f"{year}-{month}-{day} {hour}"
        
        # Strip query string from path
        if '?' in path:
            path = path.split('?', 1)[0]
        
        # All valid, update counters
        total_requests += 1
        unique_ips.add(ip)
        status_counts[status] += 1
        bytes_total += bytes_val
        path_counts[path] += 1
        requests_per_hour[hour_key] += 1
    
    # Calculate error rate
    error_count = sum(count for status, count in status_counts.items() if 400 <= status <= 599)
    if total_requests == 0:
        error_rate = 0.0
    else:
        error_rate = round(error_count / total_requests, 4)
    
    # Top 3 paths sorted by count descending, then path ascending
    top_paths = sorted(path_counts.items(), key=lambda x: (-x[1], x[0]))[:3]
    
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
