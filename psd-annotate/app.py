# -*- coding: utf-8 -*-
"""PSD 标注工具 Web 服务 —— 类似"标你妹"的网页版设计稿标注
上传 PSD -> 网页查看效果图 -> 点击图层查看尺寸/位置/CSS -> 导出图层素材
核心解析逻辑在 core.py，本文件只负责 HTTP 路由。MCP 接口见 mcp_server.py。
"""
import os
import uuid
from io import BytesIO

from flask import Flask, request, jsonify, send_from_directory, send_file, abort

import core

BASE_DIR = core.BASE_DIR

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB


@app.route("/")
def index():
    resp = send_from_directory(os.path.join(BASE_DIR, "static"), "index.html")
    resp.headers["Cache-Control"] = "no-store"  # 禁用缓存，保证页面/脚本更新即时生效
    return resp


@app.route("/api/upload", methods=["POST"])
def upload():
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "没有文件"}), 400
    if not f.filename.lower().endswith(".psd"):
        return jsonify({"error": "请上传 .psd 文件"}), 400
    doc_id = uuid.uuid4().hex[:12]
    src = os.path.join(core.UPLOAD_DIR, doc_id + ".psd")
    f.save(src)
    try:
        display_name = os.path.splitext(os.path.basename(f.filename))[0]
        meta = core.parse_psd_file(src, doc_id=doc_id, display_name=display_name)
    except Exception as e:
        return jsonify({"error": f"解析失败: {e}"}), 500
    return jsonify(meta)


@app.route("/api/docs")
def list_docs():
    return jsonify(core.list_docs())


@app.route("/api/doc/<doc_id>")
def get_doc(doc_id):
    try:
        meta, tree = core.load_doc(doc_id)
    except FileNotFoundError:
        abort(404)
    return jsonify({"meta": meta, "layers": tree})


@app.route("/api/layer/<doc_id>/<layer_id>/png")
def layer_png(doc_id, layer_id):
    try:
        path = core.render_layer_png(doc_id, layer_id)
    except FileNotFoundError:
        abort(404)
    except ValueError as e:
        abort(404, description=str(e))
    return send_file(path, mimetype="image/png",
                     as_attachment=request.args.get("download") == "1",
                     download_name=f"{layer_id}.png")


@app.route("/api/export/<doc_id>/html")
def export_html(doc_id):
    """导出静态网页为 zip 压缩包。

    功能：将指定文档的标注页面打包成可离线浏览的静态网页，以 zip 附件形式下载。
    参数：doc_id —— 文档 ID（URL 路径）；layout —— 布局单位，从 query string 读取，
          仅允许 "vw"/"px"，其他值按 "vw" 处理。
    返回：zip 文件附件（application/zip）；doc_id 无效返回 404，打包失败返回 500 及错误信息。
    """
    layout = request.args.get("layout", "vw")
    if layout not in ("vw", "px"):
        layout = "vw"
    try:
        data, name = core.export_html_zip(doc_id, layout)
    except FileNotFoundError:
        abort(404)
    except ValueError as e:
        return jsonify({"error": str(e)}), 500
    return send_file(BytesIO(data), mimetype="application/zip",
                     as_attachment=True, download_name=f"{name}.zip")


@app.route("/api/export/<doc_id>/figma")
def export_figma(doc_id):
    """导出 Figma（SVG）为 zip 压缩包。

    功能：将指定文档的图层导出为 Figma 可导入的 SVG 文件，打包成 zip 附件下载。
    参数：doc_id —— 文档 ID（URL 路径）。
    返回：zip 文件附件（application/zip）；doc_id 无效返回 404，导出失败返回 500 及错误信息。
    """
    try:
        data, name = core.export_figma_zip(doc_id)
    except FileNotFoundError:
        abort(404)
    except ValueError as e:
        return jsonify({"error": str(e)}), 500
    return send_file(BytesIO(data), mimetype="application/zip",
                     as_attachment=True, download_name=f"{name}-figma.zip")


@app.route("/output/<doc_id>/<path:fname>")
def output_file(doc_id, fname):
    return send_from_directory(core.doc_dir(doc_id), fname)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8642, threaded=True)
