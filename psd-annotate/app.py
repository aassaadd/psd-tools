# -*- coding: utf-8 -*-
"""PSD 标注工具 Web 服务 —— 类似"标你妹"的网页版设计稿标注
上传 PSD -> 网页查看效果图 -> 点击图层查看尺寸/位置/CSS -> 导出图层素材
核心解析逻辑在 core.py，本文件只负责 HTTP 路由。MCP 接口见 mcp_server.py。
"""
import os
import uuid

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


@app.route("/output/<doc_id>/<path:fname>")
def output_file(doc_id, fname):
    return send_from_directory(core.doc_dir(doc_id), fname)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8642, threaded=True)
