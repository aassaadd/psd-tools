# -*- coding: utf-8 -*-
"""PSD 解析核心逻辑（供 Flask Web 与 MCP server 共用）"""
import html
import io
import json
import os
import re
import threading
import time
import uuid
import zipfile
from collections import OrderedDict

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
    """解析 PSD 文件：渲染整体效果图 + 构建图层树 + 收集画板信息，返回 meta"""
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
    artboards = _collect_artboards(psd)
    if artboards:
        meta["artboards"] = artboards  # 画板信息（名称 + 视口 bbox），供导出多页面使用
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


# PSDImage 打开缓存：doc_id -> PSDImage（LRU，避免批量导出切图时重复解析 PSD；
# 上限 _PSD_CACHE_MAX 条，淘汰最久未使用的条目，防止长期运行内存持续增长）
_PSD_CACHE_MAX = 4
_PSD_CACHE = OrderedDict()
_PSD_CACHE_LOCK = threading.Lock()


def _get_cached_psd(doc_id):
    """获取缓存的 PSDImage（LRU 策略）。

    功能：命中缓存则将条目移至队尾（视为最近使用）；未命中则在锁外执行
        耗时的 PSDImage.open IO（避免阻塞其他线程），随后在锁内二次检查
        后写入缓存；写入后超过 _PSD_CACHE_MAX 时淘汰最久未使用（队首）条目。
    参数：doc_id —— 文档 id
    返回：PSDImage 对象
    """
    with _PSD_CACHE_LOCK:
        psd = _PSD_CACHE.get(doc_id)
        if psd is not None:
            _PSD_CACHE.move_to_end(doc_id)
            return psd
    # 锁外执行耗时的文件打开 IO
    new_psd = PSDImage.open(os.path.join(UPLOAD_DIR, doc_id + ".psd"))
    with _PSD_CACHE_LOCK:
        psd = _PSD_CACHE.get(doc_id)
        if psd is not None:
            # 并发期间已有其他线程写入同一 doc_id，复用已有条目
            _PSD_CACHE.move_to_end(doc_id)
            return psd
        _PSD_CACHE[doc_id] = new_psd
        while len(_PSD_CACHE) > _PSD_CACHE_MAX:
            _PSD_CACHE.popitem(last=False)
        return new_psd


def _locate_layer(doc_id, layer_id):
    """按深度优先顺序编号定位 psd-tools 图层对象（与解析编号一致）。

    功能：通过 LRU 缓存获取已打开的 PSD（避免批量导出时重复解析整个文件），
        按与解析期一致的深度优先编号定位图层对象。
    参数：doc_id —— 文档 id；layer_id —— 图层编号（如 "L3"）
    返回：psd-tools 图层对象；编号不存在抛 ValueError
    """
    psd = _get_cached_psd(doc_id)
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
    try:
        img = Image.open(comp_path)
    except Exception:
        raise ValueError(f"文档 {doc_id} 未生成合成图，请重新解析")
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


# ============ 静态 HTML 网页导出 ============

_TOC_CSS = """
.toc {
  max-width: 640px;
  margin: 48px auto;
  padding: 0 16px;
  font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
  color: #222;
}
.toc h1 {
  font-size: 22px;
  margin: 0 0 16px;
}
.toc ul {
  list-style: none;
  margin: 0;
  padding: 0;
}
.toc li {
  border: 1px solid #e5e5e5;
  border-radius: 8px;
  margin-bottom: 10px;
  overflow: hidden;
}
.toc a {
  display: block;
  padding: 14px 16px;
  color: #1a73e8;
  font-size: 16px;
  text-decoration: none;
}
.toc a:hover {
  background: #f5f7fa;
}
.toc-size {
  float: right;
  color: #888;
  font-size: 13px;
}
""".strip()


def _collect_artboards(group):
    """递归收集 PSD 图层树中的画板信息。

    功能：遍历 psd-tools 图层对象，识别 kind 为 "artboard" 的画板组
    （psd_tools 中 Artboard 是 Group 的子类，kind 返回 "artboard"），
    读取其视口矩形 artboardRect 作为画板 bbox（可能含负坐标，
    且该 bbox 不裁剪子图层 bbox）。单个图层读取异常时跳过，不阻断解析。
    参数：group —— psd_tools 的 PSDImage 或 Group 图层组对象
    返回：画板信息列表 [{"name": 画板名, "bbox": [l, t, r, b]}]，无画板返回 []
    """
    arts = []
    for layer in group:
        try:
            if getattr(layer, "kind", "") == "artboard":
                l, t, r, b = layer.bbox
                arts.append(
                    {"name": layer.name, "bbox": [int(l), int(t), int(r), int(b)]}
                )
            if layer.is_group():
                arts.extend(_collect_artboards(layer))
        except Exception:
            continue
    return arts


def _fmt_len(value, base_w, layout):
    """按布局模式换算长度值并附加 CSS 单位。

    功能：vw 模式按 值/基准宽*100 换算，保留 4 位小数并去除尾零；
    px 模式四舍五入取整。
    参数：value —— 长度数值（设计稿 px）；base_w —— 基准宽度（所在画板/画布宽，px）；
          layout —— 'vw'（自适应）或 'px'（固定像素）
    返回：带单位的 CSS 长度字符串，如 "24.92vw"、"320px"
    """
    if layout == "vw":
        s = ("%.4f" % (float(value) / base_w * 100)).rstrip("0").rstrip(".")
        if s in ("", "-0"):
            s = "0"
        return s + "vw"
    return f"{round(value)}px"


def _bbox_intersects(bbox, area):
    """判断图层 bbox 是否与页面区域有交集（仅边界相接不算交集）。

    参数：bbox —— 图层边界 [l, t, r, b]；area —— 页面区域 (l, t, r, b)
    返回：bool，有交集返回 True
    """
    l, t, r, b = bbox
    al, at, ar, ab = area
    return r > al and l < ar and b > at and t < ab


def _text_css_extra(ti, base_w, layout):
    """生成文本图层专属的 CSS 属性行（字体族 / 字号 / 颜色 / 近似行高）。

    功能：font-family 以解析字体优先（最多取前 3 个，名字加引号），
        拼接中文回退栈；font-size 取首个（int 或 list 均处理，None 跳过）；
        color 取首个（兼容解析出的多色 list，None 跳过）；行高采用近似值 1.4 并注释。
    参数：ti —— 节点的 text_info 字典；base_w —— 基准宽度；layout —— 'vw'|'px'
    返回：CSS 属性行字符串列表
    """
    fonts = [f for f in (ti.get("fonts") or []) if f][:3]
    stack = ", ".join('"%s"' % f for f in fonts)
    fallback = '"PingFang SC", "Microsoft YaHei", sans-serif'
    lines = ["  font-family: " + (stack + ", " if stack else "") + fallback + ";"]
    fs = ti.get("font_size")
    if isinstance(fs, list):
        fs = fs[0] if fs else None
    if fs:
        lines.append(f"  font-size: {_fmt_len(fs, base_w, layout)};")
    color = ti.get("color")
    if isinstance(color, list):
        color = color[0] if color else None
    if color:
        lines.append(f"  color: {color};")
    lines.append("  line-height: 1.4; /* 行高为近似值 */")
    lines.append("  white-space: pre-wrap;")
    return lines


def _node_css_rule(cls, node, left, top, base_w, layout, extra, size_wh=None):
    """生成单个图层的 CSS 规则文本。

    功能：以节点 bbox 相对父容器原点的 left/top 生成 position:absolute 定位规则，
        附加宽高、opacity、mix-blend-mode 以及类型专属样式（extra）。
    参数：cls —— CSS 类名（不含点号）；node —— 图层节点；left/top —— 相对父容器
        原点的偏移（px）；base_w —— 基准宽度；layout —— 'vw'|'px'；
        extra —— 附加属性行字符串列表；size_wh —— 可选 (宽, 高) 覆盖节点
        默认宽高（如切图裁掉透明边后的实际尺寸，单位 px）
    返回：完整 CSS 规则字符串（含选择器与花括号）
    """
    lines = [
        "  position: absolute;",
        f"  left: {_fmt_len(left, base_w, layout)};",
        f"  top: {_fmt_len(top, base_w, layout)};",
    ]
    w, h = size_wh if size_wh is not None else (node.get("w", 0), node.get("h", 0))
    if w > 0:
        lines.append(f"  width: {_fmt_len(w, base_w, layout)};")
    if h > 0:
        lines.append(f"  height: {_fmt_len(h, base_w, layout)};")
    if node.get("opacity", 1) < 1:
        lines.append(f"  opacity: {node['opacity']};")
    if node.get("blend", "normal") != "normal":
        lines.append(f"  mix-blend-mode: {node['blend']};")
    lines.extend(extra)
    return f".{cls} {{\n" + "\n".join(lines) + "\n}"


def _unique_asset_name(node, used_names):
    """为图层切图生成合法且唯一的资源文件基础名（不含扩展名）。

    功能：图层名经 safe_name 清洗；重名时自动追加图层 id，仍冲突则追加序号。
    参数：node —— 图层节点；used_names —— 已占用名字集合（就地更新）
    返回：唯一的基础文件名字符串
    """
    base = safe_name(node["name"])
    key = base if base not in used_names else f"{base}_{node['id']}"
    n = 2
    while key in used_names:
        key = f"{base}_{node['id']}_{n}"
        n += 1
    used_names.add(key)
    return key


def _render_page_body(doc_id, nodes, parent_left, parent_top, page, layout, rules,
                      used_names, files):
    """递归渲染一页的图层节点，产出 HTML 片段、CSS 规则与切图资源。

    功能：遍历图层树，仅导出 visible=True 且 bbox 与页面区域有交集的图层：
        组 → 嵌套容器 div（组不切图，坐标相对父组 bbox）；
        文本（text_info.text 非空）→ 真实文字 div（内容 HTML 转义）；
        其余叶子 → render_layer_png 渲染图层自身像素（透明底，不含其他元素），
        并裁掉透明边输出最小切图，HTML 定位与宽高同步偏移/收缩。
    参数：doc_id —— 文档 id；nodes —— 图层节点数组；parent_left/parent_top ——
        父容器原点（顶层节点传页面原点）；page —— 页面上下文字典（含 w/area/asset_dir）；
        layout —— 'vw'|'px'；rules —— CSS 规则收集列表（就地追加）；
        used_names —— 本页资源名占用集合；files —— zip 内路径到字节的映射（就地追加）
    返回：本层节点生成的 HTML 片段字符串
    """
    parts = []
    base_w = page["w"]
    for node in nodes:
        if not node.get("visible", True):
            continue
        if node.get("w", 0) <= 0 or node.get("h", 0) <= 0:
            continue
        bbox = node["bbox"]
        if not _bbox_intersects(bbox, page["area"]):
            continue
        rel_left = bbox[0] - parent_left
        rel_top = bbox[1] - parent_top
        cls = "n" + str(node["id"])
        ti = node.get("text_info") or {}
        if node["kind"] == "group":
            rules.append(_node_css_rule(cls, node, rel_left, rel_top, base_w, layout, []))
            inner = _render_page_body(doc_id, node.get("children", []),
                                      bbox[0], bbox[1], page, layout,
                                      rules, used_names, files)
            parts.append(f'<div class="{cls}">{inner}</div>')
        elif node["kind"] == "text" and ti.get("text"):
            extra = _text_css_extra(ti, base_w, layout)
            rules.append(_node_css_rule(cls, node, rel_left, rel_top, base_w, layout, extra))
            parts.append(f'<div class="{cls}">{html.escape(str(ti["text"]))}</div>')
        else:
            # 切图用图层自身像素渲染（透明底），而非合成图裁剪，
            # 避免该区域内其他上层元素混入切图
            try:
                path = render_layer_png(doc_id, node["id"])
            except ValueError:
                path = None  # 无可渲染像素（如空组/纯调整层），跳过该图层
            if path is None:
                continue
            img = Image.open(path)
            alpha_box = img.getbbox()  # 非零像素包围盒，裁掉透明边得到最小切图
            if not alpha_box:
                continue  # 整层全透明，跳过
            buf = io.BytesIO()
            img.crop(alpha_box).save(buf, "PNG")
            data = buf.getvalue()
            key = _unique_asset_name(node, used_names)
            src = f'{page["asset_dir"]}/{key}.png'
            files[src] = data
            # 裁掉透明边后，HTML 定位需加上裁剪偏移量
            trim_left = rel_left + alpha_box[0]
            trim_top = rel_top + alpha_box[1]
            trim_w = alpha_box[2] - alpha_box[0]
            trim_h = alpha_box[3] - alpha_box[1]
            rules.append(_node_css_rule(cls, node, trim_left, trim_top, base_w,
                                        layout, ["  display: block;"],
                                        size_wh=(trim_w, trim_h)))
            alt = html.escape(str(node["name"]), quote=True)
            parts.append(f'<img class="{cls}" src="{html.escape(src, quote=True)}" alt="{alt}">')
    return "".join(parts)


def _page_html(title, body):
    """生成完整 HTML 页面外壳。

    功能：输出 DOCTYPE / meta / 标题，并以 <link> 引用共享样式表 css/style.css，
        页面内不写任何内联样式。
    参数：title —— 页面标题字符串；body —— <body> 内的 HTML 片段
    返回：完整 HTML 文档字符串
    """
    title = html.escape(str(title), quote=True)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="zh-CN">\n'
        "<head>\n"
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{title}</title>\n"
        '<link rel="stylesheet" href="css/style.css">\n'
        "</head>\n"
        "<body>\n"
        f"{body}\n"
        "</body>\n"
        "</html>\n"
    )


def _page_css(pages, layout, rules, with_toc):
    """生成共享样式表 css/style.css 内容。

    功能：包含 body 基础样式（白底、去边距、防横向溢出）、页面容器结构样式、
        每页容器的宽高规则（vw 按 100vw 基准换算，px 固定像素）、各图层规则，
        多画板时附加目录页样式。
    参数：pages —— 页面上下文字典列表（含 cls/w/h）；layout —— 'vw'|'px'；
        rules —— 各图层 CSS 规则列表；with_toc —— 是否附加目录页样式
    返回：完整 CSS 文本字符串
    """
    lines = [
        "/* 设计稿导出样式（自动生成） */",
        "body {",
        "  margin: 0;",
        "  background: #fff;",
        "  overflow-x: hidden;",
        "}",
        ".page {",
        "  position: relative;",
        "  margin: 0 auto;",
        "  overflow: hidden;",
        "  background: #fff;",
        "}",
    ]
    for p in pages:
        lines.append(f".{p['cls']} {{")
        lines.append(f"  width: {_fmt_len(p['w'], p['w'], layout)};")
        lines.append(f"  height: {_fmt_len(p['h'], p['w'], layout)};")
        lines.append("}")
    lines.extend(rules)
    if with_toc:
        lines.append(_TOC_CSS)
    return "\n".join(lines) + "\n"


def _toc_html(meta, pages):
    """生成多画板目录页 index.html 内容。

    功能：目录页逐项展示画板名称、宽高与对应 page-N.html 链接，样式来自共享样式表。
    参数：meta —— 文档 meta 字典；pages —— 页面上下文字典列表（含 file/toc_name/w/h）
    返回：目录页完整 HTML 字符串
    """
    items = []
    for p in pages:
        name = html.escape(str(p["toc_name"]), quote=True)
        items.append(
            f'<li><a href="{p["file"]}">{name}'
            f'<span class="toc-size">{p["w"]} × {p["h"]}</span></a></li>'
        )
    doc_name = html.escape(str(meta.get("name", "设计稿")))
    body = f'<div class="toc"><h1>{doc_name}</h1><ul>{"".join(items)}</ul></div>'
    return _page_html(meta.get("name", "设计稿"), body)


def export_html_zip(doc_id, layout="vw"):
    """导出静态网页 zip。

    功能：基于缓存的图层树（layers.json）把已解析文档导出为可直接打开的静态网页包：
        单页（无画板/仅 1 个画板）产出 index.html + css/style.css + assets/*.png；
        多画板产出目录页 index.html + page-1.html...page-N.html（每页仅含该画板
        bbox 内图层，坐标减去画板原点）+ css/style.css（共享）+ assets/page-N/*.png。
        vw 模式所有长度按画板/画布宽换算为 vw 整页等比缩放，px 模式固定像素还原。
        zip 内 index.html 位于根目录（无额外根前缀）。
    参数：doc_id —— 文档 id；layout —— 'vw'（自适应，默认）或 'px'（固定像素）
    返回：(zip 文件字节 bytes, 下载文件名主体 str，即设计稿名称)
    异常：doc_id 无效抛 FileNotFoundError；
        composite.png 缺失抛 ValueError("文档 {doc_id} 未生成合成图，请重新解析")
    """
    layout = "px" if str(layout).lower() == "px" else "vw"
    meta, tree = load_doc(doc_id)
    if not os.path.isfile(os.path.join(doc_dir(doc_id), "composite.png")):
        raise ValueError(f"文档 {doc_id} 未生成合成图，请重新解析")

    # 页面划分：meta 中记录了 >=2 个有效画板时走多页，否则整稿单页回退
    artboards = [
        a for a in (meta.get("artboards") or [])
        if isinstance(a.get("bbox"), list) and len(a["bbox"]) == 4
        and a["bbox"][2] > a["bbox"][0] and a["bbox"][3] > a["bbox"][1]
    ]
    if len(artboards) > 1:
        pages = []
        for i, ab in enumerate(artboards, 1):
            l, t, r, b = ab["bbox"]
            pages.append({
                "file": f"page-{i}.html",
                "cls": f"page-{i}",
                "title": f'{meta.get("name", "")} - {ab.get("name") or f"画板{i}"}',
                "toc_name": ab.get("name") or f"画板{i}",
                "w": r - l,
                "h": b - t,
                "area": (l, t, r, b),
                "origin": (l, t),
                "asset_dir": f"assets/page-{i}",
            })
    else:
        pages = [{
            "file": "index.html",
            "cls": "page-1",
            "title": meta.get("name", "设计稿"),
            "toc_name": meta.get("name", "设计稿"),
            "w": meta["width"],
            "h": meta["height"],
            "area": (0, 0, meta["width"], meta["height"]),
            "origin": (0, 0),
            "asset_dir": "assets",
        }]

    multi = len(pages) > 1
    files = {}
    rules = []
    for page in pages:
        used_names = set()
        body = _render_page_body(doc_id, tree, page["origin"][0], page["origin"][1],
                                 page, layout, rules, used_names, files)
        inner = f'<div class="page {page["cls"]}">{body}</div>'
        if multi:
            files[page["file"]] = _page_html(page["title"], inner)
        else:
            files["index.html"] = _page_html(page["title"], inner)
    if multi:
        files["index.html"] = _toc_html(meta, pages)

    files["css/style.css"] = _page_css(pages, layout, rules, multi)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(files):
            zf.writestr(path, files[path])
    return buf.getvalue(), safe_name(meta.get("name", "未命名"))
