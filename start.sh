#!/usr/bin/env bash
# psd-tools 一键启动脚本
# 功能：自动创建虚拟环境 -> 安装依赖 -> 启动 Flask Web 服务（http://127.0.0.1:8642）
# 用法：./start.sh

set -e
cd "$(dirname "$0")/psd-annotate"

# 1. 准备虚拟环境：不存在则创建
if [ ! -x .venv/bin/python ]; then
    echo "[启动] 未检测到虚拟环境，正在创建 .venv ..."
    python3 -m venv .venv
fi

# 2. 校验依赖：核心库可导入则跳过安装，否则按 requirements.txt 安装
if ! .venv/bin/python -c "import flask, psd_tools, PIL, aggdraw, mcp" 2>/dev/null; then
    echo "[启动] 正在安装依赖（首次约需一分钟）..."
    .venv/bin/pip install --quiet -r ../requirements.txt
fi

# 3. 启动 Web 服务（前台运行，Ctrl+C 退出）
echo "[启动] Web 服务运行中：http://127.0.0.1:8642"
exec .venv/bin/python app.py
