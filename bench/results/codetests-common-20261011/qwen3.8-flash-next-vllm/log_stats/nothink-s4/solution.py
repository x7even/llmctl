import re
from collections import Counter
from datetime import datetime
from typing import Iterable, Dict, List, Tuple

# Common Log Format regex
# ip ident user [timestamp] "METHOD path PROTOCOL" status bytes
CLF_PATTERN = re.compile(
    r'^(\S+)\s+'           # ip
    r'(\S+)\s+'            # ident
    r'(\S+)\s+'            # user
    r'\[([^\]]+)\]\s+'     # timestamp
    r'"(\S+)\s+(\S+)\s+(\S+)"\s+'  # "METHOD path PROTOCOL"
    r'(\d{3})\s+'          # status (must be 3 digits)
    r'(\d+|-)$'            # bytes (digits or -)
)

def analyze_log(lines: Iterable[str]) -> dict:
    total_requests = 0
    malformed = 0
    ips = set()
    status_counts: Dict[int, int] = {}
    bytes_total = 0
    path_counter: Counter = Counter()
    requests_per_hour: Dict[str, int] = {}
    
    # Month abbreviation to number mapping
    month_map = {
        'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
        'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
        'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
    }
    
    for line in lines:
        line = line.rstrip('\n\r')
        match = CLF_PATTERN.match(line)
        if not match:
            malformed += 1
            continue
        
        ip = match.group(1)
        timestamp_str = match.group(4)
        method = match.group(5)
        path_with_query = match.group(6)
        protocol = match.group(7)
        status_str = match.group(8)
        bytes_str = match.group(9)
        
        # Validate status is numeric (it's already \d{3} from regex, but double-check)
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
            path = path_with_query.split('?', 1)[0]
        else:
            path = path_with_query
        
        # Parse timestamp to extract hour
        # Format: 10/Oct/2026:13:55:36 +0000
        # We need to extract day, month, year, hour
        ts_match = re.match(r'^(\d+)/(\w+)/(\d+):(\d+):\d+:\d+\s+[+-]\d{4}$', timestamp_str)
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
        hour_key = f"{year}-{month_num}-{day} {hour}"
        
        # All valid, update counters
        total_requests += 1
        ips.add(ip)
        status_counts[status] = status_counts.get(status, 0) + 1
        bytes_total += bytes_val
        path_counter[path] += 1
        requests_per_hour[hour_key] = requests_per_hour.get(hour_key, 0) + 1
    
    # Calculate error rate
    if total_requests == 0:
        error_rate = 0.0
    else:
        error_count = sum(count for status, count in status_counts.items() if 400 <= status <= 599)
        error_rate = round(error_count / total_requests, 4)
    
    # Top paths: 3 most requested, sorted by count desc then path asc
    top_paths_list = sorted(path_counter.items(), key=lambda x: (-x[1], x[0]))
    top_paths = top_paths_list[:3]
    
    return {
        "total_requests": total_requests,
        "malformed": malformed,
        "unique_ips": len(ips),
        "status_counts": status_counts,
        "bytes_total": bytes_total,
        "error_rate": error_rate,
        "top_paths": top_paths,
        "requests_per_hour": requests_per_hour
    }
