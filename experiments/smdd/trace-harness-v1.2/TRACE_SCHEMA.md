# TRACE_SCHEMA.md — trace-harness-v1

Trace schema for the SMDD-Bench agent harness enhancement layer.

- **Base**: SMDD-Bench @ `359ef1d7c042b85fc1c544662b4fd6fb381f346f`
- **Schema version string**: `trace-harness-v1` (emitted in `task_start.trace_schema_version` and `run_manifest.json`)
- **Scope**: observability only. No agent decision input is altered.

---

## 1. Compatibility contract

Every field upstream writes is still written, with the same name, same type, and
the same value it would have had upstream. Enhancements are **new keys added
alongside**. A consumer written against the official schema keeps working
unmodified.

`output_truncated` deserves explicit mention: it is still truncated at 2000
chars with the same `... [middle truncated] ...` marker. It was left alone on
purpose — changing it would break the official contract. The full payload is now
*also* available via `output_full`, so the preview is no longer the only record.

## 2. Files produced per task run

| File | Origin | Content |
|---|---|---|
| `trajectory.jsonl` | upstream + additions | one JSON object per line, one per event |
| `transcript.md` | upstream, unchanged | human-readable transcript |
| `run_manifest.json` | **new** | run provenance, written before the loop starts |
| `artifacts/` | **new** | content-addressed full payloads |

Artifacts are named `{kind}-{sha256[:16]}.{ext}` and content-addressed: an
identical payload logged twice is stored once and both events reference the same
file. `artifact_path` is always **relative to the run output dir**, so a results
tree stays portable.

## 3. Artifact descriptor

Wherever a full payload is stored, the JSONL carries a descriptor, never the
payload:

```json
{
  "artifact_path": "artifacts/tool-python-out-38275ba9a0af4d2c.txt",
  "sha256": "38275ba9a0af4d2c...",
  "bytes": 10027,
  "redacted": false
}
```

`redacted` is `true` if secret-scrubbing altered the payload before writing —
so a hash mismatch against a known original is explainable rather than alarming.

## 4. Event-by-event fields

### `task_start`

| Field | Origin | Notes |
|---|---|---|
| `event`, `task_id`, `timestamp` | upstream | |
| `trace_schema_version` | **new** | tells a consumer this is an enhanced trace |

### `tool_call` — the main gap upstream

| Field | Origin | Notes |
|---|---|---|
| `event`, `turn`, `tool`, `input`, `duration_s` | upstream | unchanged |
| `output_truncated` | upstream | **still 2000-char preview**, unchanged |
| `output_full` | **new** | descriptor for the complete output |
| `output_chars` | **new** | full character count |
| `output_is_truncated_preview` | **new** | `true` if the preview lost content |
| `input_full` | **new** | descriptor for the full input (redacted JSON) |
| `boltz_calls` / `admet_calls` / `budget_exceeded` | upstream `extra` | passed through untouched |

Why this matters: a failed Boltz run or a long Python traceback is typically
several thousand characters, and the diagnostic detail sits in the middle — the
exact region the official preview drops. The synthetic test asserts recovery of
a marker planted mid-payload.

### `llm_call`

| Field | Origin | Notes |
|---|---|---|
| `event`, `turn`, `model`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `tool_calls`, `assistant_text` | upstream | unchanged |
| `reasoning_content` | upstream | unchanged, still only when non-empty |
| `wall_time_s` | **new** | measured around the call site only |
| `response_id` | **new** | provider response ID when exposed |
| `actual_model` | **new** | model the provider actually served |
| `finish_reason` | **new** | resolved across Responses/Completions shapes |
| `created_at_provider`, `service_tier` | **new** | when exposed |
| `usage_detail` | **new** | full usage incl. reasoning/cached token breakdown |
| `response_full` | **new** | descriptor for the full dumped response |
| `litellm_internal_retries` | **new** | always the string `"unavailable"` — see §6 |
| `_unavailable` | **new** | list of fields this provider did not supply |

`_unavailable` exists so a missing field is distinguishable from a field that
was never checked. Absence is recorded, not guessed.

### `submit`

| Field | Origin | Notes |
|---|---|---|
| `event`, `turn`, `file`, `content` | upstream | `content` still capped at 1000 chars |
| `content_full` | **new** | descriptor for the complete submitted text |
| `content_chars`, `content_is_truncated_preview` | **new** | |

The submission is the graded artifact, so truncating it to 1000 chars loses the
thing being scored.

### `refusal`, `user_message`, `system_prompt`, `summary`

Unchanged from upstream. No fields added or removed.

## 5. `run_manifest.json`

| Field | Source |
|---|---|
| `trace_schema_version` | constant `trace-harness-v1` |
| `created_utc` | ISO-8601 UTC at manifest write |
| `task_id` | task YAML `id` |
| `model` | `AgentConfig.model` |
| `agent_config` | full `AgentConfig` as a dict, redacted |
| `repo_sha` | env `SMDD_REPO_SHA` |
| `agent_image_id` | env `SMDD_AGENT_IMAGE_ID` |
| `evaluator_image_id` | env `SMDD_EVALUATOR_IMAGE_ID` |
| `harness_variant` | constant `trace-harness-v1` |
| `container_id`, `task_dir` | passed by `run_agent` |

Image IDs and repo SHA come from the environment rather than being probed, so
the manifest never shells out to docker/git mid-run. Unset values record the
literal string `unset` rather than silently omitting the key.

## 6. Known limits, recorded rather than guessed

**LiteLLM internal retries are not observable.** `call_llm` passes
`num_retries=25`; LiteLLM retries internally and returns only the final
response, exposing no attempt counter on the response object. `wall_time_s`
therefore covers *all* internal attempts, and a long value may mean one slow
call or several retried ones. `litellm_internal_retries` is hardcoded to
`"unavailable"` — never inferred from latency.

**Provider field coverage varies.** `response_id`, `finish_reason`,
`service_tier` and the usage sub-fields depend on the provider. Whatever is
missing is listed in `_unavailable`.

**Redaction is deliberately over-broad.** Patterns match `sk-*`, `sk-ant-*`,
`Authorization:`, `Bearer <tok>`, `*api_key*`, `*secret*`, `*token*`,
`AZURE_*KEY`, and AWS `AKIA*`. Keys named `api_key`, `token`, `secret`,
`password`, etc. are masked by name regardless of value shape. A masked
non-secret is an acceptable cost; a leaked credential is not. `.env` contents
are never read or logged by this layer.

## 7. Behavioural neutrality

Byte-identical to upstream (verified by SHA-256): `config.py`, `network.py`,
`obfuscate.py`, `prompts.py`, `tools.py`, `run.py`, `__init__.py`.

`prompts.py` and `tools.py` are the two that matter most — they hold the system
prompt, the tool schemas, and tool execution. Neither is touched.

Total diff: `logger.py` +83/−7, `agent_loop.py` +11/−2, plus new `trace.py`.

The `agent_loop.py` change is three things only: import `write_manifest`, take
`time.time()` before each LLM call, and pass the elapsed time to
`log_llm_call`. Unchanged: system prompt construction, `TOOL_SCHEMAS`, tool
dispatch order, model request parameters, `num_retries=25`, token/turn/tool
budgets, submit detection, and every termination path.

`log_llm_call`'s new `wall_time_s` is an optional keyword argument, so the
patched logger still works when called by unpatched upstream code.

## 8. Verification

`test_trace_synthetic.py` — 60 assertions, 0 failures, no network access
(sockets are monkeypatched to raise for the duration). It covers: every JSONL
line parses; the full artifact is recoverable byte-for-byte; SHA-256 matches the
original; a marker planted in the middle of a 10027-char payload survives; all
official fields still present; planted `sk-` keys and `Bearer` tokens never
reach disk; manifest completeness.
