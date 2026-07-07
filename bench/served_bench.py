import json, time, statistics, threading, urllib.request

URL = "http://127.0.0.1:9310/v1/chat/completions"

# Build a ~1024-token prompt: repeated varied words, roughly 1 token per word
words = ("The quick brown fox jumps over the lazy dog near a quiet river while "
         "seventeen curious engineers measure throughput latency and bandwidth "
         "of distributed inference systems running on modern accelerators ").split()
prompt_words = []
i = 0
while len(prompt_words) < 330:
    prompt_words.append(words[i % len(words)] + str(i % 97))
    i += 1
prompt = "Repeat the following text back, then summarize it: " + " ".join(prompt_words)

def one_request():
    body = json.dumps({
        "model": "bench",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 256,
        "temperature": 0.0,
    }).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=600) as r:
        resp = json.load(r)
    wall = time.time() - t0
    u = resp["usage"]
    return u["prompt_tokens"], u["completion_tokens"], wall

# Warmup
pt, ct, w = one_request()
print(f"warmup: prompt_tokens={pt} completion_tokens={ct} wall={w:.2f}s")

# Single-stream: 3 runs
singles = []
for n in range(3):
    pt, ct, w = one_request()
    tps = ct / w
    singles.append(tps)
    print(f"single run {n+1}: prompt_tokens={pt} completion_tokens={ct} wall={w:.2f}s gen_tok_s={tps:.2f}")
single_median = statistics.median(singles)
print(f"single_stream_median_tok_s={single_median:.2f}")

# 8 concurrent
results = [None] * 8
def worker(idx):
    results[idx] = one_request()
threads = [threading.Thread(target=worker, args=(k,)) for k in range(8)]
t0 = time.time()
for t in threads: t.start()
for t in threads: t.join()
wall = time.time() - t0
total_ct = sum(r[1] for r in results)
agg = total_ct / wall
print(f"conc8: total_completion_tokens={total_ct} wall={wall:.2f}s aggregate_tok_s={agg:.2f}")
print(json.dumps({"single_stream_tok_s": round(single_median, 2), "conc8_aggregate_tok_s": round(agg, 2)}))
