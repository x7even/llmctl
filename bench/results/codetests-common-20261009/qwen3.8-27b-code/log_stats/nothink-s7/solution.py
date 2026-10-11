"""Web server access log analyzer (Common Log Format)."""

from collections import Counter
from datetime import datetime
from typing import Dict, Iterable, List, Tuple


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
    ips = set()
    status_counts: Dict[int, int] = {}
    bytes_total = 0
    path_counts: Counter = Counter()
    hour_counts: Dict[str, int] = {}
    error_count = 0

    month_map = {
        "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
        "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
        "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
    }

    for line in lines:
        line = line.strip()
        if not line:
            malformed += 1
            continue

        # Try to parse the line
        parsed = _parse_line(line)
        if parsed is None:
            malformed += 1
            continue

        ip, method, path, protocol, status, nbytes, timestamp_str = parsed

        total_requests += 1
        ips.add(ip)
        status_counts[status] = status_counts.get(status, 0) + 1
        bytes_total += nbytes

        if 400 <= status <= 599:
            error_count += 1

        # Path without query string
        clean_path = path.split("?", 1)[0]
        path_counts[clean_path] += 1

        # Parse timestamp for hour bucket
        hour_key = _timestamp_to_hour(timestamp_str, month_map)
        if hour_key is not None:
            hour_counts[hour_key] = hour_counts.get(hour_key, 0) + 1

    # Error rate
    if total_requests > 0:
        error_rate = round(error_count / total_requests, 4)
    else:
        error_rate = 0.0

    # Top paths: sort by count desc, then path asc
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


def _parse_line(line: str):
    """Parse a single Common Log Format line.

    Returns a tuple (ip, method, path, protocol, status, nbytes, timestamp_str)
    or None if the line is malformed.
    """
    # Expected format:
    # ip ident user [timestamp] "METHOD path PROTOCOL" status bytes
    # The ident and user fields can be anything (including '-'), but they
    # are separated by spaces. We need to be careful with the quoted request.

    # Find the bracketed timestamp
    bracket_start = line.find("[")
    if bracket_start == -1:
        return None
    bracket_end = line.find("]", bracket_start)
    if bracket_end == -1:
        return None

    timestamp_str = line[bracket_start + 1:bracket_end]

    # Before the bracket: ip ident user
    prefix = line[:bracket_start].strip()
    # Split prefix into at least 3 parts (ip, ident, user)
    prefix_parts = prefix.split()
    if len(prefix_parts) < 3:
        return None
    ip = prefix_parts[0]

    # After the bracket: "METHOD path PROTOCOL" status bytes
    rest = line[bracket_end + 1:].strip()
    if not rest.startswith('"'):
        return None
    quote_end = rest.find('"', 1)
    if quote_end == -1:
        return None
    request = rest[1:quote_end]

    # After the closing quote: status bytes
    after_quote = rest[quote_end + 1:].strip()
    after_parts = after_quote.split()
    if len(after_parts) < 2:
        return None
    status_str = after_parts[0]
    bytes_str = after_parts[1]

    # Validate status
    try:
        status = int(status_str)
    except ValueError:
        return None

    # Validate bytes
    if bytes_str == "-":
        nbytes = 0
    else:
        try:
            nbytes = int(bytes_str)
        except ValueError:
            return None

    # Parse the request: METHOD path PROTOCOL
    request_parts = request.split()
    if len(request_parts) < 2:
        return None
    method = request_parts[0]
    path = request_parts[1]
    protocol = request_parts[2] if len(request_parts) >= 3 else ""

    # Validate timestamp
    if not _validate_timestamp(timestamp_str):
        return None

    return (ip, method, path, protocol, status, nbytes, timestamp_str)


def _validate_timestamp(ts: str) -> bool:
    """Check if timestamp looks like DD/Mon/YYYY:HH:MM:SS +ZZZZ."""
    # Expected: 10/Oct/2026:13:55:36 +0000
    # Format: DD/Mon/YYYY:HH:MM:SS +ZZZZ
    parts = ts.split(" ")
    if len(parts) != 2:
        return False
    date_part = parts[0]
    # offset = parts[1]  # not strictly validated beyond presence

    # date_part should be like DD/Mon/YYYY:HH:MM:SS
    # Split by '/'
    slashes = date_part.split("/")
    if len(slashes) != 3:
        return False
    day_str, mon_str, rest = slashes
    if len(day_str) != 2 or not day_str.isdigit():
        return False
    if mon_str not in ("Jan","Feb","Mar","Apr","May","Jun",
                        "Jul","Aug","Sep","Oct","Nov","Dec"):
        return False
    # rest should be YYYY:HH:MM:SS
    colon_parts = rest.split(":")
    if len(colon_parts) != 4:
        return False
    year_str, hour_str, min_str, sec_str = colon_parts
    if len(year_str) != 4 or not year_str.isdigit():
        return False
    if len(hour_str) != 2 or not hour_str.isdigit():
        return False
    if len(min_str) != 2 or not min_str.isdigit():
        return False
    if len(sec_str) != 2 or not sec_str.isdigit():
        return False
    return True


def _timestamp_to_hour(ts: str, month_map: dict):
    """Convert timestamp string to 'YYYY-MM-DD HH' key, or None."""
    parts = ts.split(" ")
    if len(parts) != 2:
        return None
    date_part = parts[0]
    slashes = date_part.split("/")
    if len(slashes) != 3:
        return None
    day_str, mon_str, rest = slashes
    colon_parts = rest.split(":")
    if len(colon_parts) != 4:
        return None
    year_str, hour_str, min_str, sec_str = colon_parts
    month = month_map.get(mon_str)
    if month is None:
        return None
    return f"{year_str}-{month:02d}-{day_str} {hour_str}"
