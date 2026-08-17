# GitHub Showcase 设置清单

这份清单记录展示层完成后的远端元数据操作。它不属于冻结实验，也不改变 `mobilepilot-v2.2-final`。

执行状态（2026-08-17）：仓库已改名为 `qizhanggu/mobilepilot-runtime`，默认分支已设为 `main`，About、Topics 与双语 Social Preview 已设置，本地 origin 已更新。

## About

已设置 Description：

> Auditable Android GUI Agent Runtime with structured actions, progress verification, on-demand UI Tree, bounded recovery, and frozen AndroidWorld evaluation.

已设置 Topics：

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

`gh auth status` 中的 CLI token 已失效；仓库元数据最终通过 Git Credential Manager 中已可用于 `git push` 的凭证调用 GitHub 官方 API 设置，凭证没有输出或写入文件。Social Preview 通过已登录的 GitHub 网页上传。

## Repository Rename

计划：

```text
qizhanggu/mobile-gui-agent
→ qizhanggu/mobilepilot-runtime
```

2026-08-17 的只读检查结果：目标 GitHub URL 返回 `404 Not Found`，搜索也没有发现该账号下的同名公开仓库，因此当前看起来可用。404 不能排除同名私有仓库；真正改名前仍应在已登录的 Repository name 输入框中做最后确认。

改名后的旧 URL 搜索只保留本清单和 packaging report 中的改名前后文字对照；README 的冻结 tag 链接已更新为新 slug。

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

审计确认 `main` 没有 `rebuild/after-first-meeting` 之外的独立提交，后者相对 `main` 单向前进。Showcase packaging 已按以下方式完成 fast-forward：

```bash
git switch main
git merge --ff-only codex/showcase-packaging
git push origin main
```

GitHub 默认分支已经设为 `main`。

`rebuild/after-first-meeting` 暂时保留。未经单独确认，不删除历史分支，也不移动 `mobilepilot-v2.2-final` tag。

## 实际远端执行顺序

1. 审阅本地 packaging diff、测试与 commit graph。
2. 提交并推送 showcase 分支，保留可回退点。
3. Fast-forward `main` 并推送。
4. 确认默认分支为 `main`。
5. 将仓库改名为 `mobilepilot-runtime`，更新 origin 与 README 中的冻结 tag URL。
6. 设置 About 与 Topics。
7. 开启 Edge 扩展“允许访问文件网址”权限，上传双语 Social Preview 并检查裁剪。
8. 核对首页、图片、链接、tag 与 clone URL。
