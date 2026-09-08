---
name: psd-annotate
description: PSD 设计稿解析、标注与素材导出。通过 psd-annotate MCP（或本地 Python）解析 .psd 文件，获取图层树、每个图层的位置/尺寸/字体/颜色/CSS 示例，导出图层 PNG 素材，或将 PSD 1:1 还原为 HTML 页面。触发词：解析 PSD、PSD 标注、图层信息、切图/导出素材、PSD 转 HTML、还原设计稿、标你妹。
agent_created: true
---

# PSD 标注（psd-annotate MCP）

解析 PSD 设计稿，产出图层标注（X/Y/宽/高/透明度/混合模式/文本字体字号颜色 + CSS 示例）并导出图层素材。后端为本地项目 `/Users/zhaohaochen/git/psd-tools/psd-annotate/`（Flask 网页版 + stdio MCP server，共用 `core.py`）。

## 调用方式（按优先级）

1. **MCP 连接器 `psd-annotate`**：若会话中已有 `mcp__psd-annotate__*` 工具，直接调用（首选，工具名见 references/tools.md）。
2. **本地 Python 直调**：MCP 未连接时，用 venv Python 导入 `core.py`，接口见 references/tools.md 末尾。
3. **独立 MCP 客户端脚本**：需要脚本化批量操作时，用 `scripts/mcp_client.py`（stdio JSON-RPC）。

Python 一律使用 venv 解释器：`/Users/zhaohaochen/.workbuddy/binaries/python/envs/default/bin/python`。

## 标准工作流

### 1. 解析 PSD
`psd_parse(file_path)`：file_path 为 .psd 绝对路径。返回 doc_id、画布宽高、前两层图层树概览。解析需数秒到数十秒。同一文件重复解析会生成新 doc_id。

### 2. 浏览/搜索图层
- `psd_layer_tree(doc_id, max_depth)`：默认深度 3，深层以 `children_omitted` 计数表示；需要更深层级时增大 max_depth 逐层展开，避免一次性拉全树。
- `psd_find_layers(doc_id, keyword)`：按名称模糊搜索（不区分大小写），适合"找按钮图层"类请求。

### 3. 查询标注
`psd_layer_info(doc_id, layer_id)`：返回完整信息，layer_id 形如 `L5`。含 bbox、opacity、blend、text_info（文本内容/字体/字号/颜色）和现成的 CSS 代码片段（position:absolute 定位）。

### 4. 导出素材 —— 两个工具的选择是关键
- **`psd_export_layer_crop`（默认首选）**：按图层 bbox 裁剪整体效果图。保留叠加效果/剪贴蒙版语义，像素与设计稿完全一致。做 1:1 还原、页面重建必须用它。
- **`psd_export_layer`**：独立渲染透明背景 PNG。适合切图给开发复用，但颜色填充/剪贴蒙版类图层会有叠加语义损失。
- 两者均返回 `saved` 路径；crop 版额外返回 `offset_x/offset_y`（实际裁剪起点，图层被画布边缘裁剪时与 bbox 不同，**定位 img 时必须用 offset 而非 bbox**）。

## 1:1 还原 PSD → HTML（已验证 100% 像素一致）

1. `psd_parse` → doc_id；`psd_layer_tree` 拉全树，收集所有可见叶子图层（kind 为 pixel/text/shape）。
2. 对每个叶子：`psd_layer_info` 拿位置 + `psd_export_layer_crop` 拿素材与 offset。
3. 生成 HTML：画布容器尺寸 = PSD 宽高；每个图层一个绝对定位 `<img>`，`left/top` 用 offset（offset 为负时同样直接使用），`width/height` 用 bbox 尺寸；opacity<1 加 opacity，blend≠normal 加 mix-blend-mode。
4. 文本图层也按图片导出（不重建文字 DOM），保证字体渲染 100% 一致；若需要可编辑文本，则用 text_info 另行生成 DOM 文字节点。
5. 验证：用 Playwright 以 PSD 尺寸为视口截图，与 composite 图做像素对比（PIL + numpy）。

完整客户端示例见 `scripts/mcp_client.py`。

## 网页版工具

`cd /Users/zhaohaochen/git/psd-tools/psd-annotate && python app.py` 后访问 http://127.0.0.1:8642：上传 PSD、图层树、热区点击标注、px/rpx/% 单位切换、热区间吸附测量（Δx/Δy）、导出素材。用户问"标你妹式标注"即指此工具。

## 注意事项

- 大文件上传到网页版可能被内嵌预览面板代理拦截（Failed to fetch）；MCP/本地 Python 路径无此问题。
- 渲染依赖：psd-tools + aggdraw + scipy + scikit-image（已装在 venv）。缺依赖时 `pip install "psd-tools[composite]"`（已配置清华镜像）。
- 修改 `mcp_server.py`/`core.py` 后，MCP 连接器需重新"信任"激活才会加载新代码。

## Resources

### scripts/
- `mcp_client.py` — 独立 stdio JSON-RPC MCP 客户端：可直接调用 psd-annotate MCP 的 7 个工具，附"解析→标注→导出→生成 1:1 HTML"完整示例（`rebuild_demo`）。

### references/
- `tools.md` — 7 个 MCP 工具的参数/返回详解，以及 MCP 未连接时 `core.py` 的本地 Python 直调接口。
