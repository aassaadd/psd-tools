# psd-annotate 工具参考

MCP server：`/Users/zhaohaochen/git/psd-tools/psd-annotate/mcp_server.py`（stdio，`python mcp_server.py` 由客户端拉起）。已注册于 `~/.workbuddy/mcp.json`（名称 `psd-annotate`）。

## MCP 工具（7 个）

所有工具返回 JSON 字符串；出错时返回 `{"error": "..."}`。

### psd_list_docs()
列出已解析过的所有文档。返回 `[{id, name, width, height, layer_count, parsed_at}, ...]`。doc 缓存位于 `output/<doc_id>/`（composite.png、layers.json、meta.json）。

### psd_parse(file_path)
解析本地 .psd（绝对路径）。返回 `{"meta": {id, name, width, height, layer_count, parsed_at}, "layers_preview": [...]}`，preview 为前两层树。大文件需数秒到数十秒。

### psd_layer_tree(doc_id, max_depth=3)
图层树。节点字段：`id`（形如 L3，全局唯一）、`name`、`kind`（group/pixel/text/shape/adjustment/fill）、`bbox` `[left, top, right, bottom]`（可含负值，出血位图层会超出画布）、`w`、`h`、`visible`；text 节点附 `text` 内容；深层子树以 `children_omitted: <count>` 截断。

### psd_find_layers(doc_id, keyword)
按名称模糊搜索（大小写不敏感，子串匹配）。返回 `{"matched": n, "layers": [{id, name, kind, bbox, w, h}]}`。

### psd_layer_info(doc_id, layer_id)
完整标注：bbox/w/h、`opacity`（0~1）、`blend`（混合模式）、`visible`、`text_info`（仅文本层：text、fonts[]、font_size、color）以及 `css` —— 现成 CSS 片段（position:absolute + left/top/width/height + 字体样式）。

### psd_export_layer(doc_id, layer_id, output_dir="")
独立渲染图层为透明背景 PNG（支持图层组整体导出，按需渲染约 1~2 秒）。返回 `{saved, name, w, h}`。默认存到 `~/Downloads/psd-assets/`。
**局限**：颜色填充/剪贴蒙版类图层的叠加语义会丢失。

### psd_export_layer_crop(doc_id, layer_id, output_dir="")
按图层 bbox 裁剪整体效果图（composite）。像素与设计稿完全一致，**1:1 还原/页面重建必须用这个**。返回 `{saved, name, offset_x, offset_y, w, h}`；`offset` 是实际裁剪起点——图层被画布边缘裁剪时与 bbox 的 left/top 不同（含负值），定位时用 offset。

## 本地 Python 直调（MCP 未连接时的等价接口）

```python
import sys
sys.path.insert(0, "/Users/zhaohaochen/git/psd-tools/psd-annotate")
import core

meta = core.parse_psd_file("/path/to.psd")   # 返回 meta dict（含 id）
doc_id = meta["id"]
_, tree = core.load_doc(doc_id)              # -> layers.json（完整树，无深度截断）
node = core.find_layer(tree, "L3")           # 按 id 查节点
hits = core.find_layers_by_name(tree, "按钮") # 按名称搜索
css = core.css_snippet(node)                 # CSS 片段
png = core.render_layer_png(doc_id, "L3")    # -> output/<id>/layers/L3.png（透明背景）
dest, ox, oy = core.export_layer_crop(doc_id, "L3")  # crop 版，返回 (路径, offset_x, offset_y)
docs = core.list_docs()
```

解释器必须用 venv：`/Users/zhaohaochen/.workbuddy/binaries/python/envs/default/bin/python`。
依赖：psd-tools、pillow、flask、aggdraw、scipy、scikit-image（`pip install "psd-tools[composite]"`，清华镜像已配置）。

## 常见坑

- **测试脚本直接调 `parse_psd_file` 不会写 `uploads/`**：随后调 `render_layer_png` 会因找不到源 PSD 报错；正常走 `psd_parse`（内部会复制到 uploads/）无此问题。直调 core 时先 `shutil.copy(src, core.UPLOAD_DIR/<doc_id>.psd)`。
- Flask 改代码后必须重启进程才生效；MCP server 每次调用由客户端重新拉起，改完即生效。
- 服务器后台启动命令：`cd /Users/zhaohaochen/git/psd-tools/psd-annotate && python app.py`（端口 8642）。
