# AndroidWorld Sprint 9B：基础设施中断后的重新冻结

日期：2026-08-04

## 为什么没有继续原批次

首个冻结批次运行到 `MarkorCreateNoteFromClipboard--v1--hybrid` 时，AndroidWorld
在模型调用前下载 Accessibility Forwarder APK，远端 TLS 连接异常中断。Runner
按冻结规则写入 `infrastructure_error` 并永久禁止自动重试或继续该目录。

中断前共有 10 条有效运行，VLM 41 次，估算目录价 ¥0.2367；另有 1 条零模型调用
的基础设施错误。这批产物完整保留在
`artifacts/evaluation/androidworld-v2-frozen-20260804/`，不作为最终 12 题成绩。

没有删除错误行、伪造跳过记录、修改旧产物或重跑失败任务。

## 第二批如何保持未见性

新清单为 `configs/androidworld/runtime_eval_12_v2b.json`：

- 保留原清单中尚未启动的后 6 题；
- 从 registry 按交互面补入 6 个此前未出现在配置、文档或实验产物中的任务；
- 将首批中已经开始环境设置或模型调用的 6 题全部列入排除项；
- 不依据首批的成功或失败结果选择新任务。

因此第二批 12 题在冻结时都没有被 MobilePilot 运行过。它不是对首批失败题的重试。

## 第二次冻结值

- task hash：`1d834038980e7a34a8342e3abe291025f7cf1064070672718e00f41c50f4a449`
- Agent 源码 hash：
  `456cf27698409fedd3b093f7398743f747c9bce24dea754bc332fefdd50a1194`
- V1/V2、模型、Prompt、seed、步数、mode、指标与首批完全一致
- 最大 VLM 逻辑调用：350；本批目录价硬上限：¥12

第二批冻结后同样不根据结果修改策略。若再次发生基础设施错误，继续保留并如实报告，
不通过单题重试补齐成绩。
