# -*- coding: utf-8 -*-
"""PSD 标注工具启动器 —— Windows exe 打包入口（PyInstaller）

功能：在单个进程内同时启动两个本地服务，并自动打开浏览器：
  1) Web 网页版：http://127.0.0.1:8642
  2) MCP 网络服务：http://127.0.0.1:8643/mcp（streamable-http；启动失败仅告警降级，不影响网页版）

使用方式：
  - 开发环境：python launcher.py（效果与 exe 一致）
  - 打包：在 Windows 上运行项目根目录 build_exe.bat，生成 dist/psd-annotate.exe
  - 运行：双击 exe，uploads/output 数据目录生成在 exe 同级；控制台窗口显示日志，Ctrl+C 退出
"""
import socket
import threading
import time
import webbrowser

import app as web_app
import core

WEB_PORT = 8642
MCP_PORT = 8643


def port_in_use(port):
    """检测本机端口是否已被占用。

    参数：port —— 端口号（int）。
    返回值：True 表示端口已被监听（可能旧服务仍在运行）。
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def run_web():
    """线程目标：前台启动 Flask Web 服务（127.0.0.1:8642）。

    参数：无。返回值：无（常驻直到进程退出）。
    """
    # 非主线程必须关闭 reloader，否则 werkzeug 会报错
    web_app.app.run(host="127.0.0.1", port=WEB_PORT,
                    threaded=True, use_reloader=False)


def run_mcp():
    """线程目标：启动 MCP streamable-http 网络服务（127.0.0.1:8643/mcp）。

    参数：无。返回值：无（常驻直到进程退出）。
    说明：延迟导入 mcp_server 并吞掉启动异常——打包环境缺少
    uvicorn 子模块等情况下降级运行，网页版不受影响。
    """
    try:
        import mcp_server
        mcp_server.server.run("streamable-http", host="127.0.0.1", port=MCP_PORT)
    except Exception as e:  # noqa: BLE001 降级场景需捕获所有异常
        print(f"[警告] MCP 服务启动失败（网页版不受影响）：{e}")


def wait_port(port, timeout=15):
    """轮询等待端口就绪（服务启动完成）。

    参数：port —— 目标端口；timeout —— 最长等待秒数。
    返回值：True 表示端口已就绪；False 表示超时。
    """
    for _ in range(int(timeout * 2)):
        time.sleep(0.5)
        if port_in_use(port):
            return True
    return False


def main():
    """启动器主流程：检查端口 -> 后台线程启动 Web 与 MCP -> 就绪后打开浏览器。

    参数：无。返回值：无（主线程常驻，Ctrl+C 退出）。
    """
    print(f"[启动] 数据目录（上传/解析产物）：{core.DATA_DIR}")
    if port_in_use(WEB_PORT):
        # 端口已占用：大概率是旧服务仍在运行，直接打开浏览器复用
        print(f"[提示] 端口 {WEB_PORT} 已被占用，服务可能已在运行，直接打开浏览器。")
        webbrowser.open(f"http://127.0.0.1:{WEB_PORT}")
        return

    threading.Thread(target=run_web, daemon=True).start()
    print(f"[启动] Web 服务启动中：http://127.0.0.1:{WEB_PORT}")
    threading.Thread(target=run_mcp, daemon=True).start()
    print(f"[启动] MCP 网络服务启动中：http://127.0.0.1:{MCP_PORT}/mcp")

    if wait_port(WEB_PORT):
        webbrowser.open(f"http://127.0.0.1:{WEB_PORT}")
    else:
        print("[警告] Web 服务启动超时，请稍后手动访问 http://127.0.0.1:8642")

    print("[就绪] 浏览器已打开；关闭本窗口或按 Ctrl+C 退出服务。")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n[退出] 服务已停止。")


if __name__ == "__main__":
    main()
