# LIDDIA × SMDD Type4 首题试跑结果

固定任务：`smdd_004_ABL1_1`。本次为 DeepSeek 驱动的 LIDDIA 完整工具系统适配验证，不是原论文数值复现。

**结果：agent 动作解析异常退出，未提交 solution.smi，没有最终分子评分。** 这是本次真实失败记录，不是任务指标通过或不通过的分子级结果。未自动重跑，未启动 340 题批量实验。

## 实际执行

| 项目 | 结果 |
|---|---|
| Pocket2Mol | 原权重、真实口袋、beam=300；生成 103 个有效结果，按请求数量向 LIDDIA 返回前 100 个 |
| 首轮 CODE | 对生成集与公开参考分子筛选，保留 1 个分子 |
| GraphGA | 1 次 clearance 优化，返回 15 个已评分分子；到达共享 ADMET 上限后停止 |
| 后续 CODE | 筛出 2 个候选；下一次动作解析时退出 |
| ADMET | 15/15，全部真实调用，无 backend 错误 |
| Boltz-2 | agent 0/8；此前独立基础设施预检成功，未混入实验 |
| Vina | 0；工具注册、自动评估及原函数调用入口均禁用 |
| LLM | deepseek-v4.1-flash；10 次逻辑调用，返回响应统计 33,536 tokens |

## 退出原因

保留的原生 `liddia/utils.py:get_metadata_from_response` 使用正则查找第一个 `Input:`，随后交给 `ast.literal_eval`。

模型同一条回复中先出现解释性内联文本：

```text
Action: CODE002, Input: ['MOL010'], Desc: ...
```

末尾另有规范动作块：

```text
Action: CODE002
Input: ['MOL010']
Desc: ...
```

原解析器选中了前面的内联 `Input:`，将后续 `Desc:` 也交给 Python 字面量解析，触发 SyntaxError。没有执行最后一次 CODE，也没有提交分子。原始 `agent_result.json` 保留 `runtime_error` 标签；根据轨迹，本次具体分类为 **agent 输出格式解析失败**，不是 Docker、CUDA、ADMET 或 Boltz 服务故障。

此前 CODE 动作发生了两次重试：一次触发适配层对 os/sys/sascorer 导入的限制；另一次生成了上游提示模板示例中的无效函数签名。第三次成功。前者属于适配层限制，不能归因于 LIDDIA 原生算法；完整原始响应保存在 llm_calls.json。

不能用这一题推断整套 Type4 的成功率，也不能将未调用的 Boltz 记为预测失败。当前证据说明 Pocket2Mol、GraphGA 与共享 ADMET 预算已联通，同时暴露了原生解析器面对此聊天模型输出时的脆弱性。

## 环境与 Docker 复核

全部 340 道 Type4 任务和原 `smdd-evals:359ef1d7` 镜像文件系统已迁到 GPU 服务器。benchmark commit 为 `359ef1d7c042b85fc1c544662b4fd6fb381f346f`。

实测当前 `chenfuxin` 为 uid1009、组1010；默认 Docker socket 是 root:docker、权限 srw-rw----，当前连接访问被拒绝。不能据此说该服务器没有 Docker 或没跑过 ChatDrug。已核对的旧 ChatDrug 脚本在旧服务器运行 Docker、将 Boltz 转发到 GPU 服务器。本次改用 GPU 服务器已安装的 bubblewrap，以用户命名空间运行原评测镜像文件系统，不更改全局 Docker 权限。

原 SMDD Boltz2.2.1 的全局依赖存在 NumPy/Numba 及 RDKit 导入冲突，已在单独 overlay 环境修复；实际完整预检返回了结构与亲和力结果。正式配置保留 10 diffusion/affinity samples、并行数2、seed42、MSA及potentials。原镜像 ADMET 实际八项输出与首题公开基线数值一致。

## 证据位置

- 服务器实验目录：`/data2/chenfuxin/liddia_smdd_type4_20260928`
- 本题原始结果：`runs/pilot/smdd_004_ABL1_1/agent_result.json`
- 本地证据：[type4_pilot/agent_result.json](type4_pilot/agent_result.json)、[type4_pilot/trajectory.json](type4_pilot/trajectory.json)、[type4_pilot/llm_calls.json](type4_pilot/llm_calls.json)、[type4_pilot/budget.jsonl](type4_pilot/budget.jsonl)
- 协议：[LIDDIA_Type4_实验协议.md](LIDDIA_Type4_实验协议.md)
- 版本与哈希：[type4_runtime_manifest.json](type4_runtime_manifest.json)
