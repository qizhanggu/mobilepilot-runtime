# 测试目录说明

| 目录 | 范围 |
| --- | --- |
| [legacy/](legacy/) | 原离线竞赛原型的动作解析、视觉网格和坐标后处理测试。 |
| [mobile_pilot/](mobile_pilot/) | 本次重构新增的协议兼容、设备 Adapter、Runtime 等测试。 |

统一运行命令：

```powershell
python -m pytest -q
```

真机或模拟器集成测试将单独标记，默认不运行，避免误操作用户设备。
