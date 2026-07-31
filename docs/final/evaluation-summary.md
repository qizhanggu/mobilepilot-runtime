# MobilePilot 实验结果总表

| 层级 | 数据与规模 | 主结果 | 可说/不可说 |
| --- | --- | --- | --- |
| 自建受控实验 | 8任务×7配置×3次=168 runs | 10×10 pure vision 24/24 | 可解释网格在测试 App 中有效；不可称泛化成功率。 |
| ScreenSpot-v2 Mobile | 471 held-out×Raw/Grid | Raw 70.49% (332/471)，Grid 66.67% (314/471) | 可说已完成公开单步评测；不可称网格优于原图。 |
| AndroidWorld | 固定20题×2模式=40 runs | vision_only 5/20，hybrid 4/20，McNemar p=1.0 | 可说多步 Runtime 已接入官方 reward；不可称完整116类成绩或混合更优。 |

完整协议与审计路径分别见 `docs/evaluation/screenspot-v2-b4-held-out.md` 与 `docs/progress/androidworld-sprint4-heldout.md`。
