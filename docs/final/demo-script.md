# MobilePilot Demo 与三分钟讲解脚本

## 运行边界

- 只连接 AndroidWorld `emulator-5554`；
- 不连接真实手机，不操作 VMware；
- AndroidWorld commit 固定 `3e50888527ef9f29b9157ecd537e408008bb1c85`；
- Actor 固定 `gui-plus-2026-02-26`；
- 冻结 36 题已经产生结果，**不要在面试 Demo 中重跑或挑题重试**。

## 推荐 Demo：离线 Trace 回放

这是面试最稳的方式：不依赖 API、网络和模拟器状态，也不会污染冻结证据。

```powershell
# 1. 看最终结果和结论边界
Get-Content docs/final/frozen-evaluation-report.md

# 2. 看真实 Recovery 救回
$trace='artifacts/evaluation/androidworld-v22-final-frozen36-20260817/traces/MarkorDeleteNewestNote--v2.2--hybrid.jsonl'
rg -n 'LONG_PRESS|agent_recovery_triggered|ui_tree_decision|agent_recovery_replan|official_reward|agent_recovery_outcome' $trace

# 3. 看 ANSWER 官方通道
$answerTrace='artifacts/evaluation/androidworld-v22-final-frozen36-continuation5-network-restored-20260817/traces/SimpleCalendarAnyEventsOnDate--v2.2--hybrid.jsonl'
rg -n 'ANSWER|official_reward' $answerTrace

# 4. 离线测试
python -m pytest -q
```

预期测试结果：`186 passed`。

## 可选：启动 AndroidWorld 模拟器

只有需要展示页面时再启动。不要改 Hyper-V/VMware 配置；当前命令只启动 Android Emulator。

```powershell
$emulator='C:\Users\Admin\AppData\Local\Android\Sdk\emulator\emulator.exe'
Start-Process -FilePath $emulator -ArgumentList @(
  '-avd','AndroidWorldAvd','-port','5554','-grpc','8554','-no-snapshot-save'
)

$adb='C:\Users\Admin\AppData\Local\Android\Sdk\platform-tools\adb.exe'
& $adb devices
```

必须只看到：

```text
emulator-5554    device
```

## 三分钟讲解

### 0:00—0:30：问题

> V1 的 40 条运行只有 9 条成功，31 条失败里 21 条是非法 Actor 输出。但我继续看 Trace 后发现，真正问题不只是 JSON：Runtime 还缺 long press、drag、answer，旧状态会污染新 subgoal，Recovery 经常没有新证据。

### 0:30—1:20：架构

> 我把 GUI-Plus 收窄成 action-only；Runtime 维护 subgoal 和 completion evidence；确定性 Verifier 每步跑，只有语义不确定时才调用 Qwen；UI Tree 从每步输入改成失败事件触发；Recovery 最多两级，而且必须基于新证据换动作。最终成功只认 AndroidWorld official reward。

### 1:20—2:10：Trace

打开 `MarkorDeleteNewestNote`：

> Actor 先执行新增 LONG_PRESS；页面重访后，Recovery 从 Tree 找到 Delete；确认框出现后第二级 Recovery 找到 OK；执行后 reward 从 0 变 1。这里每一步的 blocked action、chosen element、changed action 和 rescue 都在 JSONL 中。

再打开 Calendar ANSWER：

> 这条成功不是 Recovery，而是补齐 AndroidWorld information retrieval 的正式答案通道。协议能力和 Agent 恢复要分开归因。

### 2:10—3:00：结果与边界

> 36 题冻结清单中，30 题形成有效配对：V1 0/30，V2.2 9/30，9 改善 0 退化；非法输出 21 降到 4；Recovery 25 次只救回 3 次；UI Tree 209 降到 49。6 题因为 OsmAnd 目录或 Windows SQLite FTS4 不进入分母。21/30 仍失败，所以我不会说 Runtime 已解决复杂长任务。

## 面试前检查

- README、冻结报告、面试手册数字均为 30 个有效配对；
- 不把开发 20 题称 held-out；
- 不把 9 个成功都归因于 Recovery；
- 不把 6 个环境无效任务算 Agent failure；
- 能解释为什么 V2.2 调用/Token/延迟更高；
- 能在 Trace 中找到 official reward=1 和 rescued=true。
