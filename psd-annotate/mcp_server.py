# -*- coding: utf-8 -*-
"""PSD 标注 MCP Server（标准 MCP 协议，支持 stdio 与 streamable-http 双传输）

供 AI 客户端调用，能力与网页版一致：
  - 解析本地 PSD 文件，产出整体效果图 + 图层树
  - 查询图层的位置/尺寸/透明度/字体等标注信息，并生成 CSS 示例
  - 按名称搜索图层
  - 导出任意图层（含图层组）为 PNG 素材

启动方式：
  - 网络版（推荐）：python mcp_server.py --http [--host 127.0.0.1] [--port 8643]
    端点 http://127.0.0.1:8643/mcp（streamable-http），客户端以 URL 方式连接。
  - stdio：python mcp_server.py          （由 MCP 客户端拉起，作为兜底）
"""
import argparse
import json
import os
import shutil

from mcp.server.mcpserver import MCPServer

import core

server = MCPServer(
    name="psd-annotate",
    title="PSD 标注",
    instructions=(
        "PSD 设计稿标注工具。典型流程："
        "1) 用 psd_parse 解析本地 .psd 文件得到 doc_id 和图层树；"
        "2) 用 psd_layer_tree / psd_find_layers 浏览或搜索图层；"
        "3) 用 psd_layer_info 获取某图层的 X/Y/宽/高/透明度/字体及 CSS 示例；"
        "4) 用 psd_export_layer 导出图层 PNG 素材。"
        "解析结果会被缓存，同一文件重复解析会生成新的 doc_id。"
    ),
)


def _compact(node, depth=0, max_depth=2):
    """压缩图层树输出，避免 token 爆炸"""
    item = {
        "id": node["id"],
        "name": node["name"],
        "kind": node["kind"],
        "bbox": node["bbox"],
        "w": node["w"],
        "h": node["h"],
        "visible": node["visible"],
    }
    if node["kind"] == "text" and node.get("text_info"):
        ti = node["text_info"]
        item["text"] = ti.get("text", "")
    if depth < max_depth and node.get("children"):
        item["children"] = [_compact(c, depth + 1, max_depth) for c in node["children"]]
    elif node.get("children"):
        item["children_omitted"] = len(node["children"])
    return item


@server.tool()
def psd_list_docs() -> str:
    """列出已解析过的所有 PSD 文档（含 doc_id、名称、画布尺寸、图层数）。"""
    docs = core.list_docs()
    return json.dumps(docs, ensure_ascii=False, indent=1)


@server.tool()
def psd_parse(file_path: str) -> str:
    """解析本地 PSD 文件。file_path 为 .psd 文件的绝对路径。
    返回文档 meta（doc_id、画布宽高、图层数量）和前两层图层树概览。
    解析需要数秒到数十秒，大文件请耐心等待。"""
    file_path = os.path.expanduser(file_path)
    if not os.path.isfile(file_path):
        return json.dumps({"error": f"文件不存在: {file_path}"}, ensure_ascii=False)
    if not file_path.lower().endswith(".psd"):
        return json.dumps({"error": "仅支持 .psd 文件"}, ensure_ascii=False)
    meta = core.parse_psd_file(file_path)
    _, tree = core.load_doc(meta["id"])
    return json.dumps({"meta": meta, "layers_preview": [_compact(n) for n in tree]},
                      ensure_ascii=False, indent=1)


@server.tool()
def psd_find_doc(keyword: str) -> str:
    """按设计稿名称模糊搜索已解析过的文档（不区分大小写，子串匹配）。
    返回匹配文档的 meta 列表（doc_id、名称、画布尺寸、图层数、解析时间），
    可直接用 doc_id 继续调用 psd_layer_tree / psd_layer_info / psd_export_* 等工具。"""
    kw = str(keyword).strip().lower()
    if not kw:
        return json.dumps({"matched": 0, "docs": []}, ensure_ascii=False)
    hits = [d for d in core.list_docs() if kw in str(d.get("name", "")).lower()]
    return json.dumps({"matched": len(hits), "docs": hits}, ensure_ascii=False, indent=1)


@server.tool()
def psd_layer_tree(doc_id: str, max_depth: int = 3) -> str:
    """获取某文档的图层树。doc_id 来自 psd_parse / psd_list_docs。
    max_depth 控制展开深度（默认 3），更深的子图层以 children_omitted 计数表示。"""
    try:
        _, tree = core.load_doc(doc_id)
    except FileNotFoundError:
        return json.dumps({"error": f"文档不存在: {doc_id}"}, ensure_ascii=False)
    return json.dumps([_compact(n, 0, max(1, max_depth)) for n in tree],
                      ensure_ascii=False, indent=1)


@server.tool()
def psd_find_layers(doc_id: str, keyword: str) -> str:
    """在文档中按图层名称模糊搜索（不区分大小写）。
    返回匹配图层的 id / 名称 / 类型 / bbox，可再用 psd_layer_info 查看详情。"""
    try:
        _, tree = core.load_doc(doc_id)
    except FileNotFoundError:
        return json.dumps({"error": f"文档不存在: {doc_id}"}, ensure_ascii=False)
    hits = core.find_layers_by_name(tree, keyword)
    out = [{"id": n["id"], "name": n["name"], "kind": n["kind"],
            "bbox": n["bbox"], "w": n["w"], "h": n["h"]} for n in hits]
    return json.dumps({"matched": len(out), "layers": out}, ensure_ascii=False, indent=1)


@server.tool()
def psd_layer_info(doc_id: str, layer_id: str) -> str:
    """获取图层完整标注信息：X/Y/宽/高/透明度/混合模式、文本内容与字体字号颜色、CSS 示例。
    layer_id 形如 "L5"（来自 psd_layer_tree / psd_find_layers）。"""
    try:
        _, tree = core.load_doc(doc_id)
    except FileNotFoundError:
        return json.dumps({"error": f"文档不存在: {doc_id}"}, ensure_ascii=False)
    node = core.find_layer(tree, layer_id)
    if not node:
        return json.dumps({"error": f"图层不存在: {layer_id}"}, ensure_ascii=False)
    info = dict(node)
    info["css"] = core.css_snippet(node)
    return json.dumps(info, ensure_ascii=False, indent=1)


@server.tool()
def psd_export_layer(doc_id: str, layer_id: str,
                     output_dir: str = "") -> str:
    """导出图层为 PNG 素材（透明背景，支持图层组整体导出）。
    output_dir 为输出目录，默认 ~/Downloads/psd-assets。返回保存路径与图层信息。"""
    try:
        _, tree = core.load_doc(doc_id)
    except FileNotFoundError:
        return json.dumps({"error": f"文档不存在: {doc_id}"}, ensure_ascii=False)
    node = core.find_layer(tree, layer_id)
    if not node:
        return json.dumps({"error": f"图层不存在: {layer_id}"}, ensure_ascii=False)
    try:
        src = core.render_layer_png(doc_id, layer_id)
    except ValueError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    out_dir = os.path.expanduser(output_dir) if output_dir else \
        os.path.join(os.path.expanduser("~"), "Downloads", "psd-assets")
    os.makedirs(out_dir, exist_ok=True)
    fname = f"{core.safe_name(node['name'])}_{layer_id}.png"
    dest = os.path.join(out_dir, fname)
    shutil.copyfile(src, dest)
    return json.dumps({"saved": dest, "name": node["name"],
                       "w": node["w"], "h": node["h"]}, ensure_ascii=False, indent=1)


@server.tool()
def psd_export_layer_crop(doc_id: str, layer_id: str,
                          output_dir: str = "") -> str:
    """按图层在画布中的 bbox 裁剪整体效果图，导出 PNG。
    与 psd_export_layer 的区别：保留画布上的全部叠加效果/剪贴蒙版语义，
    像素与设计稿完全一致，适合 1:1 还原页面。
    注意：图层被画布边缘裁剪时，返回的 offset 是实际裁剪起点（可能与图层 bbox 不同）。
    output_dir 为输出目录，默认 ~/Downloads/psd-assets。"""
    try:
        _, tree = core.load_doc(doc_id)
    except FileNotFoundError:
        return json.dumps({"error": f"文档不存在: {doc_id}"}, ensure_ascii=False)
    node = core.find_layer(tree, layer_id)
    if not node:
        return json.dumps({"error": f"图层不存在: {layer_id}"}, ensure_ascii=False)
    try:
        src, ox, oy = core.export_layer_crop(doc_id, layer_id)
    except ValueError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    out_dir = os.path.expanduser(output_dir) if output_dir else \
        os.path.join(os.path.expanduser("~"), "Downloads", "psd-assets")
    os.makedirs(out_dir, exist_ok=True)
    fname = f"{core.safe_name(node['name'])}_{layer_id}_crop.png"
    dest = os.path.join(out_dir, fname)
    shutil.copyfile(src, dest)
    return json.dumps({"saved": dest, "name": node["name"],
                       "offset_x": ox, "offset_y": oy,
                       "w": node["w"], "h": node["h"]}, ensure_ascii=False, indent=1)


def main():
    """解析命令行参数并启动 MCP Server。

    参数：--http 启用 streamable-http 网络模式；--host 监听地址（默认 127.0.0.1）；
         --port 监听端口（默认 8643）。不带 --http 时以 stdio 模式运行（兜底）。
    返回值：无（进程常驻直到被终止）。
    """
    ap = argparse.ArgumentParser(description="psd-annotate MCP Server")
    ap.add_argument("--http", action="store_true",
                    help="以 streamable-http 网络模式启动（默认 stdio）")
    ap.add_argument("--host", default="127.0.0.1", help="监听地址，默认 127.0.0.1")
    ap.add_argument("--port", type=int, default=8643, help="监听端口，默认 8643")
    args = ap.parse_args()
    if args.http:
        server.run("streamable-http", host=args.host, port=args.port)
    else:
        server.run("stdio")


if __name__ == "__main__":
    main()
