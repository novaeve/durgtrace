# LIDDIA Type4 运行异常修复（2026-09-29）

## 已确认的异常

8 道运行异常中，4 道是 Boltz OOM（ABL1_0、ABL1_1、ABL1_11、ABL1_3），4 道是 Pocket2Mol 不等长评分向量拼接错误（ABL1_6、ACE_15、ACE_3、ACE_4）。另有 ABL1_2 在最终评测时 Boltz OOM。Boltz 的 pre_affinity_input.npz 缺失是结构生成被 OOM 跳过的后果。

ACE_6 是之后额外发生的磁盘写满中断：agent_result.json 被截断为零字节，队列读取该 JSON 时又退出。旧 batch_status.json 的 running 是过时状态；已经备份并更正为 interrupted，未改动已记录的成绩。

## 代码修复

- 新的 pocket_runtime.py 使用独立上游脚本副本，不修改原 Pocket2Mol 仓库。向原始 logp_to_rank_prob 传递列表，避免将长短不一的平均 logp 向量强制变成二维 NumPy 数组；仍按原函数逐个求和，保留原排名公式。
- Pocket2Mol 不再逐步保存 samples_*.pt 候选池快照；仍保留配置、种子、日志、生成 SMILES 与 SDF。已有历史文件未删除。
- Boltz 保留 10 次采样与原模型，将 max_parallel_samples 从 2 改为 1。优先原 GPU；不足 28000MiB 空闲显存时选择满足条件的其他 GPU，并在取得本实验 GPU 文件锁后重新检查。无合适显卡时返回资源阻塞，不杀其他任务。外部作业不受本实验锁约束，因此仍不能保证未来绝无 OOM。
- Boltz/Pocket2Mol 子进程失败与超时转为工具错误，反馈给 agent。GraphGA 停止本次失败优化时保留已真实评分的候选；不填假分、不免费重试，失败预测仍消费预算。
- JSON 改为临时文件写完、fsync 后替换，写满时不会先截断已有结果；队列识别空/损坏 JSON，记录 corrupt_record。
- 每题开始前检查至少 50GiB 可用空间；工具/决策步骤检查至少 5GiB。磁盘/显存资源阻塞单独标记。旧冻结源码与安装源码不同则拒绝混用，后续继续须使用新运行版本。

## 验证与存储

14 项针对故障恢复和 CODE 的测试通过，含实际 bubblewrap 测试。真实 Pocket2Mol 小样本生成 1 个有效分子，0 个候选池快照。该小样本不表示所有口袋已完整复测。

存储统计：历史逐步快照 733 个、405420937380 字节（约 377.6GiB）；初始/最终快照 67 个、26186727671 字节（约 24.4GiB）。全量旧运行约 395GiB。检查期间 /data2 可用空间从约 17GB 回升到约 57GB，本轮没有执行历史文件清理。

单独使用原 ABL1_0 OOM 输入在空闲 GPU 0 重放 Boltz（10 次采样、并行 1）；结果见服务器 runs/runtimefix_preflight/boltz_result.json。诊断结果不计入正式 benchmark，不改写原预算或成绩。全量队列尚未恢复。

该 Boltz 重放已成功完成，Number of failed examples 为 0，正常输出 affinity_pred_value=-0.9614107608795166、affinity_probability_binary=0.5887174606323242。验证的是工具能够完成计算，不是该分子满足优化目标，也不能据单一输入保证全部蛋白都不会 OOM。
