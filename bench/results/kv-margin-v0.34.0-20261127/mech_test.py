"""Step 0 mechanism probe, run inside the v0.34.0 image on one GPU.

Mode via argv[1]:
  stock      : no allocator env, no runtime toggle
  runtime    : no env; toggle expandable_segments:True at runtime the way PR #69994 does
  (env modes are set by the caller: PYTORCH_ALLOC_CONF / PYTORCH_CUDA_ALLOC_CONF / PYTORCH_HIP_ALLOC_CONF)
Replays the PR's unit-test allocation order under a per-process cap.
"""
import os, sys, json
import torch
from vllm.device_allocator.alloc_conf import (
    EXPANDABLE_SEGMENTS, alloc_conf_from_env, current_alloc_conf,
    expandable_segments_enabled, set_alloc_conf, with_conf_flag)

mode = sys.argv[1]
mib = 1 << 20
dev = torch.device("cuda:0")
torch.empty(1, device=dev)
print("mode", mode, "torch", torch.__version__, "hip", torch.version.hip)
print("env conf:", repr(alloc_conf_from_env()))
print("live expandable before:", expandable_segments_enabled(), "live conf:", repr(current_alloc_conf()))
if mode == "runtime":
    set_alloc_conf(with_conf_flag(current_alloc_conf(), EXPANDABLE_SEGMENTS, True))
    print("live expandable after runtime set:", expandable_segments_enabled())

def t(n):
    return torch.empty(n * mib, dtype=torch.uint8, device=dev)

# segment type check
x = t(64)
segs = torch.cuda.memory._snapshot()["segments"]
print("segment types:", sorted({s.get("segment_type") for s in segs}), "is_expandable:",
      sorted({s.get("is_expandable") for s in segs}))
del x
torch.cuda.empty_cache()

total = torch.cuda.get_device_properties(0).total_memory
limit = torch.cuda.memory_reserved(dev) + 700 * mib
torch.cuda.set_per_process_memory_fraction(min(limit / total, 1.0), dev)
ok = True
try:
    logits = t(300); del logits
    hs = t(20)
    logits = t(300)
    sc = t(300)
    print("PR scenario: PASS reserved=%.0f MiB limit=%.0f MiB" % (torch.cuda.memory_reserved(dev) / mib, limit / mib))
    del hs, logits, sc
except torch.OutOfMemoryError as e:
    ok = False
    print("PR scenario: OOM:", str(e).splitlines()[0][:300])
st = torch.cuda.memory_stats(dev)
print("num_alloc_retries", st.get("num_alloc_retries"), "num_ooms", st.get("num_ooms"))
