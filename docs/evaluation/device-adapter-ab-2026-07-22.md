# DeviceAdapter 真机 A/B：ADB 与 uiautomator2

日期：2026-07-22

## 目的与边界

验证 `uiautomator2` 是否适合作为 Unicode 输入、控件等待和按需 UI Tree 的执行能力补充。测试只操作 `com.mobilepilot.lab`，显式绑定一台已授权 Android 16 真机；没有操作其他 App，也没有点击模拟提交按钮。

## 环境

- Python 客户端：`uiautomator2 3.7.0`；
- 设备分辨率：1260×2800；
- ADB：当前 `ADBDeviceAdapter` 的 `/dev/tty` 尝试 + 随机临时 XML 回退；
- uiautomator2：`dump_hierarchy(compressed=False)`，只有调用方要求时读取。

## 结果

| 项目 | ADB | uiautomator2 | 结论 |
| --- | ---: | ---: | --- |
| 中文输入“咖啡” | Android `input text` 抛出 `NullPointerException`，输入框未改变 | 约 0.18 秒，写入并读回“咖啡” | uiautomator2 解决当前设备的 Unicode 输入问题 |
| 控件等待 | Runtime 自行轮询 UI dump | 目标输入框等待约 0.06 秒 | 可作为按需能力使用 |
| UI Tree，10 次平均 | 5.4799 秒 | 0.0759 秒 | uiautomator2 约快 72 倍 |
| UI Tree，观测范围 | 4.8944～10.1461 秒 | 0.0578～0.0937 秒 | ADB 临时 XML 是显著瓶颈 |
| 同一五步任务，3 次 | 56.96、56.66、56.17 秒 | 16.69、17.55、15.97 秒 | 平均从约 56.60 秒降至约 16.74 秒，缩短约 70.4% |
| 五步任务结果 | 3/3，每次 5/5 | 3/3，每次 5/5 | 只描述重复运行稳定性，不是泛化成功率 |

端到端没有达到 hierarchy 单项的 72 倍提升，因为一轮任务还包含截图、设备元数据、点击、输入和多次 Verifier 观察。该结果说明应进一步减少不必要观察，但不构成继续扩建 UI Tree 架构的理由。

## 决策

1. 保留 ADB 作为基础连接、Shell 与可回退执行通道；
2. 增加 `Uiautomator2DeviceAdapter`，用于 Unicode 输入、控件等待和按需 hierarchy；
3. UI Tree 读取保持 opt-in，不进入 `vision_only` 主链路；
4. 不继续围绕 UI Tree 重构底层，下一项工程工作转向视觉主链路与受控视觉任务集；
5. 后续视觉实验必须分别记录 `vision_only`、`vision_with_tree_aux`、`tree_first`，不能混合结果。

## 可复核产物

- ADB Trace：`artifacts/traces/phase3-lab-run-01.jsonl` 至 `03`；
- uiautomator2 Trace：`artifacts/traces/phase3-u2-lab-run-01.jsonl` 至 `03`；
- 新 Adapter：`mobile_pilot/device/uiautomator2.py`；
- 网络无关回归：49 passed。
