"""Structured JSONL logging and human-readable transcript for agent runs.

trace-harness-v1: observability additions only. Every upstream field and
transcript line is preserved byte-for-byte; new keys are added alongside.
See TRACE_SCHEMA.md for the field-by-field contract.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone

from agent_harness.trace import (  # trace-harness-v1
    ArtifactStore, TRACE_SCHEMA_VERSION, redact, redact_obj, response_meta,
)

_stdout_logger = logging.getLogger("smdd_agent")

# trace-harness-v1: upstream's preview threshold, kept as the preview size so
# the official `output_truncated` field is unchanged. The full payload now also
# goes to an artifact, so this is a preview rather than the only record.
_PREVIEW_LIMIT = 2000
_PREVIEW_HALF = 1000


class AgentLogger:
    def __init__(self, output_dir, task_id):
        os.makedirs(output_dir, exist_ok=True)
        self.trajectory_path = os.path.join(output_dir, "trajectory.jsonl")
        self.transcript_path = os.path.join(output_dir, "transcript.md")
        self.output_dir = output_dir                      # trace-harness-v1
        self.artifacts = ArtifactStore(output_dir)        # trace-harness-v1
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cache_read_tokens = 0
        self.total_cache_creation_tokens = 0
        self.boltz_calls = 0
        self.admet_calls = 0
        self.refusals = 0
        self._start_time = time.time()

        # Initialize trajectory with task id
        # trace-harness-v1: schema version added so a consumer can tell an
        # enhanced trace from an upstream one without guessing.
        self._write_event({
            "event": "task_start",
            "task_id": task_id,
            "trace_schema_version": TRACE_SCHEMA_VERSION,
        })

        # Initialize transcript
        with open(self.transcript_path, "w") as f:
            f.write(f"# Agent Transcript — {task_id}\n\nStarted: {datetime.now(timezone.utc).isoformat()}\n\n")

    def _write_event(self, event):
        event["timestamp"] = datetime.now(timezone.utc).isoformat()
        with open(self.trajectory_path, "a") as f:
            f.write(json.dumps(event, default=str) + "\n")
        _stdout_logger.info(json.dumps(event, default=str))

    def _extract_cached_tokens(self, usage):
        """Extract cache read and creation tokens from the usage object.

        Handles both OpenAI format (input_tokens_details.cached_tokens) and
        Anthropic format (cache_read_input_tokens / cache_creation_input_tokens).
        """
        cache_read = 0
        cache_creation = 0
        if not usage:
            return cache_read, cache_creation

        # Anthropic format
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0

        # OpenAI format: usage.input_tokens_details.cached_tokens
        if cache_read == 0:
            details = getattr(usage, "input_tokens_details", None)
            if details:
                cache_read = getattr(details, "cached_tokens", 0) or 0

        return cache_read, cache_creation

    def log_user_message(self, turn, content):
        self._write_event({
            "event": "user_message",
            "turn": turn,
            "content": content,
        })
        with open(self.transcript_path, "a") as f:
            f.write(f"**User:** {content}\n\n")

    def log_system_prompt(self, system_prompt):
        self._write_event({
            "event": "system_prompt",
            "content": system_prompt,
        })
        with open(self.transcript_path, "a") as f:
            f.write(f"## System Prompt\n\n{system_prompt}\n\n---\n\n")

    def log_llm_call(self, turn, response, wall_time_s=None):
        # trace-harness-v1: wall_time_s is an optional keyword, so an unpatched
        # caller (upstream agent_loop) still works unchanged.
        usage = response.usage
        input_tokens = usage.input_tokens if usage else 0
        output_tokens = usage.output_tokens if usage else 0
        cache_read, cache_creation = self._extract_cached_tokens(usage)
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cache_read_tokens += cache_read
        self.total_cache_creation_tokens += cache_creation

        tool_call_names = []
        assistant_text = ""
        reasoning_text = ""
        for item in response.output:
            if item.type == "function_call":
                tool_call_names.append(item.name)
            elif item.type == "reasoning":
                # litellm normalizes reasoning across providers inconsistently: some models
                # populate `summary` (blocks), some `content` (blocks or a raw string), some both.
                for block in (getattr(item, "summary", None) or []):
                    if getattr(block, "text", None):
                        reasoning_text += block.text
                content = getattr(item, "content", None)
                if isinstance(content, str):
                    reasoning_text += content
                elif content:
                    for block in content:
                        if getattr(block, "text", None):
                            reasoning_text += block.text
            elif item.type == "message":
                for content_block in item.content:
                    if content_block.type == "output_text" and content_block.text:
                        assistant_text += content_block.text

        event = {
            "event": "llm_call",
            "turn": turn,
            "model": response.model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_tokens": cache_read,
            "cache_creation_tokens": cache_creation,
            "tool_calls": tool_call_names,
            "assistant_text": assistant_text,
        }
        if reasoning_text:
            event["reasoning_content"] = reasoning_text

        # ---- trace-harness-v1 additions ------------------------------------
        # Upstream records model + token counts but not latency, response id,
        # or finish reason, so a truncated / filtered / retried response is
        # indistinguishable from a normal one after the fact.
        if wall_time_s is not None:
            event["wall_time_s"] = round(wall_time_s, 3)
        event.update(response_meta(response))     # may include _unavailable
        # Full response object, for anything this schema does not model.
        try:
            dumped = response.model_dump() if hasattr(response, "model_dump") else None
        except Exception:
            dumped = None
        if dumped is not None:
            desc = self.artifacts.put(
                json.dumps(redact_obj(dumped), default=str, sort_keys=True),
                kind="llm-response", ext="json")
            if desc:
                event["response_full"] = desc
        # --------------------------------------------------------------------
        self._write_event(event)

        # Transcript
        with open(self.transcript_path, "a") as f:
            f.write(f"## Turn {turn}\n\n")
            if reasoning_text:
                f.write(f"**Reasoning:** {reasoning_text}\n\n")
            if assistant_text:
                f.write(f"**Assistant:** {assistant_text}\n\n")

    def log_tool_call(self, turn, tool_name, tool_input, result, duration_s, extra=None):
        result_str = str(result)
        event = {
            "event": "tool_call",
            "turn": turn,
            "tool": tool_name,
            "input": tool_input,
            "output_truncated": (result_str[:_PREVIEW_HALF] + "\n\n... [middle truncated] ...\n\n" + result_str[-_PREVIEW_HALF:]) if len(result_str) > _PREVIEW_LIMIT else result_str,
            "duration_s": round(duration_s, 2),
        }
        if extra:
            event.update(extra)

        # ---- trace-harness-v1 additions ------------------------------------
        # Upstream keeps only the preview above, which loses the middle of any
        # output over 2000 chars — exactly the part needed to diagnose a failed
        # Boltz run or a long stack trace. Store the full payload as an
        # artifact and reference it here.
        event["output_is_truncated_preview"] = len(result_str) > _PREVIEW_LIMIT
        event["output_chars"] = len(result_str)
        desc = self.artifacts.put(result_str, kind=f"tool-{tool_name}-out")
        if desc:
            event["output_full"] = desc            # path + sha256 + bytes
        # Full input too: `input` above is the live dict, but a large `code` or
        # `command` value is worth having content-addressed and hash-verified.
        try:
            input_json = json.dumps(redact_obj(tool_input), default=str, sort_keys=True)
        except Exception:
            input_json = str(tool_input)
        in_desc = self.artifacts.put(input_json, kind=f"tool-{tool_name}-in", ext="json")
        if in_desc:
            event["input_full"] = in_desc
        # --------------------------------------------------------------------
        self._write_event(event)

        # Transcript
        reasoning = tool_input.get("reasoning", "")
        display_input = {k: v for k, v in tool_input.items() if k != "reasoning"}
        with open(self.transcript_path, "a") as f:
            f.write(f"**Tool Call:** {tool_name}\n")
            if reasoning:
                f.write(f"> **Reasoning:** {reasoning}\n\n")
            if tool_name == "python":
                f.write(f"```python\n{display_input.get('code', '')}\n```\n")
            elif tool_name == "bash":
                f.write(f"```bash\n{display_input.get('command', '')}\n```\n")
            else:
                f.write(f"```json\n{json.dumps(display_input, indent=4, default=str)}\n```\n")
            result_str = str(result)
            if len(result_str) > 2000:
                result_str = result_str[:1000] + "\n\n... [middle truncated] ...\n\n" + result_str[-1000:]
            f.write(f"**Result:**\n```\n{result_str}\n```\n\n")

    def log_refusal(self, turn):
        self.refusals += 1
        self._write_event({"event": "refusal", "turn": turn, "total_refusals": self.refusals})

    def log_submit(self, turn, file_path, content_preview=""):
        event = {
            "event": "submit",
            "turn": turn,
            "file": file_path,
            "content": content_preview[:1000],
        }
        # trace-harness-v1: upstream keeps only the first 1000 chars of the
        # submitted content. The submission is the graded artifact, so the full
        # text is stored and hashed.
        event["content_chars"] = len(content_preview)
        event["content_is_truncated_preview"] = len(content_preview) > 1000
        desc = self.artifacts.put(content_preview, kind="submit-content")
        if desc:
            event["content_full"] = desc
        self._write_event(event)
        with open(self.transcript_path, "a") as f:
            f.write(f"**Submitted:** `{file_path}`\n\n")

    def log_memory(self, turn, action, payload=None):
        """Record harness-only memory activity without changing the trace contract."""
        event = {"event": f"memory_{action}", "turn": turn}
        if payload:
            event.update(payload)
        self._write_event(event)

    def log_summary(self, status, total_turns):
        wall_time = time.time() - self._start_time
        summary = {
            "event": "summary",
            "status": status,
            "total_turns": total_turns,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cache_read_tokens": self.total_cache_read_tokens,
            "total_cache_creation_tokens": self.total_cache_creation_tokens,
            "boltz_calls": self.boltz_calls,
            "admet_calls": self.admet_calls,
            "wall_time_s": round(wall_time, 2),
        }
        self._write_event(summary)

        with open(self.transcript_path, "a") as f:
            f.write(f"\n---\n## Summary\n\n")
            f.write(f"- Status: {status}\n")
            f.write(f"- Turns: {total_turns}\n")
            f.write(f"- Input tokens: {self.total_input_tokens}\n")
            f.write(f"- Output tokens: {self.total_output_tokens}\n")
            f.write(f"- Cache read tokens: {self.total_cache_read_tokens}\n")
            f.write(f"- Cache creation tokens: {self.total_cache_creation_tokens}\n")
            f.write(f"- Boltz calls: {self.boltz_calls}\n")
            f.write(f"- ADMET calls: {self.admet_calls}\n")
            f.write(f"- Refusals: {self.refusals}\n")
            f.write(f"- Wall time: {wall_time:.1f}s\n")

        return summary
