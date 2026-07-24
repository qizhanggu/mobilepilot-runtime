# ScreenSpot-v2 Mobile B4：471 条 Held-out 正式评测

日期：2026-07-24

## 结论先行

本轮在固定的 ScreenSpot-v2 Mobile 发布版本上完成了 471 条未参与接入调试的 held-out 样本，每条分别运行 Raw 与冻结 10×10 网格，共 942 次 pass@1 逻辑调用。

主要结论是：**Raw 在该固定 GUI-Plus 配置下呈趋势性更好，但差异未达到统计显著；10×10 没有复现自建受控任务集上的优势。**

| 配置 | 整体准确率 | Text | Icon/Widget | 无效输出率 | 框外点击率 | 平均延迟 | 已知 Token | 调用 | 已知目录价 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Raw vision-only | 332/471（70.49%） | 206/275（74.91%） | 126/196（64.29%） | 110/471（23.35%） | 29/471（6.16%） | 4.289s | 1,491,320 | 471 | ¥2.389992 |
| 10×10 vision-only | 314/471（66.67%） | 194/275（70.55%） | 120/196（61.22%） | 123/471（26.11%） | 34/471（7.22%） | 4.378s | 1,483,450 | 471 | ¥2.370819 |

10×10 相对 Raw 低 3.82 个百分点。配对结果为：两者都成功 253 条、仅 Raw 成功 79 条、仅 10×10 成功 61 条、两者都失败 78 条。Exact McNemar 双侧检验 `p=0.1505`，因此不能声称 Raw 或网格具有统计显著优势。

## 实验冻结条件

- 模型：`gui-plus-2026-02-26`；
- Prompt、解析器、归一化坐标换算和 point-in-bbox Evaluator 与 B2/B3 相同；
- 图像配置只有 `raw__vision_only` 与 `grid_10x10__vision_only`；
- 网格只作为视觉参考，模型仍输出 `[0,1000]` 精确坐标，不限制在网格中心；
- SDK 隐式重试关闭，单样本不重试；
- held-out manifest 固定为 471 条，SHA-256 为 `719cdb167c12d3416499c0cf70dfbac480c142dd0e56b6a52f9ada52d322021d`；
- 最大逻辑调用数 942，目录价硬上限 ¥6；
- 本阶段不连接真机、不部署 AndroidWorld。

官方仓库没有提供可直接调用的独立 Evaluator 脚本，本项目继续使用经过边界测试的确定性等价实现：预测点落入官方 `bbox` 即命中，不使用 LLM-as-Judge。

## 配对比较

| 配对结果 | 数量 |
| --- | ---: |
| Raw 与 10×10 都成功 | 253 |
| 仅 Raw 成功 | 79 |
| 仅 10×10 成功 | 61 |
| 两者都失败 | 78 |

- Raw：70.49%；
- 10×10：66.67%；
- 差值（10×10 - Raw）：-3.82 个百分点；
- 不一致配对：140；
- Exact McNemar 双侧 `p=0.1505276972`。

这个结果说明网格既能纠正部分 Raw 错误，也会干扰另一些原本正确的 Raw 样本；在当前固定 Prompt 与模型下，负向配对比正向配对多 18 条，但证据不足以判定总体存在显著差异。

## 501 条当前发布物补充汇总

以下结果合并了 30 条曾用于接入审计的 integration/audit subset 与 471 条 held-out，仅作为补充；项目主要结论以上述 471 条为准。

| 配置 | 整体 | Text | Icon/Widget | 无效输出率 | 已知 Token | 已知目录价 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Raw | 353/501（70.46%） | 218/290（75.17%） | 135/211（63.98%） | 117/501（23.35%） | 1,584,188 | ¥2.539014 |
| 10×10 | 337/501（67.27%） | 207/290（71.38%） | 130/211（61.61%） | 128/501（25.55%） | 1,583,206 | ¥2.529792 |

501 条配对结果为 270 条都成功、83 条仅 Raw 成功、67 条仅网格成功、81 条都失败，Exact McNemar 双侧 `p=0.2205`。这仍然不能替代 471 条 held-out 主结果。

## 调用、Token、成本与完整性

- held-out 共 942 条终态记录，942 个 `(sample_id, config)` 唯一配对，零重复、零缺失；
- 已返回 usage 的调用合计 2,974,770 Token，目录价估算 ¥4.760811；
- 3 条 Raw 与 5 条网格记录没有 usage，因此 Token 和费用是可审计下界，最终账单以百炼控制台为准；
- 7 条请求是 `MODEL_ERROR`，均作为真实失败保留且未重试；
- Raw 平均延迟 4.289 秒；10×10 排除下述丢失记录后的平均延迟 4.378 秒；
- 评分结果由官方标注框确定，不根据模型解释文字或人工判断修改。

### 第 730 次调用的机械性记录故障

`mobile-0382-29c94fe87b / grid_10x10__vision_only` 的模型调用已经发生，但 Runner 在响应写入 JSONL 前逐条执行本地 `git rev-parse HEAD`，该 Git 子进程异常退出，因此原始响应、usage 和真实延迟无法恢复。

处理方式：

1. 该配对直接记为失败；
2. 不重新调用该样本，不给模型第二次机会；
3. 将 Git commit 改为进入模型循环前读取一次；
4. Prompt、模型、网格、Parser、坐标换算与 Evaluator均未修改；
5. 修复前后源文件哈希和事件证据保存在 `mechanical_patch_freeze.json` 与 `mechanical_change_log.json`。

该事件最多影响 1/471，即 0.21 个百分点。即使把它假设为正确，10×10 也只有 315/471（66.88%），仍低于 Raw 的 70.49%，不改变本轮结论。

## 典型案例

### 网格纠正 Raw

`mobile-0000-32207e9d2d`，指令 `check the weather`，Icon：

- Raw 返回缺少有效点击参数的工具调用，记为无效输出；
- 10×10 预测 `[280,168]`，落入目标框并命中。

这说明网格在个别复杂桌面布局中能提供额外空间参照，但该收益不能外推到整体。

### 网格干扰 Raw

`mobile-0003-7bb9ce9f58`，指令 `open the camera`，Text：

- Raw 预测 `[1994,883]` 并命中；
- 10×10 对目标理解正确，但输出缺少冻结协议要求的 `action` 字段，记为无效输出。

这里的差异来自输出稳定性，而不是单纯的视觉定位精度。

### 两者共同失败

`mobile-0004-043666d223`，指令 `view the menu`，Icon：

- Raw 与10×10都把点击点定位到屏幕右上方；
- 官方目标框实际位于左上方；
- 两者均为合法坐标但框外点击，属于真实 grounding 错误。

### Text 与 Icon 差异

两种配置在 Text 上都明显优于 Icon：

- Raw：Text 74.91%，Icon 64.29%；
- 10×10：Text 70.55%，Icon 61.22%。

当前 GUI-Plus Actor 对小图标、空间语义和相似控件的区分仍是主要薄弱点；10×10 没有缩小这一差距。

## 与自建实验的关系

此前自建受控任务集中，10×10 纯视觉为 24/24；该结果继续有效，但只代表受控任务上的消融表现。公开 held-out 中 Raw 反而呈趋势性更好，证明不能把自建任务重复成功包装成公共界面泛化能力。

因此项目表述应调整为：

> MobilePilot 建立了可审计的视觉预处理对照与真实 Android Runtime；10×10 网格在自建受控任务中有效，但在 ScreenSpot-v2 Mobile 的 471 条 held-out 上没有带来显著收益。

模型本身完成的大部分 grounding 能力不能全部归因于 MobilePilot；本轮框架贡献主要是冻结协议、预处理消融、确定性评分、失败审计、成本门禁和可复现运行。

## 产物路径

- 逐样本记录：`artifacts/evaluation/screenspot-v2-20260723/held-out/runs.jsonl`
- held-out 汇总：`artifacts/evaluation/screenspot-v2-20260723/held-out/summary.json`
- 配对检验：`artifacts/evaluation/screenspot-v2-20260723/held-out/paired_outcomes.json`
- 完整性审计：`artifacts/evaluation/screenspot-v2-20260723/held-out/integrity_audit.json`
- 机械故障记录：`artifacts/evaluation/screenspot-v2-20260723/held-out/mechanical_change_log.json`
- 501 条汇总：`artifacts/evaluation/screenspot-v2-20260723/release-501/release_report.json`
- 典型可视化：`artifacts/evaluation/screenspot-v2-20260723/held-out/visualizations/`

## 下一阶段建议

本阶段按要求暂停，不部署 AndroidWorld。下一步只建议进行 AndroidWorld 接口接入设计与小规模环境验证，不再继续搜索网格参数；若要比较 `gui-plus` 主版本，应建立独立模型版本实验，使用与本轮不同的实验名称和预算，不能覆盖本轮快照结果。
