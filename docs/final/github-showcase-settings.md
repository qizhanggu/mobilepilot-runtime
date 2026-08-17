# GitHub Showcase 设置清单

这份清单记录展示层完成后需要执行的远端元数据操作。它不属于冻结实验，也不改变 `mobilepilot-v2.2-final`。

## About

建议 Description：

> Auditable Android GUI Agent Runtime with structured actions, progress verification, on-demand UI Tree, bounded recovery, and frozen AndroidWorld evaluation.

建议 Topics：

```text
androidworld
android
gui-agent
mobile-agent
ai-agent
agent-runtime
computer-use
vision-language-model
adb
python
```

Social Preview 文件：[`docs/assets/social-preview.png`](../assets/social-preview.png)。

如果 CLI/API 无法设置，在 GitHub 仓库首页执行：

1. 右侧 **About** 区域点击齿轮，填写 Description 与 Topics。
2. 打开 **Settings → General → Social preview**。
3. 上传 `docs/assets/social-preview.png`，保存后检查桌面与移动端裁剪效果。

当前 `gh auth status` 显示账号 `qizhanggu` 的本地 token 已失效。因此本轮没有通过 CLI 修改任何 GitHub 元数据；执行远端步骤前需要重新登录，或直接使用已登录的 GitHub 网页。

## Repository Rename

计划：

```text
qizhanggu/mobile-gui-agent
→ qizhanggu/mobilepilot-runtime
```

2026-08-17 的只读检查结果：目标 GitHub URL 返回 `404 Not Found`，搜索也没有发现该账号下的同名公开仓库，因此当前看起来可用。404 不能排除同名私有仓库；真正改名前仍应在已登录的 Repository name 输入框中做最后确认。

当前旧 URL 搜索只命中两类预期位置：README 的冻结 tag 链接，以及本清单中的改名前后对照。Rename 完成后应把 README tag 链接改为新 slug；清单中的历史对照可以保留。

执行前检查：

1. 确认目标 slug 当前未被占用。
2. 搜索 README、docs、badge、clone command 与 remote 中的旧 URL。
3. 完成本地 packaging 并保证测试、链接检查和 `git diff --check` 通过。
4. 在 GitHub **Settings → General → Repository name** 中改名。
5. 更新本地 remote：

```bash
git remote set-url origin https://github.com/qizhanggu/mobilepilot-runtime.git
git remote -v
```

GitHub 会保留 branches、tags 和 commit history，并通常为旧仓库 URL 提供重定向；改名后仍要逐条验证 README 链接、clone URL 和 `mobilepilot-v2.2-final`。

## Main 与默认分支

当前审计结果：`main` 没有 `rebuild/after-first-meeting` 之外的独立提交，后者相对 `main` 单向前进。Showcase packaging 在临时分支完成后，计划只做 fast-forward：

```bash
git switch main
git merge --ff-only codex/showcase-packaging
git push origin main
```

随后在 GitHub **Settings → Branches → Default branch** 中确认 `main` 为默认分支。

`rebuild/after-first-meeting` 暂时保留。未经单独确认，不删除历史分支，也不移动 `mobilepilot-v2.2-final` tag。

## 推荐远端执行顺序

1. 审阅本地 packaging diff、测试与 commit graph。
2. 提交并推送 showcase 分支，保留可回退点。
3. Fast-forward `main` 并推送。
4. 确认默认分支为 `main`。
5. 将仓库改名为 `mobilepilot-runtime`，更新 origin 与 README 中的冻结 tag URL。
6. 设置 About、Topics 与 Social Preview。
7. 最后从未登录浏览器打开仓库，验证首页、图片、链接、tag 与 clone 命令。
