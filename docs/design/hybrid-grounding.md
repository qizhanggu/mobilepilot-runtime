# 视觉主链路与按需 UI Tree 辅助

更新时间：2026-07-22

## 项目定位

MobilePilot 以视觉感知与 VLM 决策为主，UI Tree 按需辅助，真实 Android Runtime 负责执行、验证和恢复。UI Tree-first 路径继续保留为可靠基线与消融对照，但不再被描述为默认产品方向。

## 三种可配置模式

| 模式 | 决策主路径 | UI Tree 作用 | 用途 |
| --- | --- | --- | --- |
| `vision_only` | Screenshot → VLM → 坐标候选 | 不读取 | 测视觉策略本身的能力、延迟和错误点击 |
| `vision_with_tree_aux` | Screenshot → VLM → 坐标候选 | Critic、Verifier、安全检查时按需读取 | 计划中的主要混合模式 |
| `tree_first` | UI Tree 语义定位，缺失时视觉 fallback | Grounding 主路径 | 已完成的可靠基线和消融对照 |

`HybridGrounder` 通过 `GroundingMode` 显式选择模式，并公开 `requires_ui_tree`，让 Runtime 决定是否请求 hierarchy。任何模式产生的都只是候选动作，不能绕过 Critic、执行授权和动作后验证。

## 视觉实验方向

不预设网格一定优于原图。后续在同一受控任务集上比较：

1. 原始截图直接定位；
2. 10×10 网格；
3. 根据手机长宽比或目标密度选择的其他网格；
4. 整屏粗定位 → 局部裁剪 → 精定位；
5. 视觉候选有无 UI Tree 辅助检查。

统一记录任务成功率、错误点击率、模型调用次数、端到端延迟、模型报告的输入/输出 Token；Provider 不返回 Token 时必须标记缺失，不能估算成真实值。

## 当前真实证据

- `tree_first` 已在真机完成三次同任务复跑，证明受控闭环可重复，不代表泛化成功率；
- GUI-Plus 整屏定位 Canvas 控件时曾给出与语义按钮重叠的错误点，被 Critic 拦截；
- 裁剪到目标所在 viewport 后，GUI-Plus 正确定位并触发 UI Tree 不可访问的 Canvas 控件；
- 这只证明视觉 fallback 的一条真实闭环，尚未形成足以比较原图、网格和裁剪策略的数据集。

## 维护原则

- 归一化坐标到物理像素的转换属于 policy/grounding，不放进设备 Adapter；
- ADB 和 `uiautomator2` 只负责观察和执行，不决定使用视觉还是 UI Tree；
- `uiautomator2` hierarchy 只有显式 `include_ui_tree=True` 才读取；
- 视觉主链路不得为了获得更好结果偷偷依赖未记录的 UI Tree；
- `tree_first` 结果必须与视觉模式分开报告。
