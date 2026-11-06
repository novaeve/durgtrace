# AgentDrug × ChatDrug-MolEdit-28 / S²-mini

官方仓库：https://github.com/lhkhiem28/AgentDrug

固定commit：a8d3a9eb459e161135a2c7e27490453603b3e6c2。论文：https://aclanthology.org/2025.findings-emnlp.1328/ 。用户选择继续使用DeepSeek官方deepseek-flash进行同模型对比；本实验复现方法执行流程，不声称复现Qwen论文表格数值。

## 方法与预算

从官方 inference.py 的 refine == agentdrug 分支直接抽取 core_original.py，并生成带明确修复的 core_fixed.py。保留数值性质反馈、RDKit有效性反馈、按失败生成分子的Morgan计数指纹Tanimoto检索合格参考、原提示拼接方式、成功提前停止、最后一轮输出作为失败时最终答案。

原 inference.sh 单属性 refine_steps=3、多属性=4，分支实际执行 refine_steps+1，故最多4/5次生成。source/config.py 明确 max_completion_length=256；本实验请求max_tokens=256以保留它。原model.generate会在达上限时返回截断文本，本实验同样将已有文本交给有效性与评分/修复流程，不将截断自动视为基础设施错误或重抽。原版greedy解码在API侧用temperature=0、thinking=disabled实现近似；API模型及tokenizer不同，不声称数值逐位复现。

这与之前ChatDrug最多3次生成的预算不同，属于各方法原有流程的同模型比较，不能称严格同调用次数消融。

## 必要代码修复

1. 原分支判断无效SMILES后仍执行描述符计算，异常被except continue吞掉，修复提示没有进入下一轮。现将明确的not chemically valid反馈进入原反馈分支。
2. 多属性任务将prop变量改成第二属性后，下轮再次按LogP前缀切分而出错。现每轮恢复原任务名。
3. 完整AgentDrug分支8处下降方向检索条件缺少括号，现修复布尔表达式优先级，确保参考满足两个属性条件。
4. 原评分多属性分支引用未定义preds/labels、invalid记录可能重复计数、百分数乘99.99。最终统计直接使用此前冻结并验证的两个benchmark评分器，规避这些汇总缺陷；不沿用错误百分数。
5. 原utils.py仅用AutoGen执行一段RDKit有效性检查代码；改为直接执行同一Chem.MolFromSmiles检查与相同反馈文本，避免字符串插入执行代码与vendored AutoGen版本冲突。不是删除一个LLM agent，原处本来llm_config=False。

## 数据接口和MR扩展

输入为此前冻结的200输入×28设置=5,600条，以及S²-mini LogP/QED/MR各500条，共7,100条；不使用作者数据类自动抽100条的逻辑。保留各benchmark的原始任务指令，加原AgentDrug的单SMILES输出格式。未把作者ZINC500的14种任务定义误当作ChatDrug的14种任务。

MR原仓库没有，按同样的单属性数值反馈接口增加MR±，使用S²原评分定义。源任务的Kekulize描述符处理跟随ChatDrug评分器；S²用其原性质和相似度实现。源码中的Hit@0.5只作额外指标，未当作强制成功条件，也未加入检索相似度阈值。

为和上一轮ChatDrug控制数据变量，检索库使用同一固定10,000分子库，已按canonical结构排除两个benchmark所有输入。它不等于作者GenerationDataset从自带database.csv按random_state=42抽取的10,000条。此为明确的数据控制选择，不是论文原始数据库采样的完全复刻。各run_config记录语料与输入manifest哈希。

## 已完成验证与运行

validate.py覆盖28个源设置及LogP/QED/MR各两个方向，1,020次性质成功判定与官方评分一致；检查无效SMILES反馈进入下一轮、4/5次上限、检索参考满足全部性质条件，并对两个未受修复影响的场景比较原分支和修复分支的输出及完整提示相同。

真实API pilot固定34条（每设置/方向1条），只验流程，不要求任务成功。34条无运行错误后，自动启动full全部7,100条，pilot不混入full成绩。每实例保留请求、完整反馈、输出、token和截断标记；结果按实例落盘并可续跑。两个工作线程，无本地模型GPU依赖。

服务器目录：/data2/chenfuxin/agentdrug_20260922

tmux：agentdrug-full。日志experiment.log；结果runs/pilot与runs/full；退出码experiment.exit。旧ChatDrug/SMDD结果不修改。
