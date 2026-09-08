# -*- coding: utf-8 -*-
"""PSD 解析核心逻辑（供 Flask Web 与 MCP server 共用）"""
import json
import os
import re
import time
import uuid

from PIL import Image
from psd_tools import PSDImage

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

BLEND_MAP = {
    "NORMAL": "normal", "MULTIPLY": "multiply", "SCREEN": "screen",
    "OVERLAY": "overlay", "DARKEN": "darken", "LIGHTEN": "lighten",
    "COLOR_DODGE": "color-dodge", "COLOR_BURN": "color-burn",
    "HARD_LIGHT": "hard-light", "SOFT_LIGHT": "soft-light",
    "DIFFERENCE": "difference", "EXCLUSION": "exclusion",
    "HUE": "hue", "SATURATION": "saturation", "COLOR": "color",
    "LUMINOSITY": "luminosity",
}


def doc_dir(doc_id):
    return os.path.join(OUTPUT_DIR, doc_id)


def safe_name(name):
    return re.sub(r'[\\/:*?"<>|\r\n]', "_", str(name)).strip() or "未命名"


def parse_text_layer(layer):
    """尽力从文本图层提取文字内容 / 字体 / 字号 / 颜色"""
    info = {"type": "text", "text": "", "fonts": [], "font_size": None, "color": None}
    t = getattr(layer, "text", None)
    if not t:
        return info
    info["text"] = t.get("text", "")
    ed = t.get("engine_data") or {}
    try:
        fontset = ed["ResourceDict"]["FontSet"]
        names = []
        for f in fontset:
            n = f.get("Name") or ""
            if n and n not in names:
                names.append(n)
        info["fonts"] = names
    except Exception:
        pass
    try:
        runs = ed["EngineDict"]["StyleRun"]
        sizes, colors = set(), set()
        for run in runs:
            ss = run.get("StyleSheet", {}).get("StyleSheetData", {})
            fs = ss.get("FontSize")
            if fs:
                sizes.add(round(float(fs) / 2))  # 引擎存储为 2x
            fill = ss.get("FillColor")
            if fill and "Values" in fill:
                v = fill["Values"]
                if len(v) >= 3:
                    rgb = [int(round(float(c) * 255)) for c in v[:3]]
                    colors.add("#%02X%02X%02X" % tuple(rgb))
        if sizes:
            info["font_size"] = min(sizes) if len(sizes) == 1 else sorted(sizes)
        if colors:
            info["color"] = list(colors)[0] if len(colors) == 1 else sorted(colors)
    except Exception:
        pass
    return info


def layer_node(layer):
    """把一个 psd-tools 图层转成 JSON 节点"""
    left, top, right, bottom = layer.bbox
    node = {
        "id": None,  # 由 walk_tree 统一分配
        "name": layer.name,
        "kind": "group" if layer.is_group() else ("text" if layer.kind == "type" else "layer"),
        "bbox": [left, top, right, bottom],
        "w": max(0, right - left),
        "h": max(0, bottom - top),
        "visible": layer.visible,
        "opacity": round(layer.opacity / 255.0, 2),
        "blend": BLEND_MAP.get(str(layer.blend_mode).split(".")[-1], "normal"),
        "has_pixels": bool(getattr(layer, "has_pixels", lambda: False)()) or layer.is_group(),
        "children": [],
    }
    if node["kind"] == "text":
        try:
            node["text_info"] = parse_text_layer(layer)
        except Exception:
            node["text_info"] = {"type": "text", "text": ""}
    return node


def walk_tree(group, counter):
    nodes = []
    for layer in group:
        node = layer_node(layer)
        counter[0] += 1
        node["id"] = f"L{counter[0]}"
        if layer.is_group():
            node["children"] = walk_tree(layer, counter)
        nodes.append(node)
    return nodes


def parse_psd_file(src_path, doc_id=None, display_name=None):
    """解析 PSD 文件：渲染整体效果图 + 构建图层树，返回 meta"""
    doc_id = doc_id or uuid.uuid4().hex[:12]
    out = doc_dir(doc_id)
    os.makedirs(out, exist_ok=True)
    psd = PSDImage.open(src_path)

    composite = psd.composite(force=True)
    if composite.mode not in ("RGB", "RGBA"):
        composite = composite.convert("RGBA")
    composite.save(os.path.join(out, "composite.png"))

    counter = [0]
    tree = walk_tree(psd, counter)
    meta = {
        "id": doc_id,
        "name": display_name or os.path.splitext(os.path.basename(src_path))[0],
        "width": psd.width,
        "height": psd.height,
        "layer_count": counter[0],
        "parsed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(os.path.join(out, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    with open(os.path.join(out, "layers.json"), "w", encoding="utf-8") as f:
        json.dump(tree, f, ensure_ascii=False)

    # 保留源文件副本，供图层懒渲染使用
    src_copy = os.path.join(UPLOAD_DIR, doc_id + ".psd")
    if os.path.abspath(src_path) != os.path.abspath(src_copy):
        with open(src_path, "rb") as src, open(src_copy, "wb") as dst:
            dst.write(src.read())
    return meta


def list_docs():
    docs = []
    if os.path.isdir(OUTPUT_DIR):
        for d in sorted(os.listdir(OUTPUT_DIR)):
            mp = os.path.join(OUTPUT_DIR, d, "meta.json")
            if os.path.isfile(mp):
                with open(mp, encoding="utf-8") as f:
                    docs.append(json.load(f))
    docs.sort(key=lambda x: x.get("parsed_at", ""), reverse=True)
    return docs


def load_doc(doc_id):
    d = doc_dir(doc_id)
    if not os.path.isdir(d):
        raise FileNotFoundError(f"文档不存在: {doc_id}")
    with open(os.path.join(d, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    with open(os.path.join(d, "layers.json"), encoding="utf-8") as f:
        tree = json.load(f)
    return meta, tree


def find_layer(nodes, layer_id):
    for n in nodes:
        if n["id"] == layer_id:
            return n
        r = find_layer(n.get("children", []), layer_id)
        if r:
            return r
    return None


def iter_nodes(nodes):
    for n in nodes:
        yield n
        yield from iter_nodes(n.get("children", []))


def find_layers_by_name(tree, keyword):
    kw = keyword.lower()
    return [n for n in iter_nodes(tree) if kw in str(n["name"]).lower()]


def _locate_layer(doc_id, layer_id):
    """按深度优先顺序编号定位 psd-tools 图层对象（与解析编号一致）"""
    psd = PSDImage.open(os.path.join(UPLOAD_DIR, doc_id + ".psd"))
    idx = {"n": 0}
    found = {"layer": None}

    def locate(group):
        for layer in group:
            idx["n"] += 1
            if idx["n"] == int(layer_id[1:]):
                found["layer"] = layer
                return True
            if layer.is_group() and locate(layer):
                return True
        return False

    locate(psd)
    if found["layer"] is None:
        raise ValueError(f"图层不存在: {layer_id}")
    return found["layer"]


def render_layer_png(doc_id, layer_id):
    """按需渲染某个图层的 PNG（带缓存），返回文件路径"""
    d = doc_dir(doc_id)
    cache = os.path.join(d, "assets")
    os.makedirs(cache, exist_ok=True)
    out_path = os.path.join(cache, f"{layer_id}.png")
    if os.path.isfile(out_path):
        return out_path

    _, tree = load_doc(doc_id)
    node = find_layer(tree, layer_id)
    if not node:
        raise ValueError(f"图层不存在: {layer_id}")

    layer = _locate_layer(doc_id, layer_id)
    img = layer.composite(force=True)
    if img is None:
        raise ValueError(f"图层 {node['name']} 无可渲染像素")
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")
    img.save(out_path)
    return out_path


def export_layer_crop(doc_id, layer_id):
    """从整体效果图中按图层 bbox 裁剪（保留全部叠加/剪贴蒙版语义）。
    返回 (文件路径, 裁剪原点 offset_x, offset_y)。"""
    _, tree = load_doc(doc_id)
    node = find_layer(tree, layer_id)
    if not node:
        raise ValueError(f"图层不存在: {layer_id}")
    comp_path = os.path.join(doc_dir(doc_id), "composite.png")
    img = Image.open(comp_path)
    l, t, r, b = node["bbox"]
    cl, ct = max(0, l), max(0, t)
    cr, cb = min(img.width, r), min(img.height, b)
    if cr <= cl or cb <= ct:
        raise ValueError(f"图层 {node['name']} 完全在画布外，无可裁剪内容")
    crop = img.crop((cl, ct, cr, cb))
    cache = os.path.join(doc_dir(doc_id), "crops")
    os.makedirs(cache, exist_ok=True)
    p = os.path.join(cache, f"{layer_id}.png")
    crop.save(p)
    return p, cl, ct


def css_snippet(node):
    """根据图层节点生成 CSS 示例"""
    L = ["position: absolute;"]
    L.append(f"left: {node['bbox'][0]}px;")
    L.append(f"top: {node['bbox'][1]}px;")
    if node["w"]:
        L.append(f"width: {node['w']}px;")
    if node["h"]:
        L.append(f"height: {node['h']}px;")
    if node["opacity"] < 1:
        L.append(f"opacity: {node['opacity']};")
    if node["blend"] != "normal":
        L.append(f"mix-blend-mode: {node['blend']};")
    ti = node.get("text_info")
    if ti:
        if ti.get("fonts"):
            L.append(f'font-family: "{ti["fonts"][0]}";')
        if ti.get("font_size") is not None:
            fs = ti["font_size"][0] if isinstance(ti["font_size"], list) else ti["font_size"]
            L.append(f"font-size: {fs}px;")
        if ti.get("color"):
            L.append(f"color: {ti['color']};")
    return "\n".join(L)
