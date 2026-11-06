# LIDDIA Type4 解析修复与首题重跑

任务：smdd_004_ABL1_1。运行目录：GPU 服务器 `/data2/chenfuxin/liddia_smdd_type4_20260928/runs/pilot_parserfix1/smdd_004_ABL1_1`。

## 修复

新增 liddia_action_parser.py，读取最后一个独立 Action 行开始的指令块，将 Input 与 Desc 绑定到同一块。对动作 ID 和列表类型做校验，使用 ast.literal_eval，禁止把解释性文字作为代码执行。解析失败反馈到下一轮决策，消耗正常 LLM 预算，不执行工具。原始运行代码已归档在服务器 runs/pilot/run_liddia_type4.original.py。

4 项测试通过，包括重放首次运行全部决策、失败原文、最终块选择、拒绝非法输入/未知动作/缺少 CODE 描述及正常 Boltz 行索引。服务器 Python 编译检查通过。

## 运行结果

保持原任务、模型、温度、种子与预算：deepseek-v4.1-flash，temperature=1，seed=42，LLM 100 次，ADMET 15 次，Boltz 8 次；Vina 禁用。修复单独记录在 protocol.json 的 action_parser 与源码哈希中。旧结果未覆盖。

- 状态：runtime_error，无提交、无最终分子评测。
- LLM：6 次，14247 tokens。
- ADMET：15 次；Boltz：0 次；Vina：0 次。
- 第一次回复字段间带空行，严格解析器返回格式错误；下一次决策成功执行 GraphGA，而非退出。此次没有调用 Pocket2Mol，是模型实际选择的轨迹。
- GraphGA 用完共享 ADMET 预算后，CODE 连续三次失败。前两次因生成代码导入不在隔离环境白名单内；第三次因其引用的参考分子 MOL007 未包含在该次动作传入的数据集合中。CODE 重试耗尽抛出 RuntimeError，控制器结束。

原先误读行内 Input 的问题已修复；此次失败暴露的是 CODE 执行/错误恢复问题。导入限制是本次适配器设置，不能全归因于原生 LIDDIA。尚不能由本次失败评判分子优化效果或 Boltz 能力。没有继续自动重跑、没有启动 340 题批量实验。

本地原始记录见 type4_parserfix1/ 下的 agent_result.json、llm_calls.json、trajectory.json、protocol.json、budget.jsonl、molecule_sets.json。
