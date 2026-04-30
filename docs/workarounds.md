# Known issues and workarounds

---

## vLLM streaming tool calls — null function name

**Status:** Active workaround in place. Remove `llmproxy` once fixed upstream.

### Symptom

OpenCode (and any client using `@ai-sdk/openai-compatible`) raises:

```
Expected 'function.name' to be a string.
```

when the model tries to call a tool (e.g. reading a file, running glob).

### Root cause

The OpenAI SSE spec for streaming tool calls says follow-on argument chunks
should **omit** the `name` field entirely. vLLM instead sends it explicitly
as `null`:

```jsonc
// First chunk — correct, name is present
{"delta": {"tool_calls": [{"function": {"name": "read_file", "arguments": ""}}]}}

// Follow-on chunks — vLLM sends null instead of omitting the field
{"delta": {"tool_calls": [{"function": {"name": null, "arguments": "\"/tmp\""}}]}}
```

`@ai-sdk/openai-compatible` validates each chunk strictly and fails on `null`.

Non-streaming requests (`"stream": false`) are unaffected — vLLM correctly
omits the name there.

### Workaround: llmproxy shim

`bin/llmproxy` is a thin HTTP proxy that intercepts SSE streams and deletes
the `"name": null` field before forwarding to the client.

```
OpenCode :9000 → llmproxy → llama-swap :8080 → vLLM :910x
```

`~/.config/opencode/opencode.json` points to `:9000` (the proxy).

Managed via llmctl:

```bash
llmctl proxy-up       # start proxy on :9000
llmctl proxy-down     # stop proxy
llmctl proxy-status   # check state
```

PID file: `~/.local/share/llmstack/llmproxy.pid`
Log file: `~/.local/share/llmstack/llmproxy.log`

### Removing the workaround

When vLLM fixes the null serialisation (check release notes for "tool_call
streaming" or "SSE null name"), do the following:

1. `llmctl proxy-down`
2. In `~/.config/opencode/opencode.json`, change `baseURL` port from `8081`
   back to `8080`
3. The `bin/llmproxy` file and `proxy-*` llmctl commands can then be removed

### Upstream tracking

Search vLLM issues: `tool_call name null streaming`
Repo: https://github.com/vllm-project/vllm/issues
