# 超星学习通助手 · Android 版

基于 **Chaquopy**（Kotlin + 内嵌 Python 3.11）的原生安卓移植：业务核心 `api/` + `main.py` 与桌面版同源，零复制改动；UI 为 Jetpack Compose（设计规范见 `docs/android-ui-design.md`）。

## 架构

```
Kotlin (Compose UI)                Python (Chaquopy)
┌──────────────────┐   BiConsumer ┌─────────────────────┐
│ MainActivity 3 Tab│────日志回调──▶ android_bridge.py    │
│ StudyService 前台 │              │  ├ core.zip → filesDir/python_core
│ AppState StateFlow│◀──课程/启动──┤  ├ stdout/stderr 接管
└──────────────────┘  callAttr    │  └ input() 自动确认
                                   └─▶ api/ + main.py（与桌面版同源）
```

- **core.zip**：`git archive HEAD` 打包的核心（api + main.py + 字体表），构建前由 `scripts/sync_core.sh` 生成，不直接入库；App 每次启动重新解压（保证随 APK 更新）
- **依赖**：仅纯 Python 包（requests/bs4/fonttools/pyaes/loguru/tqdm/httpx/tenacity）；`openai`（依赖原生 pydantic-core）不可装，代码已守卫导入，AI 题库在安卓版禁用
- **验证码 OCR（ddddocr/onnxruntime）**：安卓版未内置，遇 403 时日志提示（后续可用 onnxruntime-android 桥接 common_old.onnx 补齐）
- **后台**：学习任务运行在前台服务（dataSync 类型），息屏不断；停止 = 结束进程（与桌面版 os._exit 语义一致）

## 构建

```bash
bash scripts/sync_core.sh          # 1. 生成 core.zip（核心有改动后必须）
cd android && ./gradlew assembleDebug   # 2. 构建（首次会下载 Gradle 8.9 + 依赖）
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
```

要求：JDK 17+、Android SDK 35、项目路径含中文时 `android/gradle.properties` 已含 `android.overridePathCheck=true`。

## 与桌面版的差异

| 项 | 桌面 | 安卓 |
|---|---|---|
| GUI | tkinter | Compose Material 3 |
| 验证码 OCR | ddddocr | ❌ 暂无（降级提示） |
| AI 题库 | openai SDK | ❌（守卫禁用） |
| bs4 解析器 | lxml | html.parser（自动回退） |
| loguru enqueue | ✅ | ❌（无 POSIX 信号量，同线程写回退） |
| 检查更新 | ✅ GitHub Releases | ❌ 待加 |

## 已验证（模拟器 Pixel 6 / API 36）

- 构建/安装/启动，三 Tab UI 渲染
- Python 引擎启动 + 核心导入 + config.ini 生成
- 前台服务 + 日志实时推送（时间戳/分级着色）+ 进度解析
- 端到端：真实请求超星服务器登录（假账号按预期返回 LoginError 并回显 UI）
