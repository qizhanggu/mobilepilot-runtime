# 公共 Benchmark 阶段进展：B4 Held-out

## 本阶段解决了什么

完成 ScreenSpot-v2 Mobile 当前固定发布物中 471 条未参与接入调试的 held-out 正式评测。Raw 与冻结 10×10 各运行一次，共 942 次 pass@1 逻辑调用；不连接真机，不使用 LLM-as-Judge。

## 真实结果

- Raw：332/471，70.49%；
- 10×10：314/471，66.67%；
- 差值（10×10 - Raw）：-3.82 个百分点；
- 配对结果：都成功253、仅Raw成功79、仅网格成功61、都失败78；
- Exact McNemar 双侧 `p=0.1505`，差异不显著；
- 已知 2,974,770 Token，目录价约 ¥4.760811；
- 942 条终态记录、942 个唯一配对，零重复、零缺失。

结论：10×10 在公开 held-out 上没有复现自建受控任务集优势；Raw 呈趋势性更好，但差异不显著。自建实验继续作为消融证据，不能写成公共泛化成功率。

## 关键模块和产物

- 独立 held-out 入口：`mobile_pilot/evaluation/screenspot/held_out_runner.py`
- 配对统计：`mobile_pilot/evaluation/screenspot/statistics.py`
- 501 条补充汇总：`mobile_pilot/evaluation/screenspot/release_reporting.py`
- 完整报告：`docs/evaluation/screenspot-v2-b4-held-out.md`
- 原始 JSONL、汇总和可视化：`artifacts/evaluation/screenspot-v2-20260723/held-out/`

## 故障与处理

第730次模型调用后，本地 Git 辅助命令在写入记录前异常退出。该配对按失败处理且未重试；修复只把提交号改为循环前读取一次，没有修改模型、Prompt、网格、解析、坐标换算或 Evaluator。完整证据保存在评测目录。

## 当前能否运行

可以。图片、manifest、冻结哈希、成本上限、断点续跑和统计链路均已验证；全量自动化测试67项通过。本阶段不依赖手机或 Android 模拟器。

## 下一步

按批准边界在B4结束后暂停，不部署AndroidWorld。后续先形成AndroidWorld Agent接口映射与10个代表性任务清单，再单独审批环境部署。
