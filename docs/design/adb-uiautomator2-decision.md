# ADB / uiautomator2 决策记录

更新时间：2026-07-22

## 当前结论

重评估门已经执行。保留 ADB 基础通道，并增加 `Uiautomator2DeviceAdapter` 作为 Unicode 输入、控件等待和按需 UI Tree 的补充；它不决定感知路线，也不能绕过 Critic、Verifier 或后续 Safety Gate。

## 已获得的真实证据

| 项目 | 真实结果 | 结论 |
| --- | --- | --- |
| 设备绑定 | 测试设备 serial 可显式指定 | 满足避免误操作的最低要求 |
| 截图与 Activity | 三次端到端任务均可读取 | 当前稳定 |
| UI Tree | `/dev/tty` 不可用，随机临时 XML 回退可用且会清理 | 功能可用，但明显偏慢 |
| 页面等待 | 单次读取曾把已出现弹窗误判为失败；有限轮询随后正确识别 | Runtime 必须保留 Verifier 轮询，不能依赖固定 sleep |
| ASCII 输入 | `adb shell input text coffee` 成功，页面读回 `coffee` | 可支撑当前基准 |
| 中文输入 | ADB 失败；uiautomator2 约 0.18 秒写入并读回 `咖啡` | 使用 uiautomator2 补充 Unicode 输入 |
| UI Tree | ADB 10 次平均 5.4799 秒；uiautomator2 平均 0.0759 秒 | hierarchy 仅按需使用 uiautomator2 |
| 端到端耗时 | ADB 三次平均约 56.60 秒；uiautomator2 三次平均约 16.74 秒 | 同一受控任务缩短约 70.4% |

## 为什么现在值得引入对照、但不直接替换

`uiautomator2` 已实现同一 `DeviceAdapter` 边界。视觉策略不直接依赖 selector；不需要 UI Tree 时，`observe(include_ui_tree=False)` 不读取 hierarchy。

## 对照实验验收结果

1. 只操作 `com.mobilepilot.lab` 并明确绑定 serial：通过；
2. 中文 `咖啡` 写入并由 UI Tree 读回：通过；
3. 连续 10 次 hierarchy 读取无失败：通过；
4. 同一五步任务运行 3 次并比较耗时：通过；
5. ADB Adapter 保持可用：通过；
6. selector 未泄漏到 Planner/Runtime：通过。

## 当前边界

结论只对本设备、当前版本和 `MobilePilot Lab` 有效。它证明 Unicode 输入问题在该环境得到解决、受控任务明显加速，但不能外推为所有 Android 设备或任意 App 的稳定性。
