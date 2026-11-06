# SoL-Pi 四基准实验

服务器目录：`/data2/chenfuxin/sol_pi_fourbench_20261005`。

完全复用 Codex/MolClaw 已冻结的 3,800 题：S²-Bench MolEdit 1,500、MolCustom 1,500；MolLangBench Editing、Generation 各 400（core/extended 各 200）。cases.json SHA-256 为 da312e6665807008cc758ba97e6f4289ce4501e3b1d5c82e5f540ac4ed845f6e。

主模型及 evidence reducer 均为 deepseek-v4.1-flash。实际发送端强制 temperature=0、enable_thinking=false，移除 reasoning_effort/thinking 和 max_tokens，与已核验的 Codex 实际请求一致。使用原服务器私有 deepseek_canchen.env；不复制或输出真实密钥，agent 仅收到 loopback 占位凭据。API receipts 记录实际请求参数和 provider usage。

SoL-Pi 复用已有安装：commit e1a586af0ad8956f42ae5b26bba20e48fbf30e00、原生 Pi 0.86.1。actionFusion、observationPack、evidencePreservingReducer、onlineContextCompact 全部启用。provider contextWindow/output metadata 与已有 SoL-Pi 实验一致，实际输出额度仍由上游默认值决定；cacheWriteReadRatio=12.5 为默认配置，不宣称对应 DeepSeek 真实收费。

任务 prompt 与 Codex 四基准实验逐字一致；仅底层原生 agent/harness 系统提示和工具变化。允许原生 Bash/read/write/edit 及同一 RDKit 环境自行计算，未新增公开条件评分器或隐藏 oracle 反馈。每题独立文件系统/PID 空间；不挂载答案、评估源码、其他运行结果或真实密钥。离线评分代码直接复制已有 score.py，S² 使用原精确属性约束，MolLang 使用官方 canonical SMILES 一致率；完整分母保留运行失败和缺失答案。

沿用 Codex 的并发 2、单题墙钟 3,600 秒、事件静默 1,800 秒。每题一条原生 session；上下文压缩恢复产生的中间 aborted 不算最终失败。截断工具参数不执行，截断/超时保留为该题结果，不按正确性挑选、续跑或重采样；这些不是 PMO 的 oracle 预算实验。

最终答案使用唯一 <answer>SMILES</answer>，与审计后的 Codex parser 一致，接受 <- 配位键；不选轨迹中的早期候选。固定题集、评估文件、SoL-Pi 源文件和实验源码哈希记录在 manifest.json。

启动流程：回归检查、隔离/RDKit/模型加载、原生工具 smoke、10 题独立 pilot、离线 pilot 评分、全量独立实验、离线全量评分。基础设施检查通过自动启动全量，不以 pilot 化学成功率阻止启动。

服务器状态命令：

```bash
cd /data2/chenfuxin/sol_pi_fourbench_20261005
/data2/chenfuxin/molclaw_20260924/isolated_env/bin/python status.py
```

主要证据：runs/full/<id>/result.json、api/*.json、events.jsonl；work/full/<id>/.pi/session.jsonl 和 loaded-runtime.json；runs/full/summary.json；runs/full/scores.json；pipeline_exit.json。
