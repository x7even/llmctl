Write a Python module with a function `analyze_log(lines)` that summarises a web server access log in Common Log Format. Standard library only.

```python
def analyze_log(lines: Iterable[str]) -> dict: ...
```

Each line looks like:

```
127.0.0.1 - frank [10/Oct/2026:13:55:36 +0000] "GET /index.html?x=1 HTTP/1.1" 200 2326
```

i.e. `ip ident user [timestamp] "METHOD path PROTOCOL" status bytes`. The bytes field is `-` when no body was sent (count it as 0). Lines that do not match this format (blank lines, garbage, missing fields, non-numeric status) are *malformed*: skip them and count them.

Return a dict with exactly these keys:

- `"total_requests"`: number of valid lines.
- `"malformed"`: number of malformed lines.
- `"unique_ips"`: number of distinct client IPs among valid lines.
- `"status_counts"`: dict mapping each integer status code to how many valid lines had it.
- `"bytes_total"`: sum of the bytes fields of valid lines.
- `"error_rate"`: fraction of valid lines whose status is 400-599, as a float rounded to 4 decimals (`0.0` if there are no valid lines).
- `"top_paths"`: the 3 most requested paths as a list of `(path, count)` tuples, sorted by count descending then path ascending. The query string (everything from `?`) is not part of the path. If fewer than 3 distinct paths exist, return as many as there are.
- `"requests_per_hour"`: dict mapping `"YYYY-MM-DD HH"` to the number of valid requests in that hour, using the timestamp as written in the log (ignore the timezone offset). Month names are the usual English abbreviations (`Jan` ... `Dec`).

Output requirements: reply with **one** Python code block containing the complete module. No explanation outside the code block.
