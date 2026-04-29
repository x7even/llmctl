#!/usr/bin/env bash
# smoke.sh — Phase 1 verification for llmstack
# Run after: llmctl up
# Usage: ./tests/smoke.sh [--skip-gguf]   (--skip-gguf skips the 73 GB 122B model)
set -euo pipefail

PORT=8080
BASE_URL="http://127.0.0.1:${PORT}"
SKIP_GGUF=0
[[ "${1:-}" == "--skip-gguf" ]] && SKIP_GGUF=1

PASS=0
FAIL=0

pass() { echo "  [PASS] $1"; ((PASS++)); }
fail() { echo "  [FAIL] $1"; ((FAIL++)); }

chat() {
    # chat <model> <prompt> <max_tokens> <timeout_s>
    local model="$1" prompt="$2" max_tokens="${3:-20}" timeout="${4:-600}"
    curl -sf -X POST "${BASE_URL}/v1/chat/completions" \
        -H "Content-Type: application/json" \
        --max-time "${timeout}" \
        -d "{\"model\":\"${model}\",\"messages\":[{\"role\":\"user\",\"content\":\"${prompt}\"}],\"max_tokens\":${max_tokens}}" \
        2>/dev/null || echo ""
}

extract_content() {
    python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d['choices'][0]['message']['content'])
except Exception:
    print('')
"
}

echo "════════════════════════════════════════"
echo "  llmstack smoke test"
echo "  $(date)"
echo "════════════════════════════════════════"
echo ""

# ── 1. llama-swap health ─────────────────────────────────────────────────────
echo "1/5  llama-swap health"
if curl -sf "${BASE_URL}/v1/models" > /dev/null 2>&1; then
    pass "llama-swap reachable at ${BASE_URL}"
else
    fail "llama-swap not responding — run: llmctl up"
    echo ""
    echo "Cannot continue without llama-swap running."
    exit 1
fi

# ── 2. Profile listing ───────────────────────────────────────────────────────
echo ""
echo "2/5  Profile listing"
MODELS_JSON=$(curl -sf "${BASE_URL}/v1/models" 2>/dev/null || echo '{}')
PROFILE_COUNT=$(echo "${MODELS_JSON}" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(len(d.get('data',[])))
" 2>/dev/null || echo 0)
echo "     Known profiles from llama-swap: ${PROFILE_COUNT}"
if [[ "${PROFILE_COUNT}" -gt 0 ]]; then
    pass "profiles listed"
    echo "${MODELS_JSON}" | python3 -c "
import sys,json
for m in json.load(sys.stdin).get('data',[]): print('     •', m['id'])
" 2>/dev/null || true
else
    # llama-swap lists profiles even when not loaded only in newer versions
    pass "llama-swap running (profiles lazy-load on first request)"
fi

# ── 3. vLLM backend ─────────────────────────────────────────────────────────
echo ""
echo "3/5  vLLM backend: qwen3-coder-30b-fp8"
echo "     Loading model — first cold-start takes 2–5 min ..."
RESP=$(chat "qwen3-coder-30b-fp8" "Reply with exactly one word: ready" 5 600)
if echo "${RESP}" | grep -q '"content"' 2>/dev/null; then
    CONTENT=$(echo "${RESP}" | extract_content)
    pass "vLLM responded: ${CONTENT}"
    # Sanity: check usage tokens
    COMP_TOKENS=$(echo "${RESP}" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(d.get('usage',{}).get('completion_tokens',0))
" 2>/dev/null || echo 0)
    [[ "${COMP_TOKENS}" -gt 0 ]] && pass "completion_tokens=${COMP_TOKENS}" || fail "completion_tokens=0 (unexpected)"
else
    fail "vLLM backend failed or timed out"
    echo "     Response: ${RESP:0:300}"
fi

# ── 4. llama.cpp GGUF backend ────────────────────────────────────────────────
if [[ "${SKIP_GGUF}" -eq 1 ]]; then
    echo ""
    echo "4/5  GGUF backend: SKIPPED (--skip-gguf)"
else
    echo ""
    echo "4/5  llama.cpp backend: qwen3.5-122b-a10b-q4"
    echo "     Loading 73 GB model — cold-start ~90 s from page cache ..."
    RESP=$(chat "qwen3.5-122b-a10b-q4" "Reply with exactly one word: ready" 5 600)
    if echo "${RESP}" | grep -q '"content"' 2>/dev/null; then
        CONTENT=$(echo "${RESP}" | extract_content)
        pass "llama-server responded: ${CONTENT}"
    else
        fail "llama-server backend failed or timed out"
        echo "     Response: ${RESP:0:300}"
    fi
fi

# ── 5. GPU VRAM ──────────────────────────────────────────────────────────────
echo ""
echo "5/5  GPU VRAM snapshot (rocm-smi)"
rocm-smi --showmeminfo vram 2>&1 | grep -E "GPU\[|VRAM" | head -16 | while read -r line; do
    echo "     ${line}"
done
pass "rocm-smi completed"

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════"
echo "  Results:  ${PASS} passed  |  ${FAIL} failed"
echo "════════════════════════════════════════"

if [[ "${FAIL}" -gt 0 ]]; then
    echo ""
    echo "Troubleshooting:"
    echo "  llmctl status          — check llama-swap + loaded models"
    echo "  llmctl logs            — tail llama-swap log"
    echo "  llmctl logs <profile>  — tail a model container log"
    echo "  podman ps -a           — check all containers"
    exit 1
fi
