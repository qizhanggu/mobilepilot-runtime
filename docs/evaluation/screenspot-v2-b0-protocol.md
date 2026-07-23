# ScreenSpot-v2 Mobile B0：数据与评分协议核验

日期：2026-07-23

## 固定的数据版本

- 官方仓库：`OS-Copilot/ScreenSpot-v2`
- 固定 commit：`5efbb1f1b5463a575f2eb7bc30fe29e49c15f93c`
- Mobile 标注：`screenspot_mobile_v2.json`
- SHA-256：`fdd1595b64179e31407eed5929fa12e80adc6ba2ee372a3802d36da379ea1825`
- 标注格式：`img_filename`、`bbox`、`instruction`、`data_type`、`data_source`
- `bbox` 语义：像素 `[x, y, width, height]`

本机直连 Hugging Face 超时，因此下载使用兼容镜像，但 URL 固定到上述官方 commit；镜像不参与样本选择或评分。

## 502 与 501 的发布差异

OS-ATLAS 论文和公开数据卡写明 Mobile 共 502 条，但固定版本的官方 Mobile JSON 实际只有 501 条：

| 分类 | 数量 |
| --- | ---: |
| Text | 290 |
| Icon/Widget（JSON 中为 `icon`） | 211 |
| iOS | 238 |
| Android | 211 |
| Shop | 52 |
| 合计 | 501 |

公开的 FiftyOne 转换版 `Voxel51/ScreenSpot-v2@f221b744...` 也只有 501 条 Mobile；使用 instruction、data source、data type 和反归一化 bbox 组成完整签名后，与官方 JSON 逐条精确匹配 501/501。

因此，本轮不会补造第 502 条：30 条 `integration/audit subset` 之后，可审计的主要 held-out 是 471 条。若上游后续补发第 502 条，需要作为数据版本升级单独记录，不能静默并入当前结果。

## 划分

- `integration/audit subset`：30 条，Text 15、Icon 15；iOS、Android、Shop 各 10 条。
- `held_out`：官方发布物剩余 471 条。
- 抽样只依赖固定 seed 与公开字段，不依赖任何模型结果。
- 看到30条结果后只允许修复解析、坐标换算、记录丢失等机械性 Bug；不得修改 Prompt、网格、策略或输出规则。

## Evaluator

OS-Atlas 论文规定主要 Grounding Accuracy：预测位置落入 ground-truth element bounding box 即为正确。官方 OS-Atlas 代码仓库当前没有提供可直接复用的 ScreenSpot-v2 evaluator 脚本，因此本项目没有宣称“直接调用官方脚本”，而是实现同规则的确定性等价 Evaluator：

```text
x <= predicted_x <= x + width
and
y <= predicted_y <= y + height
```

实现包含边界命中、框外拒绝、`[0,1000]` 到原图像素换算和 Text/Icon 分组指标测试。LLM-as-Judge 不参与主要评分。
