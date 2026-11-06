# SoL-Pi SMDD Type2 / Type3

服务器独立目录：`/data2/chenfuxin/sol_pi_smdd_type2_type3_20261006`。

Type2：沿用原 25 题、75 个药效团点。公开描述及去标识 receptor.pdb 与现有 Codex / DeepSeek 相同；输出 solution.csv（3 行 x,y,z,type，无表头）。DeepSeek v4.1 Flash，temperature=1，enable_thinking=false，无 reasoning_effort。

Type3：原 52 题；复用原 obfuscate_task 的 complex.pdb、reference.sdf、公开描述，与现有 Codex 输入哈希核对。输出 solution.smi。DeepSeek v4.1 Flash，temperature=1，enable_thinking=true，reasoning_effort=high；保留 reasoning_content，主模型与 reducer 使用同一后端和思考设置。

两组 API 直接复用各自原 runtime.API 类，真实 key 保留在原私有 deepseek_canchen.env，不复制到实验文件或 agent 沙箱。每题共享模型调用上限 100、累计输入输出 1,000 万 token，SoL-Pi 附属请求也计入；不向上游新增单次 max_tokens。原科学工具源码（python、predict_boltz、predict_admet、submit）、AgentConfig 和工具提示一致。Boltz/ADMET 预算 8/15，种子 42，默认 10 个结构与 affinity 样本。

原生 Pi 0.86.1、已有 SoL-Pi commit e1a586af0ad8956f42ae5b26bba20e48fbf30e00，四机制全部启用。保留原生文件、计划和观察回忆工具；一般科学计算通过原 SMDD python 在无网络 rootfs 内执行。Native Bash / action-fusion then_run 仅用于当前工作区的简单文件检查，避免旁路科学工具预算；这是公共科学工具对齐的适配版。模型价格字段为 adapter 元数据，cacheWriteReadRatio 沿用默认 12.5，不宣称为 DeepSeek 实际收费。

Type2 原 baseline 的 CPU Docker 工具传输改用现有服务器 evaluator_rootfs；此环境部署差异保留，不宣称原镜像逐字节相同。Type3 使用已有同一 rootfs、工具实现、官方 EvaluationRunner。沿用确认可用的低显存部署：max_parallel_samples=1、expandable_segments，保持默认 10 样本、精度、指标和阈值。复用已有 GPU pool/shared leases/free-memory gate，不打断其他任务；无可用 GPU 时排队并记录 resource_wait.json。

仅复制公开输入进 agent 工作区；不挂载 task.yaml、ground_truth、评估器或既有 agent 结果。submit 接受后即结束 episode，不再调用模型。上下文压缩产生的可恢复 abort 不算失败；截断工具参数不执行。Type2 墙钟上限 3,600 秒、并发 2；Type3 沿用原补充 harness 的 86,400 秒、一次生成 1 题。评分器独立后台运行，可与生成并行；GPU 预测共享锁。

Type2 直接使用原 pharmacophore_3d.py：类型兼容 Hungarian 匹配、距离严格小于 2.5 Å，报告题目通过率及点正确率，分母固定 25/75。Type3 复用原 evaluate.py / eval_bridge.py /官方五项评分，分母 52；无效分子保留 raw_result 后计失败，基础设施错误单列并停止等待检查。评分不反馈模型，不按正确率重抽。

每组先运行独立工具、submit、思考参数及隔离 smoke，通过后自动开始全题生成；错误小测不混入正式结果。实际 API receipts、工具轨迹、输入和源码 hash、原生 session 保留。已有 agent 实验与源码均不修改。

状态命令：

```bash
cd /data2/chenfuxin/sol_pi_smdd_type2_type3_20261006
/data2/chenfuxin/molclaw_20260924/isolated_env/bin/python status.py
```

结果：type2 或 type3/runs/solpi/<task>/result.json 及 solution.csv/solution.smi；原生会话位于同目录 workspace/.pi/session.jsonl；官方评分位于 type2 或 type3/evaluation/solpi/<task>/result.json；evaluation/summary.json 保存进度。
