# 超星学习通助手 · Android UI 设计规范

Platform: Android (Jetpack Compose, Material 3) · 品牌延续桌面版蓝白卡片风 · 2026-10

## 1. 设计令牌 (Design Tokens)

### 色彩（浅色主题）
| Token | 值 | 用途 |
|---|---|---|
| `primary` | #1E3A8A | 顶栏、主强调、选中态 |
| `onPrimary` | #FFFFFF | 顶栏文字 |
| `secondary` | #2563EB | 主按钮（开始任务）、链接、进度条 |
| `onSecondary` | #FFFFFF | 主按钮文字 |
| `background` | #F5F7FA | 页面底 |
| `surface` | #FFFFFF | 卡片 |
| `onSurface` | #1F2937 | 正文 |
| `onSurfaceVariant` | #6B7280 | 次要文字/提示 |
| `outline` | #E2E8F0 | 卡片描边、分隔线 |
| `success` | #16A34A | 运行中状态点、成功日志 |
| `warning` | #D97706 | 警告日志、有新版本 |
| `error` | #DC2626 | 停止按钮、错误日志 |
| `logBg` | #0F172A | 日志控制台背景 |
| `logFg` | #E2E8F0 | 日志正文（深底浅字，对比度 ≥ 12:1）|

深色日志控制台嵌浅色页面（延续桌面版），其余组件走 Material 3 浅色方案；对空/错/载状态全部落到 surface 卡片内呈现。

### 字体与字号（系统默认 Roboto / 中文回退）
| Token | 值 |
|---|---|
| `displaySmall` | 20sp / 600（页标题）|
| `titleMedium` | 16sp / 600（卡片标题）|
| `bodyLarge` | 15sp（表单值）|
| `bodyMedium` | 14sp（正文）|
| `labelSmall` | 11sp（辅助、计数徽标）|
| `mono` | 13sp Monospace（日志、课程 ID）|

### 间距 / 圆角 / 阴影
- 间距梯度（dp）：4 · 8 · 12 · 16 · 24；页面水平 padding 16，卡片内 padding 16
- 圆角：卡片 16dp，按钮/输入框 12dp，徽标 999dp
- 阴影：无（描边 outline 1dp 替代），按压 `surfaceVariant` 变化反馈

### 触控与无障碍
- 所有可点目标 ≥ 48dp；复选列表行高 56dp
- 主行动区（开始/停止）固定底部，不随键盘滚动
- 对比度：正文 ≥ 4.5:1，大字 ≥ 3:1（上表已满足）；日志色 success #4ADE80 于 #0F172A ≈ 9:1
- 状态除颜色外必带文字（色弱可辨）：状态点 + 汉字状态词成对出现

## 2. 信息架构与屏幕流

单 Activity + 底部导航 3 Tab：

```
┌──────────────────────────────────────────┐
│ 顶栏：超星学习通助手 v1.0.0（primary 深蓝） │
├──────────────────────────────────────────┤
│                                          │
│           当前 Tab 内容（可滚动）           │
│                                          │
├──────────────────────────────────────────┤
│ [📚 课程]  [⚙️ 设置]  [▶️ 运行]            │ ← NavigationBar
└──────────────────────────────────────────┘
```

### Tab 1 课程（首屏）
- **登录卡片**：手机号（数字键盘）、密码（显隐切换）、cookies.txt 开关；主按钮「获取课程列表」
- **课程卡片**：加载态（骨架行）/ 空态（提示文案 + 重试引导）/ 数据态（复选列表，行 = 课名 + 班级副行 + 右侧复选框）；顶行工具条 = 全选 / 清空 / 「全部课程」开关 / 已选 N 门徽标
- 错误态：卡片内红字 + 重试按钮（不弹全局对话框）

### Tab 2 设置
分组卡片（延续桌面版）：播放与并发（倍速下拉 1.0–2.0 / 并发 1–16 / 关闭处理 / 重试间隔）· 章节检测（重做开关+次数）· 学习次数（开关+目标）· 题库（provider 下拉 / token 密文 / 自动提交 / 覆盖率 / 间隔）
- 数值输入失焦即校验，非法红框 + 行内提示

### Tab 3 运行
- 状态头卡片：状态点(●颜色) + 状态词 + 已运行 mm:ss + 线性进度条（tqdm 百分比驱动，无百分比时流动动画）
- 操作区：底部固定「▶ 开始任务」（secondary 实心）/「■ 停止」（error，运行时才出现）
- 日志控制台：logBg 深底，等宽字体，行 = 灰时间戳 + 彩色正文，自动滚到底（上滑即暂停跟随），复制按钮
- 运行中启动前台服务通知（不可滑掉），返回桌面任务继续

### 关键用户旅程
1. 首次：课程 Tab 填账号 → 获取课程（loading 骨架）→ 勾选 → 运行 Tab → 开始 → 看日志 → 完成（状态点变蓝 + 通知）
2. 复用：课程列表缓存于本地（config），直接运行 Tab 开始
3. 更新：启动静默查 GitHub Release，有新版顶栏出现「新版本」徽标，点击跳浏览器

### 空 / 载 / 错清单
| 场景 | 呈现 |
|---|---|
| 课程未加载 | 空态卡：「先在上方登录并获取课程，或到设置填写课程 ID」 |
| 获取中 | 骨架 4 行 + 按钮转圈禁用 |
| 登录失败 | 卡片内 error 行（登录失败原因），密码框保留 |
| 任务崩溃 | 状态点红 + 「已异常结束」+ 日志尾部自动定位错误行 |
| 无网络 | 启动检查更新静默失败（不提示）；获取课程报连接错误行内提示 |

## 3. 组件规范（Compose 落地映射）
- 卡片 = `Card(outline 边框, 16dp 圆角, surface 底)`
- 主按钮 = `Button(containerColor=secondary, 12dp 圆角, 高 48dp)`
- 危险按钮 = 同上容器 error
- 输入项 = `OutlinedTextField(12dp, label 上浮)`
- 状态点 = `Box(10dp 圆) + Spacer(8dp) + Text(状态词)`
- 日志行 = `Row { Text(HH:mm:ss, #64748B, mono 11sp); Text(正文, level 色, mono 13sp) }`
- 课程行 = `Row(56dp) { Column{课名 bodyLarge; 班级 labelSmall 灰}; TrailingCheckbox }`

## 4. 技术约束备忘
- Python 核心经 Chaquopy 嵌入（api/ + main.py 原样 vendor，仅 2 处兼容补丁：bs4 解析器自适应、openai 守卫导入）
- 文件落点 `filesDir`（config.ini / cookies.txt / 日志），首启拷贝 resource/font_map_table.json
- 长任务跑在 Foreground Service（dataSync 类型）线程；日志 Python→Java 回调推送，Kotlin StateFlow 驱动 UI
- 分发走 GitHub Releases APK（复用检查更新机制）
