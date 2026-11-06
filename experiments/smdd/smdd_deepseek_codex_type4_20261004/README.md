# SMDD-type4：DeepSeek 官方基线与 Codex

2026-10-04 在原 GPU 服务器新增两组，各独立跑完整 340 题：

| 方法 | harness | 模型 |
|---|---|---|
| deepseek | 现有 SMDD-Bench upstream `agent_harness`，主循环、工具和预算代码保持源文件哈希一致 | 百炼 deepseek-v4.1-flash |
| codex | 官方 Codex CLI 0.149.0，复用现有其他 benchmark 的 Responses 接口适配方式 | 百炼 deepseek-v4.1-flash |

两组实际发送 `enable_thinking=false`，不发送 reasoning_effort，temperature=1。模型接口凭据仍由 GPU 原服务器 host 侧读取；不向生成进程挂载凭据、评分程序、task.yaml 或其他题目/历史答案。

预算为每题 ADMET 15 次、Boltz 8 次、100 模型轮次、累计输入输出 10,000,000 tokens；Boltz 默认 10 samples、seed=42。Codex 通过 MCP 调用同一官方 ToolExecutor。原官方评分代码不修改，仅将 GPU 计算排入同一资源池，最终评分不计入生成预算。

远端目录：`/data2/chenfuxin/smdd_deepseek_codex_type4_20261004`，用户 `chenfuxin@123.157.219.189:17065`。

每组先跑一题验证生成及评估；评分返回 passed/failed 后自动扩展到每组 4 题并发。GPU 池为 1、3、4、6，每卡最多一个本实验 Boltz，启动至少需要 28,000 MiB 空闲显存。与旧 LIDDIA 和 CPU Type4 池共享锁，避开其他用户或其他 Boltz 已占用的 GPU；科学推理的 GPU 时间上限 30 分钟，资源等待独立计时、最长六小时。可用磁盘不足 30 GiB 时暂停派发。

调度器使用 nohup 独立会话运行，断开 SSH 后继续。进程恢复通过 PID 身份和现有 worker 判定防止重复执行；服务器重启后需重新启动调度器。尚未产生终态的部分输出会保留，不自动重做。

`manifest.json` 保存实际请求检查、源文件哈希、预算及并发配置；`preflight/result.json` 保存真实工具测试。进度在 `scheduler_status.json`，每题模型与工具轨迹在 `runs/<method>/<task>/`，官方评测在该目录的 `evaluation/result.json`。通过率分母固定 340，阶段已评测通过率另算。

Codex 自定义模型供应商和 Responses 配置参考 [OpenAI 官方文档](https://learn.chatgpt.com/docs/config-file/config-advanced)。这里的模型保持用户指定的 DeepSeek，不替换成 Codex 默认模型。
