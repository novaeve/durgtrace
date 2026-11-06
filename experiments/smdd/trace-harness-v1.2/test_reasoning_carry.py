#!/usr/bin/env python3
"""Unit test for trace-harness-v1.1: reasoning_content must survive the
responses->completions conversion. NO network access.

Run: PYTHONPATH=<runtime>:<v1.1> python3 test_reasoning_carry.py
"""
import socket
import sys

# Import BEFORE blocking sockets: agent_loop imports litellm -> httpx -> ssl,
# and ssl does `class SSLSocket(socket)`, which needs socket.socket to still be
# a class. Blocking first makes the import itself fail.
from agent_harness.agent_loop import _responses_input_to_messages  # noqa: E402


class _NetBlocked(RuntimeError):
    pass


class _BlockedSocket(socket.socket):
    """Subclass so any `class X(socket)` already executed stays valid, while
    every attempt to actually construct a socket raises."""

    def __init__(self, *a, **k):
        raise _NetBlocked("unit test attempted network access")


def _blocked_conn(*a, **k):
    raise _NetBlocked("unit test attempted network access")


_real_socket = socket.socket
_real_conn = socket.create_connection
socket.socket = _BlockedSocket
socket.create_connection = _blocked_conn

FAILS, PASSES = [], []


def check(name, cond, detail=""):
    (PASSES if cond else FAILS).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


SYS = "system prompt text"

# Shape produced by _FakeResponse._build_output for a thinking model that also
# emits a tool call (DeepSeek V4 / Kimi K2.5). reasoning.content is a raw str.
REASON_TEXT = "I should compute 2+2 using the python tool."
ITEMS_STR = [
    {"role": "user", "content": "compute 2+2"},
    {"type": "reasoning", "content": REASON_TEXT},
    {"type": "function_call", "name": "python", "arguments": '{"code":"print(2+2)"}',
     "call_id": "call_abc123"},
    {"type": "function_call_output", "call_id": "call_abc123", "output": "4\n"},
]


def assistants(msgs):
    return [m for m in msgs if m.get("role") == "assistant"]


print("=== 1. reasoning.content 为字符串（_FakeResponse 形态）===")
m = _responses_input_to_messages(ITEMS_STR, SYS)
a = assistants(m)
check("产生恰好一个 assistant message", len(a) == 1, f"{len(a)} 个")
check("assistant 含 tool_calls", bool(a and a[0].get("tool_calls")))
check("assistant 含 reasoning_content", bool(a and a[0].get("reasoning_content")))
check("reasoning_content 内容正确", a and a[0].get("reasoning_content") == REASON_TEXT,
      repr(a[0].get("reasoning_content"))[:60] if a else "")
check("reasoning 未被当作 unknown item 丢弃",
      a and "reasoning_content" in a[0])
check("tool_call id 保持不变", a and a[0]["tool_calls"][0]["id"] == "call_abc123")
check("tool_call 函数名保持不变", a and a[0]["tool_calls"][0]["function"]["name"] == "python")
check("tool 结果消息仍生成",
      any(x.get("role") == "tool" and x.get("tool_call_id") == "call_abc123" for x in m))

print("\n=== 2. reasoning 用 content blocks（Responses API 形态）===")
ITEMS_BLOCKS = [
    {"role": "user", "content": "hi"},
    {"type": "reasoning", "content": [{"type": "reasoning_text", "text": "block-A "},
                                      {"type": "reasoning_text", "text": "block-B"}]},
    {"type": "function_call", "name": "python", "arguments": "{}", "call_id": "c2"},
]
a2 = assistants(_responses_input_to_messages(ITEMS_BLOCKS, SYS))
check("content blocks 被拼接", a2 and a2[0].get("reasoning_content") == "block-A block-B",
      repr(a2[0].get("reasoning_content")) if a2 else "")

print("\n=== 3. reasoning 用 summary blocks ===")
ITEMS_SUMMARY = [
    {"role": "user", "content": "hi"},
    {"type": "reasoning", "summary": [{"type": "summary_text", "text": "sum-1"}]},
    {"type": "function_call", "name": "python", "arguments": "{}", "call_id": "c3"},
]
a3 = assistants(_responses_input_to_messages(ITEMS_SUMMARY, SYS))
check("summary blocks 被读取", a3 and a3[0].get("reasoning_content") == "sum-1")

print("\n=== 4. 回归：无 reasoning 时行为与 v1 完全一致 ===")
ITEMS_NO_REASON = [
    {"role": "user", "content": "hi"},
    {"type": "message", "content": [{"type": "output_text", "text": "hello there"}]},
    {"type": "function_call", "name": "submit", "arguments": '{"file_path":"a.py"}',
     "call_id": "c4"},
]
a4 = assistants(_responses_input_to_messages(ITEMS_NO_REASON, SYS))
check("无 reasoning 时不注入该键", a4 and "reasoning_content" not in a4[0],
      sorted(a4[0].keys()) if a4 else "")
check("assistant content 仍正确", a4 and a4[0].get("content") == "hello there")
check("tool_calls 仍正确", a4 and a4[0]["tool_calls"][0]["function"]["name"] == "submit")

print("\n=== 5. 回归：system 与 cache_control 未受影响 ===")
check("首条为 system", m[0]["role"] == "system")
check("system 带 cache_control", m[0].get("cache_control") == {"type": "ephemeral"})
last_ut = [x for x in m if x["role"] in ("user", "tool")]
check("最后一条 user/tool 带 cache_control 断点",
      last_ut and last_ut[-1].get("cache_control") == {"type": "ephemeral"})

print("\n=== 6. 未知 item 仍被安全跳过（不死循环）===")
ITEMS_UNKNOWN = [
    {"role": "user", "content": "hi"},
    {"type": "some_future_type", "data": 1},
    {"type": "function_call", "name": "python", "arguments": "{}", "call_id": "c5"},
]
try:
    m6 = _responses_input_to_messages(ITEMS_UNKNOWN, SYS)
    check("未知类型被跳过且不挂起", True, f"{len(m6)} 条消息")
except Exception as e:
    check("未知类型被跳过且不挂起", False, f"{type(e).__name__}: {e}")

print("\n=== 7. 无网络访问 ===")
check("socket 已被拦截", socket.socket is _BlockedSocket)
try:
    socket.create_connection(("127.0.0.1", 9))
    check("拦截真实生效", False, "竟然建连成功")
except _NetBlocked:
    check("拦截真实生效", True, "create_connection 抛 _NetBlocked")
except Exception as e:
    check("拦截真实生效", False, f"抛了别的异常 {type(e).__name__}")

socket.socket = _real_socket
socket.create_connection = _real_conn
print(f"\n=== 结果: {len(PASSES)} PASS / {len(FAILS)} FAIL ===")
if FAILS:
    for f in FAILS:
        print("  未通过:", f)
sys.exit(1 if FAILS else 0)
