# LIDDIA / AgentD 源码审计与安装记录

检查日期：2026-09-28。服务器：`chenfuxin@123.157.219.189:17065`。

**目前不能把这两个 agent 标为“完整复现”。主要生成、优化和亲和力工具已安装并通过小规模运行验证；完整 agent 流程仍有下述缺口。** 没有运行论文全量实验，也没有验证论文数值结果。

安装目录为 `/data2/chenfuxin/agent_reproduction_20260928`。所有修改限定在这个独立目录，既有实验目录和密钥文件未改动。

## LIDDIA

论文已核对为 [EMNLP 2025 正式会议版本](https://aclanthology.org/2025.emnlp-main.603/)。[官方仓库](https://github.com/ninglab/LIDDIA)固定到 `d8665726c4ec15c8ba22f7d44cfaccf24d490ad1`。

**公开源码缺少论文中的 Pocket2Mol 集成。** `liddia/action.py` 的 `sample_pocket2mol` 被注释，其中引用的 `liddia/apptainer/pocket2mol` 不存在；`run.py` 实际注册的是 `sample_zinc`。因此，安装独立 Pocket2Mol 并不等于恢复了作者的生成步骤，不能直接拿公开版当论文方法比较。原始集成的口袋处理、采样配置和失败处理也不能仅凭这一段注释还原。

| 部件 | 安装及验证结果 |
|---|---|
| Pocket2Mol | 已安装官方源码和官方 Google Drive 权重；在官方 `4yhj.pdb` 示例上通过 CPU 采样，保存 1 个有效 SMILES 和对应 SDF |
| GraphGA | 已安装 `wenhao-gao/mol-opt` 的 GraphGA；真实 QED 优化成功，结果中 33 个有效分子 |
| LIDDIA LLM 接口 | 复用既有百炼配置，`deepseek-v4.1-flash` 实际对话通过 |
| QED / SA | 实际评分通过 |
| docking | **未通过**。Vina 1.2.7 返回 -5.09 后，进程发生 `malloc_consolidate` 原生内存错误并退出；恢复 1.2.5 的构建缺少 SWIG 和部分 Boost 链接库，未完成 |
| 完整 LIDDIA 论文流程 | 未通过；原始 Pocket2Mol 连接层缺失，30 个靶标实验未运行 |

GraphGA 上游的 `load_smiles_from_file` 被注释，已补回读取列表/文件的基础函数，并为仅使用 GraphGA 的安装单独声明依赖。其原始预算判断有边界问题：设置 32 次评分实际记录 33 次；未改动其优化算法来掩盖这一差异。

Pocket2Mol 做了三处兼容性修复：PyG 的 `subgraph` 导入位置、硬编码 CUDA 改为跟随输入设备、完成采样后避免对空候选队列计算采样概率。LIDDIA 的并行任务数默认限制为 2。修改均保存在 `audit/patches/`。

`run_liddia_zinc_deepseek.sh` 是**公开 ZINC 版**的启动入口，不是补全后的 Pocket2Mol 论文版。独立 Pocket2Mol 验证脚本为 `smoke_pocket.sh`，优化验证脚本为 `smoke_liddia.sh`。

## AgentD

已通过 Undermind 的“核心 Agent Benchmark 文献 / 提出 Agent”确认条目，并核对 [JCIM 正式论文 DOI](https://doi.org/10.1021/acs.jcim.5c02454)。[官方仓库](https://github.com/hoon-ock/AgentD)说明论文复现使用早期发行版本；实际存在的标签是 `V1`，对应 `40571357b62eb0ef2d418fdc00fe9edbd0097199`，已放在 `AgentD-paper/`。当前主分支另保存在 `AgentD/`。

**未发现六类核心任务模块和 BAPULM 回归头权重缺失；但这不能证明论文结果已可完整复现。** 上游 Python 版本声明冲突、FAISS CPU/GPU 同时固定、作者机器绝对路径、未固定的 REINVENT4 版本，都需要处理。另一个实际限制是论文版本的 Boltz 工具只生成配置并返回命令，需另外执行预测。

| 部件 | 安装及验证结果 |
|---|---|
| REINVENT4 | 固定 `v4.4.22`，保留 AgentD 需要的 `configs/toml/sampling.toml` 接口；这是可运行的兼容版本选择，不是已确认的作者实验精确版本 |
| Reinvent / Mol2Mol | 官方 prior 已就绪；两者均通过 AgentD 原工具实际生成 4 个有效分子 |
| DeepSeek | 既有配置中的 `deepseek-v4.1-flash` 返回正常；AgentD 的 LLM 配置生成工具实际输出了可解析、模型路径存在的 TOML |
| BAPULM | 回归头、ProtT5、MoLFormer 权重齐全；完整编码与预测链路通过，输出维度分别为 1024 / 768，预测结果有限 |
| Boltz 2.0.3 | 独立环境安装完成，CLI 通过；复用 `/data2/chenfuxin/boltz-cache`，未做整条复合物预测 |
| GPU | PyTorch 2.7.1 + CUDA 12.8；RTX 5090 上极小矩阵内核验证通过 |
| embedding / Serper | 仍未配置可用服务。现有百炼凭据对所测 embedding 模型返回 403；DeepSeek 官方接口无对应 embedding 路由 |
| 完整 AgentD 流程 | 尚未打通向量记忆/RAG 与联网检索；未运行论文 BCL-2 全量实验 |

为兼容 RTX 5090，使用 PyTorch 2.7.1，FAISS 使用 CPU 版。REINVENT4 移除了本次不用的商业 OpenEye 强制依赖，并调整其版本声明以兼容已验证的采样/Boltz 环境；这些修改不代表所有可选评分插件都经过测试。老格式官方 prior 的加载显式指定 `weights_only=False`。所有权重来源和 SHA256 保存在 `audit/manifest.json`。

亲和力编码模型固定到 AgentD `V1` 发布时间之前的公开快照，避免最新远程模型代码与原 Transformers 版本冲突：ProtT5 为 `94a6abc029ae13029317b140b7424e012bf8dfbf`，MoLFormer 为 `7b12d946c181a37f6012b9dc3b002275de070314`。短合成序列测试仅验证推理能运行，不验证生物学预测准确性。

## 运行入口与证据

```bash
cd /data2/chenfuxin/agent_reproduction_20260928
./run_agentd_python.sh --status
# 使用现有 DeepSeek 配置运行自己的 AgentD Python 脚本
./run_agentd_python.sh /absolute/path/to/script.py
```

原有密钥通过 `/data2/chenfuxin/molingo_20260922/private/deepseek_canchen.env` 在运行时读取，没有复制或打印密钥。AgentD 构造时请传入 `model=os.environ['AGENTD_CHAT_MODEL']`。embedding 单独通过 `AGENTD_EMBEDDING_API_KEY`、`AGENTD_EMBEDDING_BASE_URL`、`AGENTD_EMBEDDING_MODEL`、`AGENTD_EMBEDDING_DIM` 配置；联网检索另需 `SERPER_API_KEY`。未静默替换或关闭向量记忆。

`audit/manifest.json` 保存源码版本、权重校验值和测试结果；`audit/patches/` 保存源码修改；`logs/agentd-freeze.txt`、`logs/liddia-freeze.txt` 保存最终环境；`smoke/` 保存生成分子、评分和测试结果。

**复现结论：LIDDIA 存在明确的论文方法实现缺口；AgentD 主体源码较齐全，工具级流程已验证，但完整运行仍取决于 embedding、Serper 等外部服务。用 DeepSeek 替换论文 LLM 后，应标记为适配版本，不能宣称严格复现原始论文结果。**
