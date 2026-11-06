# SMDD Type 4 全量实验：ChatDrug / AgentDrug

两组各 340 题，百炼 `deepseek-v4.1-flash`。使用新的独立实验目录，历史 20 题结果不纳入本批次。

CPU 实验目录：`/home/chenfuxin/smdd-migration/smdd-assets/experiments/type4_full340_bailian_20260929`

模型请求在 GPU 服务器原密钥所在位置执行；CPU 通过 SSH 接收模型响应，不传输密钥。GPU 程序目录：`/data2/chenfuxin/smdd_type4_full340_bailian_20260929`。

首次诊断发现共享 Boltz 环境的 NumPy/RDKit 版本冲突。修复依赖仅安装到本次 GPU 目录的 `boltz_deps`，通过命令级 `PYTHONPATH` 使用，不修改共享环境。受影响的诊断结果单独归档到 `recovery_attempts`，不纳入正式 340 题。正式启动前要求一次真实 10-sample Boltz 预测成功。

## 方法与预算

- 每题 ADMET 15 次、Boltz 8 次，总 token 上限 10,000,000；检索过程调用性质预测也消耗同一预算。官方最终评分不消耗生成阶段预算。
- ChatDrug 复用之前 SMDD 20 题的 ReDF 适配器，最多 2 轮反馈。按原 ChatDrug 代码，对检索库按与当前生成分子的 Morgan count 指纹 Tanimoto 相似度降序查找；原实现没有固定相似度截断值。本次不添加 0.7 检索门槛，保留性质条件筛选、无合格参考时停止的规则。最终 SMDD 评分仍要求候选分子与原始分子相似度 ≥0.7。温度沿用之前 SMDD 实验的 1。
- AgentDrug 现有版本用于分子编辑基准，本次新增 SMDD 适配层：有效性反馈、数值性质反馈、性质合格参考检索、成功提前结束、最多 5 次生成、无参考仍继续、最后一次生成作为最终输出。保留现有实现的 temperature=0、每次生成最多 256 tokens，截断输出照常进入有效性反馈，不重抽。性质检查替换为 SMDD 的公开条件与预算受限 oracle；不是原论文任务的数值复现。
- 两种方法使用同一固定 10,000 分子检索库，排除本题原始分子；不读取 witness 作为模型或检索输入。适配器只从公开 `reference.sdf`、`complex.pdb` 与任务描述获取输入。
- 最终评测复用 `smdd-evals:359ef1d7`，仅将 Boltz 计算转到 GPU 服务器，评分规则不变。

## 执行与结果

ChatDrug 使用 GPU 1，AgentDrug 使用 GPU 6，各自独立顺序运行。预算耗尽与科学失败不终止全批；基础设施错误单独记录，继续后面的题目。每题安全看门狗为 12 小时，官方评测返回 errored 时重试一次。

各方法目录中的 `summary.json` 包含总数、完成数、通过数、评测失败数、基础设施错误和预算耗尽数。`state=running` 时不是最终成绩；最终准确率分母固定为 340。`run/<task>/` 保存生成轨迹和提交，`evaluator/<task>/result.json` 保存官方评测，`records/<task>.json` 保存终态。`supervisor.log`、`current.json`、`supervisor.pid` 用于查看进度；全部处理完成后生成 `RESULTS.md` 和 `experiment.exit`。

`protocol_manifest.json` 记录源代码与检索库哈希；预检确认 340 题输入、公开文件隔离、模型实际响应名和预算限制。`test_flow.py` 检查无参考及预算耗尽后仍完成 5 次生成、截断输出保留和成功提前停止。
