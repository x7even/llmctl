import re
from collections import Counter

_LINE = re.compile(
    r'^(\S+) \S+ \S+ \[(\d{2})/([A-Za-z]{3})/(\d{4}):(\d{2}):\d{2}:\d{2} [+-]\d{4}\] '
    r'"[A-Z]+ (\S+) [^"]*" (\d{3}) (\d+|-)$'
)
_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def analyze_log(lines):
    total = bad = nbytes = errors = 0
    ips, status, paths, hours = set(), Counter(), Counter(), Counter()
    for raw in lines:
        m = _LINE.match(raw.strip())
        if not m or m.group(3) not in _MONTHS:
            bad += 1
            continue
        ip, day, mon, year, hour, path, st, size = m.groups()
        total += 1
        ips.add(ip)
        status[int(st)] += 1
        errors += int(st) >= 400
        nbytes += 0 if size == "-" else int(size)
        paths[path.split("?", 1)[0]] += 1
        hours[f"{year}-{_MONTHS[mon]:02d}-{day} {hour}"] += 1
    top = sorted(paths.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    return {
        "total_requests": total,
        "malformed": bad,
        "unique_ips": len(ips),
        "status_counts": dict(status),
        "bytes_total": nbytes,
        "error_rate": round(errors / total, 4) if total else 0.0,
        "top_paths": top,
        "requests_per_hour": dict(hours),
    }
