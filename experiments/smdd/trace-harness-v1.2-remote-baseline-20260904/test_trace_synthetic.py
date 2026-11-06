#!/usr/bin/env python3
"""Synthetic test for trace-harness-v1. Makes NO network calls.

Feeds the patched AgentLogger a dummy response object and a tool output well
over the 2000-char preview limit, then asserts the enhanced trace is complete
and the official fields survived.

Run:  PYTHONPATH=<runtime>:<trace-harness-v1> python3 test_trace_synthetic.py
"""

import hashlib
import json
import os
import shutil
import sys
import tempfile

# Guard: fail loudly if anything tries to open a socket during this test.
import socket


class _NetworkBlocked(RuntimeError):
    pass


_real_socket = socket.socket


def _blocked(*a, **k):
    raise _NetworkBlocked("synthetic test attempted a network connection")


socket.socket = _blocked
socket.create_connection = _blocked

from agent_harness.logger import AgentLogger          # noqa: E402
from agent_harness.trace import (                     # noqa: E402
    TRACE_SCHEMA_VERSION, redact, redact_obj, write_manifest,
)
from agent_harness.config import AgentConfig          # noqa: E402

FAILS = []
PASSES = []


def check(name, cond, detail=""):
    (PASSES if cond else FAILS).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


# --------------------------------------------------------------------------
# Synthetic dummy response objects (no provider, no network)
# --------------------------------------------------------------------------

class DummyUsage:
    input_tokens = 1234
    output_tokens = 567
    total_tokens = 1801
    cache_read_input_tokens = 800
    cache_creation_input_tokens = 120


class DummyBlock:
    type = "output_text"

    def __init__(self, text):
        self.text = text


class DummyMessage:
    type = "message"
    status = "completed"

    def __init__(self, text):
        self.content = [DummyBlock(text)]


class DummyFunctionCall:
    type = "function_call"

    def __init__(self, name):
        self.name = name


class DummyResponse:
    """Shaped like a litellm Responses-API object, built entirely offline."""
    id = "resp_synthetic_0001"
    model = "azure/gpt-5.4"
    created = 1780000000
    status = "completed"
    usage = DummyUsage()

    def __init__(self):
        self.output = [DummyMessage("synthetic assistant text"),
                       DummyFunctionCall("python")]

    def model_dump(self):
        return {"id": self.id, "model": self.model, "status": self.status,
                "output": [{"type": "message", "text": "synthetic assistant text"},
                           {"type": "function_call", "name": "python"}],
                "usage": {"input_tokens": 1234, "output_tokens": 567},
                # deliberately planted secrets — must be redacted on write
                "api_key": "REPLACE_WITH_API_KEY",
                "headers": {"Authorization": "Bearer abcdef1234567890"}}


def main():
    tmp = tempfile.mkdtemp(prefix="trace_test_")
    print(f"输出目录: {tmp}\n")
    try:
        lg = AgentLogger(tmp, "smdd_synthetic_test")

        print("=== 1. 超过 2000 字符的工具输出 ===")
        # 12000 chars with a unique marker in the MIDDLE — the exact region
        # upstream's preview discards.
        big = ("HEAD" + "A" * 5000 + "MIDDLE_MARKER_XYZZY" + "B" * 5000 + "TAIL")
        marker_in_middle = "MIDDLE_MARKER_XYZZY"
        print(f"  合成输出长度: {len(big)} 字符")
        lg.log_tool_call(1, "python", {"code": "print('hi')", "reasoning": "test"},
                         big, 1.234)

        print("\n=== 2. LLM 调用（合成 response，无真实请求）===")
        lg.log_llm_call(2, DummyResponse(), wall_time_s=3.14159)

        print("\n=== 3. submit 事件 ===")
        lg.log_submit(3, "output.smi", "C" * 4000)

        print("\n=== 4. summary ===")
        lg.log_summary("submitted", 3)

        print("\n=== 5. run manifest ===")
        os.environ["SMDD_REPO_SHA"] = "359ef1d7c042b85fc1c544662b4fd6fb381f346f"
        os.environ["SMDD_AGENT_IMAGE_ID"] = "sha256:856965e37f2f"
        write_manifest(tmp, "smdd_synthetic_test", AgentConfig(),
                       extra={"container_id": "deadbeef", "api_key": "sk-leak-me"})

        # ------------------------------------------------------------------
        print("\n=== 校验 ===")
        traj = os.path.join(tmp, "trajectory.jsonl")
        lines = [l for l in open(traj, encoding="utf-8").read().splitlines() if l.strip()]
        events = []
        parse_ok = True
        for i, line in enumerate(lines, 1):
            try:
                events.append(json.loads(line))
            except Exception as e:
                parse_ok = False
                print(f"    第 {i} 行解析失败: {e}")
        check("JSONL 每行均可解析", parse_ok, f"{len(events)} 个事件")

        by = {}
        for e in events:
            by.setdefault(e["event"], []).append(e)
        check("事件类型齐全",
              all(k in by for k in ("task_start", "tool_call", "llm_call", "submit", "summary")),
              ",".join(sorted(by)))

        # ---- official fields preserved ----
        tc = by["tool_call"][0]
        for f in ("event", "turn", "tool", "input", "output_truncated", "duration_s"):
            check(f"官方字段保留 tool_call.{f}", f in tc)
        lc = by["llm_call"][0]
        for f in ("event", "turn", "model", "input_tokens", "output_tokens",
                  "cache_read_tokens", "cache_creation_tokens", "tool_calls", "assistant_text"):
            check(f"官方字段保留 llm_call.{f}", f in lc)
        sm = by["summary"][0]
        for f in ("status", "total_turns", "total_input_tokens", "total_output_tokens",
                  "boltz_calls", "admet_calls", "wall_time_s"):
            check(f"官方字段保留 summary.{f}", f in sm)
        check("官方 truncation 行为不变（预览仍被截断）",
              tc["output_truncated"] != big and "[middle truncated]" in tc["output_truncated"],
              f"预览 {len(tc['output_truncated'])} 字符")

        # ---- enhancement: full output recoverable ----
        check("新增 output_full 描述符", "output_full" in tc)
        desc = tc.get("output_full", {})
        art = os.path.join(tmp, desc.get("artifact_path", "___missing"))
        check("artifact 文件存在", os.path.isfile(art), desc.get("artifact_path", ""))
        recovered = open(art, encoding="utf-8").read() if os.path.isfile(art) else ""
        check("完整输出可恢复（与原文逐字符相同）", recovered == big,
              f"{len(recovered)} vs {len(big)} 字符")
        check("被官方预览丢弃的中段内容已保住", marker_in_middle in recovered
              and marker_in_middle not in tc["output_truncated"])
        actual_sha = hashlib.sha256(recovered.encode("utf-8")).hexdigest()
        check("SHA-256 与原文一致", actual_sha == desc.get("sha256"),
              f"{actual_sha[:16]}...")
        check("bytes 字段与实际一致",
              desc.get("bytes") == len(recovered.encode("utf-8")))
        check("output_is_truncated_preview 标记正确",
              tc.get("output_is_truncated_preview") is True)
        check("新增 input_full 描述符", "input_full" in tc)

        # ---- enhancement: llm metadata ----
        check("新增 wall_time_s", lc.get("wall_time_s") == 3.142, str(lc.get("wall_time_s")))
        check("新增 response_id", lc.get("response_id") == "resp_synthetic_0001")
        check("新增 actual_model", lc.get("actual_model") == "azure/gpt-5.4")
        check("新增 finish_reason", lc.get("finish_reason") == "completed")
        check("新增 usage_detail", isinstance(lc.get("usage_detail"), dict),
              json.dumps(lc.get("usage_detail", {}), sort_keys=True)[:70])
        check("LiteLLM 内部重试标为 unavailable（不猜测）",
              lc.get("litellm_internal_retries") == "unavailable")
        check("trace schema 版本已记录",
              by["task_start"][0].get("trace_schema_version") == TRACE_SCHEMA_VERSION)

        # ---- enhancement: submit full ----
        sub = by["submit"][0]
        check("submit 保留官方 content 字段（1000 预览）",
              "content" in sub and len(sub["content"]) == 1000)
        check("submit 新增 content_full", "content_full" in sub)
        sart = os.path.join(tmp, sub.get("content_full", {}).get("artifact_path", "___x"))
        check("submit 完整内容可恢复",
              os.path.isfile(sart) and len(open(sart, encoding="utf-8").read()) == 4000)

        # ---- secret hygiene ----
        whole = open(traj, encoding="utf-8").read()
        mani_txt = open(os.path.join(tmp, "run_manifest.json"), encoding="utf-8").read()
        art_all = ""
        for root, _, files in os.walk(os.path.join(tmp, "artifacts")):
            for fn in files:
                art_all += open(os.path.join(root, fn), encoding="utf-8", errors="replace").read()
        combined = whole + mani_txt + art_all
        check("未写入 sk- 明文密钥", "REPLACE_WITH_API_KEY" not in combined)
        check("未写入 sk-leak-me", "sk-leak-me" not in combined)
        check("未写入 Bearer 明文 token", "Bearer abcdef1234567890" not in combined)
        check("redact() 对 sk- 生效",
              "REPLACE_WITH_API_KEY" not in redact("key=REPLACE_WITH_API_KEY"))
        check("redact_obj 按键名屏蔽",
              redact_obj({"api_key": "whatever-plain-value"})["api_key"] == "***REDACTED***")

        # ---- manifest ----
        mani = json.loads(mani_txt)
        for f in ("trace_schema_version", "created_utc", "task_id", "model",
                  "agent_config", "repo_sha", "agent_image_id"):
            check(f"manifest 字段 {f}", f in mani)
        check("manifest 记录仓库 SHA",
              mani.get("repo_sha") == "359ef1d7c042b85fc1c544662b4fd6fb381f346f")
        check("manifest 含完整 AgentConfig",
              isinstance(mani.get("agent_config"), dict)
              and mani["agent_config"].get("max_turns") == 100
              and mani["agent_config"].get("boltz_budget") == 8)
        check("manifest 中敏感 extra 已屏蔽",
              mani.get("api_key") == "***REDACTED***")

        # ---- transcript ----
        tr = open(os.path.join(tmp, "transcript.md"), encoding="utf-8").read()
        check("transcript.md 已生成且含官方结构",
              "# Agent Transcript" in tr and "## Summary" in tr and "**Tool Call:**" in tr)

        # ---- no network ----
        check("测试期间未发生真实网络请求", socket.socket is _blocked)

        print(f"\n=== 结果: {len(PASSES)} PASS / {len(FAILS)} FAIL ===")
        if FAILS:
            for f in FAILS:
                print(f"  未通过: {f}")
            return 1
        print("  全部通过。")
        return 0
    finally:
        socket.socket = _real_socket
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
