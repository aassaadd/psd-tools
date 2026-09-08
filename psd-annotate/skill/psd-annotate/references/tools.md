# psd-annotate 工具参考

网络版 MCP：端点 `http://127.0.0.1:8643/mcp`（streamable-http），在 MCP 客户端配置中以 URL 方式接入（名称 `psd-annotate`）。服务端代码为仓库内 `psd-annotate/mcp_server.py`，由仓库根目录 `./start.sh` 拉起（或 `python psd-annotate/mcp_server.py --http --port 8643`）。

## MCP 工具（8 个）

所有工具返回 JSON 字符串；出错时返回 `{"error": "..."}`。

### psd_list_docs()
列出已解析过的所有文档。返回 `[{id, name, width, height, layer_count, parsed_at}, ...]`（按解析时间倒序）。doc 缓存位于 `output/<doc_id>/`（composite.png、layers.json、meta.json）。

### psd_find_doc(keyword)
按设计稿名称模糊搜索已解析过的文档（不区分大小写，子串匹配；网页版上传与 MCP 解析的都能搜到）。返回 `{"matched": n, "docs": [{id, name, width, height, layer_count, parsed_at}]}`，用 `id`（doc_id）继续后续工具调用。

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

## 常见坑

- **禁止用 Python 直接 import core 或拉起 stdio 子进程调用**：一律走网络 MCP（`http://127.0.0.1:8643/mcp`）；连接失败说明服务未启动，重跑 `./start.sh`。
- `psd_parse` 内部会把源 PSD 复制到 `uploads/`，`psd_export_layer` 等导出工具依赖该副本，请勿手动清理。
- Flask/MCP 均为常驻进程；服务重启（重跑 `./start.sh` 会自动先停旧进程）后，MCP 连接需断开重连。
