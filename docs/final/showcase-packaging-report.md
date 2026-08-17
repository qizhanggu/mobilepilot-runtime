# MobilePilot Repository Showcase Packaging Report

日期：2026-08-17
状态：本地 packaging 完成；远端元数据操作待确认。

本轮只修改展示层、文档和 legacy 说明，没有修改 Agent 行为，没有运行 frozen benchmark，也没有移动 `mobilepilot-v2.2-final`。

## 1. README 第一屏

首页现在以 **MobilePilot — Auditable Android GUI Agent Runtime** 开场，紧接英文/中文定位、核心导航、冻结结果图和可见的 scope disclosure。

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

建议：

> Auditable Android GUI Agent Runtime with structured actions, progress verification, on-demand UI Tree, bounded recovery, and frozen AndroidWorld evaluation.

## 8. Topics

建议：`androidworld`、`android`、`gui-agent`、`mobile-agent`、`ai-agent`、`agent-runtime`、`computer-use`、`vision-language-model`、`adb`、`python`。

## 9. Repository Rename 检查

计划：`qizhanggu/mobile-gui-agent` → `qizhanggu/mobilepilot-runtime`。

- 2026-08-17 只读访问目标 URL 返回 `404 Not Found`，搜索未发现同名公开仓库；仍需在已登录 GitHub 中排除同名私有仓库。
- 旧 URL 搜索只命中 README 的冻结 tag 链接和 rename 清单中的历史对照。
- Rename 后需更新本地 origin 和 README 的 tag URL，并重新检查全部链接。
- GitHub rename 会保留 branches、tags 与 commit history；执行后仍要显式验证冻结 tag 的 commit target。

完整步骤见 [`github-showcase-settings.md`](github-showcase-settings.md)。

## 10. Main Fast-forward 计划

审计结果：

```text
merge-base: bb1a45d616e809387d62d4491deb84304bbcbd45
main...rebuild/after-first-meeting: 0 41
```

`main` 没有独立提交，最终开发分支单向领先 41 个提交。Packaging 提交完成后，计划让 `main` 以 `--ff-only` 前进到 showcase HEAD，不制造 merge commit。`rebuild/after-first-meeting` 暂时保留。

## 11. 验证结果

- Full pytest：`186 passed, 3 warnings`；
- Markdown link checker：仓库 58 个 Markdown 文件的本地目标全部存在；
- 5 个 SVG 均通过 XML 解析并完成 PNG 渲染检查；
- `social-preview.png` 为 `1280×640`；
- stale number 搜索：`170 passed` 和 `7/20` 只出现在明确标注阶段的历史/RCA 文档；最终 README 使用当前 `186 passed` 和冻结结论；
- `mobilepilot-v2.2-final` 仍指向 commit `c48c5fa4682fc2645315998fe169bde45e73eeef`。

## 12. 仍需 GitHub UI / 远端操作

以下均未执行，等待确认：

1. 提交并推送 showcase packaging；
2. fast-forward 并推送 `main`；
3. 将默认分支确认/设置为 `main`；
4. repository rename；
5. 设置 About、Topics；
6. 上传 [`social-preview.png`](../assets/social-preview.png)；
7. 从未登录浏览器验证首页、图片、内部链接、tag 和 clone URL。

当前 `gh` 的本地 token 已失效，所以 About、Topics、Social Preview、默认分支和 rename 需要先重新认证，或在已登录的 GitHub UI 中完成；本报告没有假装这些设置已经生效。

不会删除历史分支，也不会移动或重建 `mobilepilot-v2.2-final`。
