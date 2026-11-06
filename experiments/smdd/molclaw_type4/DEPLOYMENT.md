# MolClaw SMDD Type4 / A100

目标：125.76.110.84:11032，zlc；独立目录 `/yimin/zlc/molclaw_type4_20261003`。

340 个 Type4 任务，6 个任务 worker。两张 A100 每卡最多两个 Boltz 进程，启动前要求空闲显存至少 36000 MiB，连续启动间隔 90 秒。采样总数仍为结构 10、亲和力 10，seed=42；内部串行采样降低显存峰值。所有 oracle 与评估共享进程锁。磁盘低于 50 GiB 时暂停派发新任务。中断任务单独标记，禁止盲目重跑覆盖。

模型已核对现有运行源码：百炼 deepseek-v4.1-flash，enable_thinking=false，不传 reasoning_effort。温度为 1，与 ChatDrug/LIDDIA 一致；AgentDrug 的原方法温度 0 不作修改。模型请求构造测试已通过；未调用真实模型。

保留 MolClaw 原生 CLI、技能库和提示构造；使用官方 SMDD 公共 python、predict_boltz、predict_admet、submit 工具适配。不是四基准的 SCP 工具配置。每任务 100 次模型请求、1000 万累计 token、Boltz 8 次、ADMET 15 次。官方 evaluator 独立运行；任务答案、认证文件不挂载到 agent 工作区。

当前状态：代码、CLI、代理环境和 340 题数据已部署；科学计算环境/权重仍在传输。六进程竞争测试通过（每卡上限 2，总上限 4）。DeepSeek 最小实际请求成功，返回 deepseek-v4.1-flash，总 token 10；明确发送 enable_thinking=false，不传 reasoning_effort。已针对本实验清除宿主失效的 localhost 代理变量。真实 CUDA、Boltz 和原生 CLI 工具 smoke 待完成，正式实验尚未启动。

认证已配置：初次方案被自动审批拒绝；用户随后明确授权“允许，仅用于这批实验”。已通过内存中转复制到 `private/model.env`，目录 0700、文件 0600；不挂载至 agent 工作区。未添加 SSH key。

长期服务 `molclaw-type4-a100.service` 已启用，zlc Linger=yes。当前状态是等待环境和 Boltz 预检；预检成功后自动执行原生 MolClaw 工具 smoke，核对实际请求模型与思考设置，然后启动六 worker。任何 smoke 失败均阻止正式任务开始。当前本地传输与后续预检进程需保持运行，数据传完后正式实验由服务器独立常驻服务管理。

旧服务器实验未修改。源代码副本保存在本目录 source_*.py；构建命令 `python build_deployment.py`，模型设置验证 `python test_model_settings.py`。
