import re
from collections import Counter
from datetime import datetime
from typing import Iterable


def analyze_log(lines: Iterable[str]) -> dict:
    """
    Summarise a web server access log in Common Log Format.
    
    Each line should look like:
    ip ident user [timestamp] "METHOD path PROTOCOL" status bytes
    
    Returns a dict with summary statistics.
    """
    # Pattern to match Common Log Format
    # ip - user [timestamp] "method path protocol" status bytes
    log_pattern = re.compile(
        r'^(\S+)\s+'          # IP
        r'(\S+)\s+'           # ident
        r'(\S+)\s+'           # user
        r'\[([^\]]+)\]\s+'    # timestamp
        r'"(\S+)\s+(\S+)\s+(\S+)"\s+'  # method, path, protocol
        r'(\d+)\s+'           # status
        r'(\S+)$'             # bytes
    )
    
    total_requests = 0
    malformed = 0
    ips = set()
    status_counts = Counter()
    bytes_total = 0
    path_counts = Counter()
    requests_per_hour = Counter()
    
    for line in lines:
        line = line.strip()
        if not line:
            malformed += 1
            continue
        
        match = log_pattern.match(line)
        if not match:
            malformed += 1
            continue
        
        ip, ident, user, timestamp, method, path, protocol, status_str, bytes_str = match.groups()
        
        # Validate status is numeric
        try:
            status = int(status_str)
        except ValueError:
            malformed += 1
            continue
        
        # Parse bytes: '-' means 0
        if bytes_str == '-':
            bytes_sent = 0
        else:
            try:
                bytes_sent = int(bytes_str)
            except ValueError:
                malformed += 1
                continue
        
        # This is a valid line
        total_requests += 1
        ips.add(ip)
        status_counts[status] += 1
        bytes_total += bytes_sent
        
        # Extract path without query string
        if '?' in path:
            clean_path = path.split('?')[0]
        else:
            clean_path = path
        path_counts[clean_path] += 1
        
        # Parse timestamp for requests_per_hour
        # Timestamp format: 10/Oct/2026:13:55:36 +0000
        # We need to extract the hour ignoring timezone
        try:
            # Parse the timestamp
            # Format: DD/Mon/YYYY:HH:MM:SS +ZZZZ
            ts_match = re.match(r'(\d+)/(\w+)/(\d+):(\d+):(\d+):(\d+)', timestamp)
            if ts_match:
                day, month_str, year, hour, minute, second = ts_match.groups()
                # Convert month name to number
                month_names = {
                    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4,
                    'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8,
                    'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
                }
                if month_str in month_names:
                    month = month_names[month_str]
                    # Format as "YYYY-MM-DD HH"
                    hour_key = f"{year}-{month:02d}-{int(day):02d} {int(hour):02d}"
                    requests_per_hour[hour_key] += 1
                else:
                    # Invalid month name, treat as malformed? 
                    # The problem says lines that don't match format are malformed.
                    # But we already matched the regex. Let's be lenient here and just skip hour counting.
                    pass
            else:
                # Timestamp doesn't match expected pattern, but we still count it as valid request
                # since the overall line matched. Just don't add to requests_per_hour.
                pass
        except Exception:
            # If timestamp parsing fails, still count the request but don't add to hourly stats
            pass
    
    # Calculate error rate
    if total_requests == 0:
        error_rate = 0.0
    else:
        error_count = sum(count for status, count in status_counts.items() if 400 <= status <= 599)
        error_rate = round(error_count / total_requests, 4)
    
    # Get top 3 paths sorted by count descending, then path ascending
    top_paths = sorted(path_counts.items(), key=lambda x: (-x[1], x[0]))[:3]
    
    return {
        "total_requests": total_requests,
        "malformed": malformed,
        "unique_ips": len(ips),
        "status_counts": dict(status_counts),
        "bytes_total": bytes_total,
        "error_rate": error_rate,
        "top_paths": top_paths,
        "requests_per_hour": dict(requests_per_hour),
    }
