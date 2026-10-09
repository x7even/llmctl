"""Web server access log analyzer (Common Log Format)."""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable, Dict, List, Tuple

# Regex for Common Log Format:
# ip ident user [timestamp] "METHOD path PROTOCOL" status bytes
#
# Fields:
#   ip:       \S+
#   ident:    \S+  (often '-')
#   user:     \S+  (often '-')
#   timestamp: [10/Oct/2026:13:55:36 +0000]
#   request:  "GET /index.html?x=1 HTTP/1.1"
#   status:   \d+
#   bytes:    \d+ or -

_CLF_RE = re.compile(
    r'^(\S+)\s+'          # ip
    r'(\S+)\s+'           # ident
    r'(\S+)\s+'           # user
    r'\[([^\]]+)\]\s+'    # timestamp
    r'"(\S+)\s+(\S+)\s+(\S+)"\s+'  # method, path, protocol
    r'(\d+)\s+'           # status
    r'(\d+|-)\s*$'        # bytes
)

_MONTH_MAP = {
    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12',
}

# Regex to parse the timestamp inside the brackets
_TIMESTAMP_RE = re.compile(
    r'^(\d{2})/(\w{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2})\s+([+-]\d{4})$'
)


def _parse_timestamp(ts: str) -> str | None:
    """Parse a CLF timestamp and return 'YYYY-MM-DD HH' or None if invalid."""
    m = _TIMESTAMP_RE.match(ts)
    if not m:
        return None
    day, mon, year, hour, _min, _sec, _tz = m.groups()
    mon_num = _MONTH_MAP.get(mon)
    if mon_num is None:
        return None
    return f"{year}-{mon_num}-{day} {hour}"


def analyze_log(lines: Iterable[str]) -> dict:
    """Summarise a web server access log in Common Log Format.

    Args:
        lines: An iterable of log line strings.

    Returns:
        A dict with keys: total_requests, malformed, unique_ips,
        status_counts, bytes_total, error_rate, top_paths,
        requests_per_hour.
    """
    total_requests = 0
    malformed = 0
    ips: set = set()
    status_counts: Dict[int, int] = {}
    bytes_total = 0
    error_count = 0
    path_counts: Counter = Counter()
    hour_counts: Dict[str, int] = {}

    for line in lines:
        # Strip trailing newline / whitespace
        stripped = line.rstrip('\r\n')
        if not stripped:
            malformed += 1
            continue

        m = _CLF_RE.match(stripped)
        if not m:
            malformed += 1
            continue

        ip, _ident, _user, timestamp, _method, path, _protocol, status_str, bytes_str = m.groups()

        # Validate status is numeric (already guaranteed by regex \d+, but check anyway)
        try:
            status = int(status_str)
        except ValueError:
            malformed += 1
            continue

        # Validate bytes field
        if bytes_str == '-':
            size = 0
        else:
            try:
                size = int(bytes_str)
            except ValueError:
                malformed += 1
                continue

        # Parse timestamp for hour bucketing
        hour_key = _parse_timestamp(timestamp)
        if hour_key is None:
            malformed += 1
            continue

        # All valid
        total_requests += 1
        ips.add(ip)
        status_counts[status] = status_counts.get(status, 0) + 1
        bytes_total += size
        if 400 <= status <= 599:
            error_count += 1

        # Strip query string from path
        clean_path = path.split('?', 1)[0]
        path_counts[clean_path] += 1

        hour_counts[hour_key] = hour_counts.get(hour_key, 0) + 1

    # Error rate
    if total_requests > 0:
        error_rate = round(error_count / total_requests, 4)
    else:
        error_rate = 0.0

    # Top 3 paths: sort by count descending, then path ascending
    sorted_paths = sorted(path_counts.items(), key=lambda x: (-x[1], x[0]))
    top_paths: List[Tuple[str, int]] = sorted_paths[:3]

    return {
        "total_requests": total_requests,
        "malformed": malformed,
        "unique_ips": len(ips),
        "status_counts": status_counts,
        "bytes_total": bytes_total,
        "error_rate": error_rate,
        "top_paths": top_paths,
        "requests_per_hour": hour_counts,
    }
