"""Trace enhancement layer for SMDD-Bench (observability only).

ADDED BY trace-harness-v1. Not part of upstream @ 359ef1d7.

Design constraint: this module must NOT influence agent behaviour. It holds no
decision logic — no prompt text, no tool schema, no retry/budget/termination
rules. It only records what already happened. Everything here is called AFTER
the decision it observes has been made.

What it provides:
  * ArtifactStore  — content-addressed storage for full tool outputs, so the
    official 2000-char preview stops being the only record.
  * write_manifest — one-shot run provenance file.
  * redact         — strips secrets before anything is written.

Upstream's own fields are never removed; this layer only adds keys alongside
them (see TRACE_SCHEMA.md).
"""

import hashlib
import json
import os
import re
from datetime import datetime, timezone

TRACE_SCHEMA_VERSION = "trace-harness-v1"

# --------------------------------------------------------------------------
# Secret redaction
# --------------------------------------------------------------------------
# Applied to every string this layer writes. The official logger already
# avoids dumping env vars, but the enhancement layer captures FULL tool output
# and full request metadata, so it has a wider blast radius and needs its own
# scrubbing. Patterns are deliberately broad: a false positive costs a masked
# token in a log, a false negative leaks a credential.
_SECRET_PATTERNS = [
    (re.compile(r"(sk-[A-Za-z0-9_\-]{16,})"), "sk-***REDACTED***"),
    (re.compile(r"(sk-ant-[A-Za-z0-9_\-]{16,})"), "sk-ant-***REDACTED***"),
    (re.compile(r"(?i)\b(authorization)\s*[:=]\s*\S+"), r"\1: ***REDACTED***"),
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._\-]{8,}"), r"\1 ***REDACTED***"),
    (re.compile(r"(?i)\b([A-Z0-9_]*api[_-]?key)\s*[:=]\s*\S+"), r"\1=***REDACTED***"),
    (re.compile(r"(?i)\b([A-Z0-9_]*secret[A-Z0-9_]*)\s*[:=]\s*\S+"), r"\1=***REDACTED***"),
    (re.compile(r"(?i)\b([A-Z0-9_]*token)\s*[:=]\s*\S+"), r"\1=***REDACTED***"),
    (re.compile(r"(?i)\b(AZURE_[A-Z_]*KEY)\s*[:=]\s*\S+"), r"\1=***REDACTED***"),
    (re.compile(r"(AKIA[0-9A-Z]{16})"), "***REDACTED_AWS_KEY***"),
]

# Config keys whose VALUE must never be written, whatever it looks like.
_SENSITIVE_KEYS = {
    "api_key", "apikey", "authorization", "auth", "token", "secret",
    "password", "passwd", "aws_secret_access_key", "aws_access_key_id",
    "azure_api_key", "openai_api_key", "anthropic_api_key",
}


def redact(text):
    """Mask anything that looks like a credential. Returns a str."""
    if text is None:
        return None
    if not isinstance(text, str):
        text = str(text)
    for pattern, repl in _SECRET_PATTERNS:
        text = pattern.sub(repl, text)
    return text


def redact_obj(obj):
    """Recursively redact a JSON-ish structure, by key name and by value shape."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and k.lower().replace("-", "_") in _SENSITIVE_KEYS:
                out[k] = "***REDACTED***"
            else:
                out[k] = redact_obj(v)
        return out
    if isinstance(obj, (list, tuple)):
        return [redact_obj(x) for x in obj]
    if isinstance(obj, str):
        return redact(obj)
    return obj


# --------------------------------------------------------------------------
# Artifact store
# --------------------------------------------------------------------------

class ArtifactStore:
    """Writes full payloads to disk and returns a descriptor for the JSONL.

    Content-addressed by SHA-256, so a repeated identical output is stored once
    and both events point at the same file. The JSONL keeps the descriptor
    (path + hash + byte count), never the payload itself, which keeps
    trajectory.jsonl streamable while making the full text recoverable.
    """

    def __init__(self, output_dir, subdir="artifacts"):
        self.root = os.path.join(output_dir, subdir)
        self.subdir = subdir
        os.makedirs(self.root, exist_ok=True)

    def put(self, payload, kind="tool_output", ext="txt"):
        """Store payload; return a descriptor dict (never the payload).

        Returns None for empty payloads so callers can skip the key entirely.
        """
        if payload is None:
            return None
        if not isinstance(payload, str):
            payload = str(payload)
        clean = redact(payload)
        raw = clean.encode("utf-8", errors="replace")
        digest = hashlib.sha256(raw).hexdigest()
        name = f"{kind}-{digest[:16]}.{ext}"
        path = os.path.join(self.root, name)
        if not os.path.exists(path):          # content-addressed: write once
            tmp = path + ".part"
            with open(tmp, "wb") as f:
                f.write(raw)
            os.replace(tmp, path)             # atomic; no partial artifact
        return {
            "artifact_path": f"{self.subdir}/{name}",   # relative to output_dir
            "sha256": digest,
            "bytes": len(raw),
            "redacted": clean != payload,
        }


# --------------------------------------------------------------------------
# LLM response introspection
# --------------------------------------------------------------------------

def response_meta(response):
    """Pull provenance fields off a LiteLLM response, defensively.

    Providers disagree on what they expose and litellm normalises only some of
    it, so every field is optional and absence is recorded explicitly rather
    than guessed. `_unavailable` lists what this provider did not supply.
    """
    meta = {}
    missing = []

    for key, attr in (("response_id", "id"),
                      ("actual_model", "model"),
                      ("created_at_provider", "created"),
                      ("service_tier", "service_tier")):
        val = getattr(response, attr, None)
        if val is None:
            missing.append(key)
        else:
            meta[key] = val

    # finish_reason lives in different places across APIs
    finish = None
    choices = getattr(response, "choices", None)
    if choices:
        finish = getattr(choices[0], "finish_reason", None)
    if finish is None:
        # trace-harness-v1.2: _FakeResponse exposes it directly (completions path)
        finish = getattr(response, "finish_reason", None)
    if finish is None:
        finish = getattr(response, "status", None)       # Responses API
    if finish is None:
        for item in (getattr(response, "output", None) or []):
            if getattr(item, "type", None) == "message":
                finish = getattr(item, "status", None)
                if finish:
                    break
    if finish is None:
        missing.append("finish_reason")
    else:
        meta["finish_reason"] = finish

    usage = getattr(response, "usage", None)
    if usage is not None:
        u = {}
        for attr in ("input_tokens", "output_tokens", "total_tokens",
                     "prompt_tokens", "completion_tokens",
                     "cache_read_input_tokens", "cache_creation_input_tokens",
                     "reasoning_tokens"):
            v = getattr(usage, attr, None)
            if v is not None:
                u[attr] = v
        details = getattr(usage, "input_tokens_details", None)
        if details is not None:
            cached = getattr(details, "cached_tokens", None)
            if cached is not None:
                u["cached_tokens"] = cached
        out_details = getattr(usage, "output_tokens_details", None)
        if out_details is not None:
            rt = getattr(out_details, "reasoning_tokens", None)
            if rt is not None:
                u["reasoning_tokens"] = rt
        if u:
            meta["usage_detail"] = u
    else:
        missing.append("usage_detail")

    # LiteLLM does not surface how many internal retries num_retries=25 consumed.
    # Recorded as an explicit unknown rather than assumed to be zero.
    meta["litellm_internal_retries"] = "unavailable"

    if missing:
        meta["_unavailable"] = missing
    return meta


# --------------------------------------------------------------------------
# Run manifest
# --------------------------------------------------------------------------

def write_manifest(output_dir, task_id, config, extra=None):
    """Write run_manifest.json capturing provenance for this run."""
    from dataclasses import asdict, is_dataclass

    cfg = asdict(config) if is_dataclass(config) else dict(vars(config))
    manifest = {
        "trace_schema_version": TRACE_SCHEMA_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "task_id": task_id,
        "model": cfg.get("model"),
        "agent_config": redact_obj(cfg),
        "repo_sha": os.environ.get("SMDD_REPO_SHA", "unset"),
        "agent_image_id": os.environ.get("SMDD_AGENT_IMAGE_ID", "unset"),
        "evaluator_image_id": os.environ.get("SMDD_EVALUATOR_IMAGE_ID", "unset"),
        "harness_variant": "trace-harness-v1",
    }
    if extra:
        manifest.update(redact_obj(extra))
    path = os.path.join(output_dir, "run_manifest.json")
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2, default=str, sort_keys=True)
    return path
