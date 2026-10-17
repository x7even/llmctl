#!/usr/bin/env python3
"""
Unit tests for scripts/llmkv (KV-budget reader for vLLM profiles): pulling a profile's cmd
out of models.yaml, applying flag overrides to the vllm portion without touching podman's,
forcing a throwaway container name, parsing the KV numbers out of a startup log, and turning
a KV token total into a context x concurrency table.

No GPU, no podman and no server are needed: models.yaml fragments and startup logs are
supplied as strings.

Run:  python3 tests/test_llmkv.py        (also pytest-compatible)
"""
import importlib.machinery
import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "llmkv"

_loader = importlib.machinery.SourceFileLoader("llmkv", str(SCRIPT))
_spec = importlib.util.spec_from_loader("llmkv", _loader)
kv = importlib.util.module_from_spec(_spec)
_loader.exec_module(kv)

# A models.yaml fragment shaped like the real one: two profiles, line-continuation cmd blocks,
# podman options before the image name and vllm flags after it.
YAML = """version: 2
models:
  other-profile:
    ttl: 0
    cmd: |
      podman run --rm --entrypoint="" --name llmstack-vllm-other \\
        docker.io/vllm/vllm-openai-rocm:v0.26.0 \\
        vllm serve /models/other --port 8000
  qwen-test:
    ttl: 0
    concurrencyLimit: 64
    cmd: |
      podman run --rm --entrypoint="" \\
        --name llmstack-vllm-qwen-test \\
        --ipc=private --shm-size=32g --network=host \\
        -e HSA_ENABLE_SDMA=0 \\
        -v /mnt/models/llm:/models:ro \\
        docker.io/vllm/vllm-openai-rocm:v0.26.0 \\
        vllm serve /models/qwen \\
          --served-model-name ${MODEL_ID} \\
          --tensor-parallel-size 4 \\
          --max-model-len 131072 \\
          --max-num-seqs 32 \\
          --gpu-memory-utilization 0.95 \\
          --enable-prefix-caching \\
          --speculative-config '{"method": "mtp", "num_speculative_tokens": 2}' \\
          --cudagraph-capture-sizes 1 2 4 8 16 32 \\
          --port ${PORT}
  trailing-profile:
    ttl: 0
"""


def _argv(port=9711):
    cmd = kv.extract_cmd(YAML, "qwen-test")
    return kv.split_argv(cmd, "qwen-test", port)


# --- extract_cmd ---------------------------------------------------------------------

def test_extract_cmd_picks_the_named_profile_only():
    cmd = kv.extract_cmd(YAML, "qwen-test")
    assert "/models/qwen" in cmd
    assert "/models/other" not in cmd, "bled into the neighbouring profile"


def test_extract_cmd_stops_at_the_next_profile():
    cmd = kv.extract_cmd(YAML, "other-profile")
    assert "/models/other" in cmd
    assert "qwen" not in cmd


def test_extract_cmd_rejects_an_unknown_profile():
    try:
        kv.extract_cmd(YAML, "no-such-profile")
    except SystemExit as e:
        assert "no-such-profile" in str(e)
    else:
        raise AssertionError("an unknown profile must not be silently accepted")


def test_extract_cmd_rejects_a_profile_with_no_cmd():
    try:
        kv.extract_cmd(YAML, "trailing-profile")
    except SystemExit as e:
        assert "cmd" in str(e)
    else:
        raise AssertionError("a profile with no cmd block must not be silently accepted")


def test_extract_cmd_matches_the_whole_profile_name():
    """"qwen-test" must not be found by asking for "qwen"."""
    try:
        kv.extract_cmd(YAML, "qwen")
    except SystemExit:
        pass
    else:
        raise AssertionError("a prefix of a profile name must not match it")


# --- split_argv / find_serve_split ---------------------------------------------------

def test_split_argv_substitutes_what_llama_swap_substitutes():
    argv = _argv(port=9999)
    assert "qwen-test" in argv, "${MODEL_ID} was not substituted"
    assert "9999" in argv, "${PORT} was not substituted"
    assert not any("${" in a for a in argv)


def test_split_argv_keeps_an_empty_entrypoint_as_one_argument():
    assert "--entrypoint=" in _argv()


def test_find_serve_split_lands_on_the_first_vllm_flag():
    argv = _argv()
    at = kv.find_serve_split(argv)
    assert argv[at - 2] == "serve"
    assert argv[at - 1] == "/models/qwen"
    assert argv[at].startswith("--")


def test_find_serve_split_refuses_a_cmd_with_no_serve():
    try:
        kv.find_serve_split(["podman", "run", "--rm", "image"])
    except SystemExit:
        pass
    else:
        raise AssertionError("a cmd without 'vllm serve <model>' must be an error")


# --- apply_overrides -----------------------------------------------------------------

def test_override_replaces_an_existing_flag_in_place():
    argv = _argv()
    at = kv.find_serve_split(argv)
    before = argv.index("--gpu-memory-utilization")
    out, applied = kv.apply_overrides(argv, at, {"gpu-memory-utilization": "0.92"})
    assert out.index("--gpu-memory-utilization") == before, "flag moved"
    assert out[before + 1] == "0.92"
    assert applied["--gpu-memory-utilization"] == ("0.95", "0.92")
    assert len(out) == len(argv), "replacing a value must not change the argv length"


def test_override_replaces_every_value_of_a_list_valued_flag():
    """--cudagraph-capture-sizes 1 2 4 8 16 32 is one flag with six values.

    Replacing only the first would leave "2 4 8 16 32" behind as stray positionals, and vllm
    would either reject them or - worse - capture the old sizes. This is the flag the MTP
    graph-capture lever changes, so it has to be right.
    """
    argv = _argv()
    at = kv.find_serve_split(argv)
    i = argv.index("--cudagraph-capture-sizes")
    out, applied = kv.apply_overrides(
        argv, at, {"cudagraph-capture-sizes": ["1", "2", "4", "8", "16", "32", "64", "128"]})
    assert out[i + 1:i + 9] == ["1", "2", "4", "8", "16", "32", "64", "128"]
    assert out[i + 9] == "--port", "a stray old value survived"
    assert applied["--cudagraph-capture-sizes"] == ("1 2 4 8 16 32", "1 2 4 8 16 32 64 128")


def test_override_shrinking_a_list_valued_flag_leaves_nothing_behind():
    argv = _argv()
    at = kv.find_serve_split(argv)
    i = argv.index("--cudagraph-capture-sizes")
    out, _ = kv.apply_overrides(argv, at, {"cudagraph-capture-sizes": ["1", "2"]})
    assert out[i + 1:i + 3] == ["1", "2"]
    assert out[i + 3] == "--port"


def test_split_values_only_splits_a_bare_comma_list():
    assert kv.split_values("1,2,4,8") == ["1", "2", "4", "8"]
    assert kv.split_values("0.92") == ["0.92"]
    assert kv.split_values("expandable_segments:True") == ["expandable_segments:True"]
    # the flag that would break if this were greedy
    spec = '{"method": "mtp", "num_speculative_tokens": 2}'
    assert kv.split_values(spec) == [spec], "a JSON value must stay one argument"


def test_override_keeps_a_json_valued_flag_as_one_argument():
    argv = _argv()
    at = kv.find_serve_split(argv)
    new = '{"method": "mtp", "num_speculative_tokens": 3}'
    out, _ = kv.apply_overrides(argv, at, {"speculative-config": kv.split_values(new)})
    assert out[out.index("--speculative-config") + 1] == new
    assert out[out.index("--speculative-config") + 2].startswith("--")


def test_override_appends_a_flag_that_is_absent():
    argv = _argv()
    at = kv.find_serve_split(argv)
    out, applied = kv.apply_overrides(argv, at, {"kv-cache-dtype": "fp8"})
    assert out[-2:] == ["--kv-cache-dtype", "fp8"]
    assert applied["--kv-cache-dtype"] == (None, "fp8")


def test_override_accepts_a_flag_written_with_dashes():
    argv = _argv()
    at = kv.find_serve_split(argv)
    out, _ = kv.apply_overrides(argv, at, {"--max-num-seqs": "16"})
    assert out[out.index("--max-num-seqs") + 1] == "16"
    assert "----max-num-seqs" not in out


def test_override_gives_a_value_to_a_bare_boolean_flag():
    """--enable-prefix-caching has no value; an override must insert one, not eat a neighbour."""
    argv = _argv()
    at = kv.find_serve_split(argv)
    i = argv.index("--enable-prefix-caching")
    neighbour = argv[i + 1]
    out, _ = kv.apply_overrides(argv, at, {"enable-prefix-caching": "False"})
    assert out[i + 1] == "False"
    assert out[i + 2] == neighbour, "the next flag was overwritten"


def test_override_never_touches_the_podman_half():
    """--name exists before the split too; the podman one must be left alone."""
    argv = _argv()
    at = kv.find_serve_split(argv)
    out, applied = kv.apply_overrides(argv, at, {"name": "hijacked"})
    assert out[out.index("--name") + 1] == "llmstack-vllm-qwen-test", "podman --name was edited"
    assert out[-2:] == ["--name", "hijacked"], "the override should have appended past the split"
    assert applied["--name"] == (None, "hijacked")


def test_no_overrides_is_a_no_op():
    argv = _argv()
    out, applied = kv.apply_overrides(argv, kv.find_serve_split(argv), {})
    assert out == argv and applied == {}


def test_apply_overrides_does_not_mutate_its_input():
    argv = _argv()
    snapshot = list(argv)
    kv.apply_overrides(argv, kv.find_serve_split(argv), {"gpu-memory-utilization": "0.5"})
    assert argv == snapshot


# --- rename_and_isolate --------------------------------------------------------------

def test_rename_replaces_the_production_container_name():
    out = kv.rename_and_isolate(_argv(), "llmkv-probe")
    assert out[out.index("--name") + 1] == "llmkv-probe"
    assert "llmstack-vllm-qwen-test" not in out, "production container name survived"


def test_rename_adds_a_name_when_the_profile_has_none():
    out = kv.rename_and_isolate(["podman", "run", "--rm", "image"], "llmkv-probe")
    assert out[out.index("--name") + 1] == "llmkv-probe"


def test_rename_forces_detached_mode():
    out = kv.rename_and_isolate(_argv(), "llmkv-probe")
    assert "-d" in out
    assert out.index("-d") == out.index("run") + 1


def test_rename_does_not_add_a_second_detach_flag():
    out = kv.rename_and_isolate(["podman", "run", "--detach", "image"], "n")
    assert "-d" not in out


# --- concurrency_table ---------------------------------------------------------------

def test_concurrency_table_divides_the_kv_budget_by_context():
    rows = kv.concurrency_table(1_009_850, 131072)
    at = {r["context"]: r["streams"] for r in rows}
    assert at[131072] == 7.7
    assert at[65536] == 15.41
    assert at[8192] == 123.27


def test_concurrency_table_stops_at_max_model_len():
    rows = kv.concurrency_table(1_009_850, 32768)
    assert [r["context"] for r in rows] == [8192, 16384, 32768]


def test_concurrency_table_without_a_known_max_model_len_shows_every_point():
    rows = kv.concurrency_table(1_009_850, None)
    assert [r["context"] for r in rows] == kv.CONTEXT_POINTS


def test_concurrency_table_reports_a_budget_too_small_for_one_stream():
    """The number that matters: a profile can advertise a context it cannot serve once."""
    rows = kv.concurrency_table(100_000, 131072)
    assert {r["context"]: r["streams"] for r in rows}[131072] < 1.0


# --- parse_startup -------------------------------------------------------------------

# Real lines, copied from a 27B startup log.
LOG = """(Worker_TP0 pid=490) INFO 10-17 08:36:43 [gpu_worker.py:739] CUDA graph memory profiling is enabled (default since v0.21.0). The current --gpu-memory-utilization=0.9500 is equivalent to --gpu-memory-utilization=0.9368 without CUDA graph memory profiling. To maintain the same effective KV cache size as before, increase --gpu-memory-utilization to 0.9632.
INFO 10-17 19:08:02 [gpu_worker.py:298] Available KV cache memory: 17.60 GiB
INFO 10-17 19:08:03 [kv_cache_utils.py:1229] GPU KV cache size: 1,009,850 tokens
INFO 10-17 19:08:03 [kv_cache_utils.py:1233] Maximum concurrency for 131,072 tokens per request: 7.70x
Capturing CUDA graphs (FULL):   0%|          | 0/4 [00:00<?, ?it/s]Capturing CUDA graphs (FULL): 100%|##########| 4/4 [00:00<00:00,  5.00it/s]
Capturing CUDA graphs (PIECEWISE):   0%|          | 0/6 [00:00<?, ?it/s]Capturing CUDA graphs (PIECEWISE): 100%|##########| 6/6 [00:02<00:00,  1.37it/s]
(Worker_TP0 pid=475) INFO 10-17 20:19:33 [gpu_model_runner.py:6844] Graph capturing finished in 4 secs, took 0.70 GiB
(Worker_TP0 pid=475) INFO 10-17 20:19:33 [gpu_worker.py:857] Free memory on device (31.42/31.86 GiB) on startup. Desired GPU memory utilization is (0.95, 30.27 GiB). Actual usage is 7.65 GiB for weight, 2.82 GiB for peak activation, 1.78 GiB for non-torch memory, and 0.7 GiB for CUDAGraph memory. Current kv cache memory in use is 17.6 GiB.
INFO 10-17 19:09:41 [api_server.py:1813] Application startup complete.
"""

# A real config dump is thousands of characters; this is the one key it is read for.
CONFIG_DUMP = "... 'cudagraph_mode': 3, 'cudagraph_capture_sizes': [1, 2, 4, 8, 16, 32], ..."


def test_parse_startup_reads_all_three_numbers():
    got = kv.parse_startup(LOG)
    assert got["kv_cache_tokens"] == 1_009_850, "thousands separators must be stripped"
    assert got["available_kv_gib_per_gpu"] == 17.60
    assert got["vllm_reported_concurrency"] == {"at_tokens": 131072, "streams": 7.70}


def test_parse_startup_reads_the_captured_graph_count_not_the_requested_one():
    """The profile asks for six sizes; with MTP only four survive rounding.

    Reading the requested list from the config dump would report six and hide the whole
    problem, so the count comes off the FULL progress bar's own total. PIECEWISE bars (prefill)
    must not be counted: they are not subject to the spec-decode rounding.
    """
    assert kv.parse_startup(LOG)["full_cudagraphs_captured"] == 4


def test_parse_startup_prices_the_graph_capture():
    """What the capture-size lever costs: graph memory comes out of the KV budget.

    The tqdm bar above does not actually reach `podman logs` on this stack, so the graph
    count can be absent while this line is present - which is why the cost is read
    separately and not derived from the count.
    """
    got = kv.parse_startup(LOG)
    assert got["graph_mem_gib"] == 0.70
    assert got["graph_capture_s"] == 4
    assert got["mem_split_gib"] == {"weight": 7.65, "peak_activation": 2.82,
                                    "non_torch": 1.78, "cudagraph": 0.7}


def test_parse_startup_reads_the_requested_capture_sizes_separately():
    """Requested and captured are different numbers under MTP; report both, conflate neither."""
    assert kv.parse_startup(CONFIG_DUMP)["requested_capture_sizes"] == [1, 2, 4, 8, 16, 32]
    assert kv.parse_startup(CONFIG_DUMP)["full_cudagraphs_captured"] is None


def test_parse_startup_reads_the_effective_utilization():
    """0.95 requested is 0.9368 effective once cudagraph profiling has taken its share."""
    got = kv.parse_startup(LOG)
    assert got["requested_util"] == 0.95
    assert got["effective_util"] == 0.9368


def test_parse_startup_returns_nones_rather_than_raising_on_a_failed_boot():
    got = kv.parse_startup(
        "torch.OutOfMemoryError: HIP out of memory\nTraceback (most recent call last)")
    assert got == {"kv_cache_tokens": None, "available_kv_gib_per_gpu": None,
                   "vllm_reported_concurrency": None, "full_cudagraphs_captured": None,
                   "requested_capture_sizes": None, "graph_capture_s": None,
                   "graph_mem_gib": None, "mem_split_gib": None,
                   "requested_util": None, "effective_util": None}


def test_parse_startup_on_an_empty_log():
    assert kv.parse_startup("")["kv_cache_tokens"] is None


def test_failure_regex_catches_the_mtp_drafter_oom():
    assert kv.FAIL_RE.search(
        "torch.OutOfMemoryError: HIP out of memory. Tried to allocate 640.00 MiB")
    assert kv.READY_RE.search(LOG)


# --- CLI ------------------------------------------------------------------------------

def _run(args):
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, timeout=120)


def test_cli_dry_run_builds_a_renamed_detached_command_and_boots_nothing():
    """--dry-run is the only CLI path safe to test: everything else needs the GPUs."""
    r = _run(["qwen3.8-27b-code", "--dry-run", "--set", "gpu-memory-utilization=0.92",
              "--env", "PYTORCH_HIP_ALLOC_CONF=expandable_segments:True",
              "--name", "llmkv-probe", "--port", "9711"])
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "--name llmkv-probe" in out
    assert "llmstack-vllm-qwen3.8-27b-code" not in out, "production container name survived"
    assert "run -d" in out, "not detached"
    assert "--gpu-memory-utilization 0.92" in out
    assert "PYTORCH_HIP_ALLOC_CONF=expandable_segments:True" in out
    assert out.index("-e PYTORCH_HIP_ALLOC_CONF") < out.index("docker.io/vllm"), \
        "podman -e must precede the image name or podman rejects it"


def test_boot_execs_the_argv_as_given_without_a_second_podman():
    """argv already starts with podman: models.yaml's cmd is a whole command line.

    boot_and_read used to run ["podman", *argv], so every real boot exec'd
    "podman podman run -d ..." and died on podman's own argument parsing. The dry-run test
    above checks how argv is BUILT and cannot see what is EXEC'd, which is how this shipped.
    """
    calls = []

    class _Fake:
        returncode = 1
        stderr = "boom"
        stdout = ""

    def fake_run(argv, **kw):
        calls.append(list(argv))
        return _Fake()

    real = kv.subprocess.run
    kv.subprocess.run = fake_run
    try:
        argv = ["podman", "run", "-d", "--name", "probe", "img", "vllm", "serve", "/m"]
        try:
            kv.boot_and_read(argv, "probe", timeout=1)
        except SystemExit:
            pass
    finally:
        kv.subprocess.run = real

    boots = [c for c in calls if "run" in c]
    assert boots, f"no podman run was attempted; calls={calls}"
    assert boots[0] == argv, f"argv was rewritten before exec: {boots[0]}"
    assert boots[0].count("podman") == 1, f"duplicated podman: {boots[0]}"


def _fake_boot(keep, logs):
    """Drive boot_and_read against a scripted sequence of `podman logs` outputs."""
    seen = {"n": 0}

    class _Ok:
        returncode = 0
        stderr = ""

        def __init__(self, stdout=""):
            self.stdout = stdout

    def fake_run(argv, **kw):
        if "logs" in argv:
            i = min(seen["n"], len(logs) - 1)
            seen["n"] += 1
            return _Ok(logs[i])
        if argv[:2] == ["podman", "inspect"]:
            return _Ok("true\n")
        return _Ok("")

    real = kv.subprocess.run
    kv.subprocess.run = fake_run
    try:
        log = kv.boot_and_read(["podman", "run", "-d", "img"], "probe",
                               timeout=5, poll=0.0, keep=keep)
    finally:
        kv.subprocess.run = real
    return log, seen["n"]


KV_ONLY = "INFO [kv_cache_utils.py:1229] GPU KV cache size: 1,009,850 tokens\n"
SERVING = KV_ONLY + "INFO [api_server.py:1813] Application startup complete.\n"


def test_boot_returns_as_soon_as_the_kv_numbers_are_known():
    """The default job is reading the budget, and that is knowable before the API binds."""
    log, polls = _fake_boot(keep=False, logs=[KV_ONLY, SERVING])
    assert "Application startup complete" not in log
    assert polls == 1


def test_boot_with_keep_waits_for_the_api_not_just_for_the_kv_line():
    """--keep hands the container to a caller that will send requests.

    READY_RE is satisfied by the KV line itself, and KV is reported before CUDA graph capture,
    so stopping there returns a container that refuses connections for another minute or more -
    which is exactly what made the first real A/B run bench against a closed port.
    """
    log, polls = _fake_boot(keep=True, logs=[KV_ONLY, KV_ONLY, SERVING])
    assert "Application startup complete" in log, "handed back a server that was not serving"
    assert polls == 3, f"stopped polling too early ({polls})"


def test_boot_sees_readiness_when_it_is_only_on_stderr():
    """vLLM logs to stdout; uvicorn's "Application startup complete." goes to stderr.

    Reading only podman's stdout therefore finds the KV numbers and never finds readiness, so
    --keep polled until its 900 s timeout against a server that had been up for minutes.
    """
    seen = {"n": 0}

    class _Split:
        returncode = 0

        def __init__(self, out="", err=""):
            self.stdout, self.stderr = out, err

    def fake_run(argv, **kw):
        if "logs" in argv:
            seen["n"] += 1
            return _Split(KV_ONLY, "INFO:     Application startup complete.\n")
        if argv[:2] == ["podman", "inspect"]:
            return _Split("true\n")
        return _Split()

    real = kv.subprocess.run
    kv.subprocess.run = fake_run
    try:
        log = kv.boot_and_read(["podman", "run", "-d", "img"], "probe",
                               timeout=5, poll=0.0, keep=True)
    finally:
        kv.subprocess.run = real
    assert "Application startup complete" in log
    assert seen["n"] == 1, f"did not accept a stderr-only readiness line ({seen['n']} polls)"


def test_cli_rejects_a_malformed_set():
    r = _run(["qwen3.8-27b-code", "--dry-run", "--set", "no-equals-sign"])
    assert r.returncode != 0
    assert "FLAG=VALUE" in r.stderr


def test_cli_help_works():
    r = _run(["--help"])
    assert r.returncode == 0
    assert "context x concurrency" in r.stdout


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"ok   {fn.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
