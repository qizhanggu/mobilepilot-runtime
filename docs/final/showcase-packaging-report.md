# MobilePilot Repository Showcase Packaging Report

日期：2026-08-17
状态：Showcase、双语 README、`main`、仓库改名、About、Topics 与 Social Preview 均已完成。

本轮只修改展示层、文档和 legacy 说明，没有修改 Agent 行为，没有运行 frozen benchmark，也没有移动 `mobilepilot-v2.2-final`。

## 1. README 第一屏

`README.md` 现在是面向国内面试场景的中文主版本，以 **MobilePilot — 可审计的 Android GUI Agent Runtime** 开场；`README_EN.md` 完整保留英文版。两边顶部可以直接切换语言，共用同一套架构与证据资产。

第一屏直接展示：

- Frozen paired success：V1 `0/30` → V2.2 `9/30`；
- Invalid-output exits：`21` → `4`；
- UI Tree requests：`209` → `49`；
- Recovery：`3/25` strict rescues；
- Tests：`186 passed`。

同时明确：30 个有效配对来自预冻结 36 题清单，不是 AndroidWorld 总体 30%。

## 2. 架构图

[`architecture.svg`](../assets/architecture.svg) 用一条主链路展示 Goal、Observation、Runtime State、GUI Actor、Protocol Guard、Action Contract、Android、Official Reward、Progress Verifier、Bounded Recovery 和 On-demand UI Tree。

图中强调三条边界：Actor proposes / Runtime decides；official reward authoritative；Recovery limited and evidence-bound。

## 3. Results Visual

[`frozen-results.svg`](../assets/frozen-results.svg) 只展示可复算的 paired metrics，并把分母边界放在图内，没有使用“AndroidWorld accuracy: 30%”。

## 4. Recovery Case Study

[`recovery-case-study.svg`](../assets/recovery-case-study.svg) 根据冻结的 `MarkorDeleteNewestNote` JSONL Trace 重建：

```text
LONG_PRESS → stuck → Tree 找到 Delete → CLICK Delete
→ confirmation stuck → Tree 找到 OK → CLICK OK → official_reward = 1
```

只有第二次 Recovery 标记为 strict rescue。原 Trace 没有保存 Delete/OK 阶段截图，因此没有伪造手机截图。

## 5. 根目录调整

全仓库搜索确认，根目录 `agent.py` 仍被 legacy regression tests 直接 import；`agent_base.py` 与 `test_runner.py` 仍属于竞赛兼容链路。因此没有移动文件，只在三个文件顶部增加醒目的 legacy compatibility 说明。最终 Runtime 仍位于 `mobile_pilot/`。

## 6. Docs Navigation

[`docs/README.md`](../README.md) 已整理为：Start Here、Final Evidence、Architecture & Design、Evaluation、RCA & Negative Results、Development History、Archive。

## 7. About Description

GitHub 已设置为：

> Auditable Android GUI Agent Runtime with structured actions, progress verification, on-demand UI Tree, bounded recovery, and frozen AndroidWorld evaluation.

## 8. Topics

GitHub 已设置：`androidworld`、`android`、`gui-agent`、`mobile-agent`、`ai-agent`、`agent-runtime`、`computer-use`、`vision-language-model`、`adb`、`python`。

## 9. Repository Rename 结果

已完成：`qizhanggu/mobile-gui-agent` → `qizhanggu/mobilepilot-runtime`。

- 改名前通过已认证 API 确认目标 slug 不存在，包括当前账号可见的私有仓库。
- 本地 origin 和 README 的冻结 tag URL 已更新为新 slug。
- `main`、`rebuild/after-first-meeting`、`codex/showcase-packaging` 和冻结 tag 均保留。
- 旧 slug 只在改名前后对照记录中保留。

完整步骤见 [`github-showcase-settings.md`](github-showcase-settings.md)。

## 10. Main Fast-forward 结果

审计结果：

```text
merge-base: bb1a45d616e809387d62d4491deb84304bbcbd45
main...rebuild/after-first-meeting: 0 41
```

`main` 没有独立提交，最终开发分支单向领先 41 个提交。Packaging commit `3d157e3` 创建后，`main` 已通过 `--ff-only` 前进并推送，没有产生 merge commit。`rebuild/after-first-meeting` 继续保留。

## 11. 验证结果

- Full pytest：`186 passed, 3 warnings`；
- Markdown link checker：仓库 59 个 Markdown 文件的本地目标全部存在；
- 5 个 SVG 均通过 XML 解析并完成 PNG 渲染检查；
- `social-preview.png` 为 `1280×640`；
- stale number 搜索：`170 passed` 和 `7/20` 只出现在明确标注阶段的历史/RCA 文档；最终 README 使用当前 `186 passed` 和冻结结论；
- `mobilepilot-v2.2-final` 仍指向 commit `c48c5fa4682fc2645315998fe169bde45e73eeef`。

## 12. GitHub 远端执行状态

已完成：

1. 提交并推送 showcase packaging commit `3d157e3`；
2. fast-forward 并推送 `main`；
3. 将默认分支设置为 `main`；
4. repository rename；
5. 设置 About 与 Topics；
6. 更新本地 origin。

7. 上传双语 [`social-preview.png`](../assets/social-preview.png)，并在 GitHub 设置页确认最终裁剪效果。

最终封面保留英文项目名与技术定位，增加“可审计 · 可恢复 · 可冻结评测”中文价值说明；分母边界也直接写在图中。

不会删除历史分支，也不会移动或重建 `mobilepilot-v2.2-final`。
