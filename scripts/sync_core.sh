#!/usr/bin/env bash
# 同步 Python 核心到安卓工程：从 git HEAD 打包 api/ + main.py + 字体表为 core.zip
# 用法：在仓库根目录执行 bash scripts/sync_core.sh
set -euo pipefail
cd "$(dirname "$0")/.."
git archive --format=zip -o android/app/src/main/python/core.zip HEAD -- api resource/font_map_table.json "main?py"
echo "core.zip 已更新: $(wc -c < android/app/src/main/python/core.zip) bytes"
