# MobilePilot Lab

`MobilePilot Lab` 是 MobilePilot 的可控 Android 测试环境，不是面向用户发布的产品。

它没有网络、登录、支付、相机、个人数据或后端依赖；所有数据都在本地固定生成，用于验证：UI Tree 定位、文本输入、筛选、弹窗处理、任务完成验证，以及“提交前必须停下确认”的安全策略。

## 首个测试任务

> 打开 MobilePilot Lab，搜索咖啡，筛选评分 4.5 以上，并读取前三个结果。

该任务对应的 UI 元素具有明确的 `resource-id`，在 Phase 2 可以验证 UI Tree 优先和视觉 fallback。

## 构建

本机已安装 Android SDK Platform 34、Android Build Tools、Gradle 8.7 与 Android Studio JDK。项目使用 Android Gradle Plugin 8.5.2；首次 Gradle Sync 会从官方源下载 Android Gradle Plugin 及其依赖。

```powershell
cd mobilepilot_lab
# Android Studio: Open → 选择本目录 → Gradle Sync → Run app
```

首次安装到手机前，必须由用户再次确认目标 serial、App package 和安装动作。
