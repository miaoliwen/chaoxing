#!/usr/bin/env bash
# 一键打包 macOS 版 chaoxing 并生成 DMG
# 用法: bash scripts/build_mac_dmg.sh [arm64|x86_64]
#   - 在任意 Mac 上可直接运行(Mac 上不传参数会自动探测本机架构)
#   - 在 GitHub Actions 的 macos-15 / macos-15-intel 云端 runner 上同样可用
# 产物: <项目根>/chaoxing-macos-<arch>.dmg
set -euo pipefail

ARCH="${1:-$(uname -m)}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== 目标架构: ${ARCH} =="

# 选择 Python (项目要求 3.13+)
if command -v python3.13 >/dev/null 2>&1; then
    PY=python3.13
else
    PY=python3
fi
if [ "$("$PY" -c 'import sys; print(sys.version_info >= (3, 13))' 2>/dev/null)" != "True" ]; then
    echo "错误: 需要 Python 3.13+,请先安装(如 brew install python@3.13)" >&2
    exit 1
fi
echo "== Python: $($PY --version 2>&1) =="

echo "== 创建虚拟环境 =="
$PY -m venv .venv-mac
# shellcheck disable=SC1091
source .venv-mac/bin/activate

python -m pip install --upgrade pip

echo "== 安装依赖 =="
python -m pip install -r requirements.txt pyinstaller
if [ "$ARCH" = "x86_64" ]; then
    # onnxruntime 1.24+ 不再发布 macOS x86_64 wheel, 在 Intel 上强制降级到 1.23.x
    python -m pip install "onnxruntime<1.24"
fi

echo "== PyInstaller 打包 (onefile) =="
# 注意: macOS 上 --add-data 的分隔符是冒号(:)
pyinstaller -F main.py -n chaoxing \
    --add-data "resource:resource" \
    --hidden-import=chardet \
    --collect-all ddddocr \
    --noconfirm --clean

echo "== 组装 release 目录 =="
rm -rf release_dmg
mkdir -p release_dmg
cp dist/chaoxing release_dmg/
cp config_template.ini release_dmg/

# 双击启动器: .command 文件会在终端窗口中打开并执行主程序
cat > release_dmg/chaoxing.command << 'EOF'
#!/bin/bash
cd "$(dirname "$0")" || exit 1
exec ./chaoxing
EOF
chmod +x release_dmg/chaoxing release_dmg/chaoxing.command

cat > release_dmg/使用说明.txt << EOF
超星学习通 chaoxing · macOS ${ARCH} 版
================================================

一、运行
  1. 把文件夹整体拖到桌面或其他位置
  2. 双击 chaoxing.command 启动(会自动弹出终端窗口)
     或在终端里手动运行:
       cd 到本文件夹
       ./chaoxing

二、首次运行若提示"无法验证开发者 / 已损坏"
  在终端执行(进入本文件夹后):
       xattr -dr com.apple.quarantine .
  或到 系统设置 > 隐私与安全性 中点击"仍要打开"。

三、常用方式
  # 配置文件运行(推荐): 复制 config_template.ini 为 config.ini, 填入账号密码
  ./chaoxing -c config.ini

  # 命令行运行
  ./chaoxing -u 手机号 -p 密码 -l 课程ID1,课程ID2 -s 2 -a retry

  常用参数:
    -l 课程ID列表     指定要刷的课程
    -s 2              播放倍速(最大2)
    -j 4              并发章节数
    -a retry|ask|continue   关闭任务点处理方式
    --auto-sign       自动签到

四、构建信息
  架构: ${ARCH} $( [ "$ARCH" = arm64 ] && echo "(Apple Silicon: M1/M2/M3/M4)" || echo "(Intel)" )
  需要网络连接。未签名的开源构建(GPL-3.0), 仅供学习研究。

项目: https://github.com/Samueli924/chaoxing
EOF

echo "== 制作 DMG =="
hdiutil create -volname "chaoxing" \
    -srcfolder release_dmg \
    -format UDZO \
    -ov \
    "chaoxing-macos-${ARCH}.dmg"

echo "== 完成: ${ROOT}/chaoxing-macos-${ARCH}.dmg =="
ls -lh "chaoxing-macos-${ARCH}.dmg"
