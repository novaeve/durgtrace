#!/usr/bin/env python3
"""trace-harness-v1.2 元数据透传单元测试。dummy response，无网络。"""
import sys, json, tempfile, shutil, os
from agent_harness.agent_loop import _FakeResponse
from agent_harness.trace import response_meta
from agent_harness.logger import AgentLogger

FAILS, PASSES = [], []
def ck(n, c, d=""):
    (PASSES if c else FAILS).append(n)
    print(f"  {'PASS' if c else 'FAIL'}  {n}" + (f"  [{d}]" if d else ""))

class U:
    prompt_tokens=100; completion_tokens=20; total_tokens=120
    prompt_cache_hit_tokens=64
class M:
    content="hello"; tool_calls=None; reasoning_content="thinking hard"
class C:
    finish_reason="tool_calls"
    def __init__(self): self.message=M()
class Raw:
    """形如 LiteLLM ModelResponse。"""
    id="chatcmpl-dummy-abc123"; model="deepseek-v4-flash"; created=1780000123
    def __init__(self): self.choices=[C()]; self.usage=U()

print("=== 1. _FakeResponse 保留元数据 ===")
fr = _FakeResponse(Raw())
ck("保留 id", fr.id == "chatcmpl-dummy-abc123", fr.id)
ck("保留 finish_reason", fr.finish_reason == "tool_calls", str(fr.finish_reason))
ck("保留 created", fr.created == 1780000123, str(fr.created))
ck("model 仍正确", fr.model == "deepseek-v4-flash")
ck("usage 仍存在", fr.usage is not None)
ck("output 仍构建", isinstance(fr.output, list) and len(fr.output) >= 1,
   str([i.type for i in fr.output]))

print("\n=== 2. response_meta 读到真实值（不再 unavailable）===")
meta = response_meta(fr)
ck("response_id 有值", meta.get("response_id") == "chatcmpl-dummy-abc123", meta.get("response_id"))
ck("finish_reason 有值", meta.get("finish_reason") == "tool_calls", meta.get("finish_reason"))
ck("actual_model 有值", meta.get("actual_model") == "deepseek-v4-flash")
unav = meta.get("_unavailable", [])
ck("response_id 不在 _unavailable", "response_id" not in unav, str(unav))
ck("finish_reason 不在 _unavailable", "finish_reason" not in unav)
ck("litellm 重试仍诚实标 unavailable",
   meta.get("litellm_internal_retries") == "unavailable")

print("\n=== 3. 真缺失时仍标 unavailable（不伪造）===")
class Bare:
    model="m"; usage=None
    def __init__(self): self.output=[]
m2 = response_meta(Bare())
ck("缺 id 时列入 _unavailable", "response_id" in m2.get("_unavailable", []))
ck("缺 finish_reason 时列入 _unavailable", "finish_reason" in m2.get("_unavailable", []))
ck("不伪造 response_id", "response_id" not in m2)

print("\n=== 4. Logger 实际写入 trajectory ===")
tmp = tempfile.mkdtemp(prefix="v12_")
try:
    lg = AgentLogger(tmp, "t_meta")
    lg.log_llm_call(1, fr, wall_time_s=2.5)
    ev = [json.loads(l) for l in open(os.path.join(tmp,"trajectory.jsonl")) if l.strip()]
    llm = [e for e in ev if e["event"]=="llm_call"][0]
    ck("trajectory 记录 response_id", llm.get("response_id")=="chatcmpl-dummy-abc123")
    ck("trajectory 记录 finish_reason", llm.get("finish_reason")=="tool_calls")
    ck("trajectory 记录 wall_time_s", llm.get("wall_time_s")==2.5)
    ck("官方字段仍在", all(k in llm for k in
       ("model","input_tokens","output_tokens","tool_calls","assistant_text")))
    ck("reasoning_content 仍记录", llm.get("reasoning_content")=="thinking hard")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n=== 结果: {len(PASSES)} PASS / {len(FAILS)} FAIL ===")
for f in FAILS: print("  未通过:", f)
sys.exit(1 if FAILS else 0)
