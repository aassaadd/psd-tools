#!/usr/bin/env bash
# psd-tools 一键启动脚本
# 功能：自动停止旧服务 -> 自动创建虚拟环境 -> 按需安装依赖 -> 启动 Flask Web 服务（http://127.0.0.1:8642）
# 用法：./start.sh

set -e
cd "$(dirname "$0")/psd-annotate"

PORT=8642

# 0. 自动停止：清理占用端口的旧服务进程（先 TERM，不退出再 KILL）
OLD_PIDS=$(lsof -ti :"$PORT" 2>/dev/null || true)
if [ -n "$OLD_PIDS" ]; then
    echo "[停止] 端口 $PORT 被旧服务占用（PID: $OLD_PIDS），正在停止..."
    kill $OLD_PIDS 2>/dev/null || true
    sleep 1
    OLD_PIDS=$(lsof -ti :"$PORT" 2>/dev/null || true)
    if [ -n "$OLD_PIDS" ]; then
        echo "[停止] 进程未响应，强制结束..."
        kill -9 $OLD_PIDS 2>/dev/null || true
        sleep 1
    fi
    echo "[停止] 旧服务已停止"
fi

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
echo "[启动] Web 服务运行中：http://127.0.0.1:$PORT"
exec .venv/bin/python app.py
