# 历史离线原型资料

这里保存当前重构不再作为主设计依据、但仍具有追溯价值的竞赛原型文档。

- `docs/architecture.md`：原“截图到下一步动作”决策器架构；
- `docs/experiments.md`：历史 Prompt、图片格式和解析策略实验；
- `docs/failure-analysis.md`：原离线原型的失败案例复盘。

原 `agent.py`、`agent_base.py`、`test_runner.py`、`utils/` 和 `test_data/` 暂时保留在仓库现有位置，因为它们仍是 Phase 0 兼容基线和离线对照的一部分。等新 Runtime 覆盖能力并有迁移测试后，再评估是否通过兼容层归档代码。
