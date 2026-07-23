# 公共 Benchmark 阶段进展：B0–B3

## 本阶段解决了什么

MobilePilot新增了不依赖真机Runtime的ScreenSpot-v2 Mobile适配层，能够固定数据版本、划分审计集、调用同一个GUI-Plus Actor、保存原始响应，并用确定性标注框判断预测点是否正确。

## 关键模块

- `mobile_pilot/evaluation/screenspot/dataset.py`：官方JSON解析、固定划分和图片映射；
- `preprocess.py`：Raw及三种网格，保持原图尺寸；
- `evaluator.py`：point-in-bbox与Text/Icon分组统计；
- `runner.py`：断点续跑、调用预算、原始响应和Token记录；
- `reporting.py`：JSON/CSV和成功/失败可视化；
- `grid_development.py`：私有开发集唯一网格冻结。

## 测试与实际运行

- 自动化测试：64项通过；
- B1：8个私有开发任务 × 3种网格 × 3次，共72条记录；
- B2：30条ScreenSpot integration/audit样本 × Raw/10×10，共60条记录；
- Raw 21/30，10×10 23/30；仅表示审计子集结果。

## 产物

- `artifacts/evaluation/grid-development-20260723/`
- `artifacts/evaluation/screenspot-v2-20260723/`
- `docs/evaluation/screenspot-v2-b0-protocol.md`
- `docs/evaluation/grid-development-b1-2026-07-23.md`
- `docs/evaluation/screenspot-v2-b3-integration-audit.md`

## 已知问题与边界

- 论文报告502条Mobile，但官方固定发布JSON只有501条，因此held-out为471条；
- 官方仓库未发布可直接调用的ScreenSpot evaluator脚本，本项目使用同规则等价实现；
- 模型存在非法JSON、坐标点偏和API超时；
- 30条审计子集不是完整Benchmark，也不用于继续调参；
- AndroidWorld未部署。

## 下一步

当前在B3暂停。只有获得批准后，才运行471条未用于调试的held-out，并将模型能力与MobilePilot图像预处理影响分开解释。
