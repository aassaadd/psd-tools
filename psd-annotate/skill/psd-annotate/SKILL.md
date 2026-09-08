---
name: psd-annotate
description: PSD 设计稿解析、标注与素材导出。通过 psd-annotate 网络版 MCP（streamable-http）解析 .psd 文件，获取图层树、每个图层的位置/尺寸/字体/颜色/CSS 示例，导出图层 PNG 素材，或将 PSD 1:1 还原为 HTML 页面。触发词：解析 PSD、PSD 标注、图层信息、切图/导出素材、PSD 转 HTML、还原设计稿、标你妹。
agent_created: true
---

# PSD 标注（psd-annotate 网络版 MCP）

解析 PSD 设计稿，产出图层标注（X/Y/宽/高/透明度/混合模式/文本字体字号颜色 + CSS 示例）并导出图层素材。后端为本仓库 `psd-annotate/` 目录（Flask 网页版 + MCP 网络服务，共用 `core.py`）。

## 调用方式（网络版 MCP）

- 服务传输类型 `streamable-http`，默认端点 `http://127.0.0.1:8643/mcp`。在所用 MCP 客户端的配置中以 URL 方式接入（timeout 建议 ≥300s，大 PSD 解析耗时长）：

  ```json
  {
    "mcpServers": {
      "psd-annotate": {
        "type": "streamableHttp",
        "url": "http://127.0.0.1:8643/mcp",
        "timeout": 300000,
        "disabled": false
      }
    }
  }
  ```

- 若会话中已有 `mcp__psd-annotate__*` 工具，直接调用（工具名见 references/tools.md）。
- 服务未启动（工具连接失败）时，在仓库根目录执行 `./start.sh` 拉起（同时启动网页版 8642 与 MCP 8643），或单独启动 MCP：`python psd-annotate/mcp_server.py --http --port 8643`（依赖见仓库 requirements.txt）。
- **不要**用 Python 脚本直接 import core 或拉起 stdio 子进程来调用——一律走网络 MCP。

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
3. 生成 HTML：画布容器尺寸 = PSD 宽高；每个图层一个绝对定位 `<img>`，`left/top` 用 offset（offset 为负时同样直接使用），`width/height` 用 bbox 尺寸；opacity<1 加 opacity，blend≠normal 加 mix-blend-mode。**DOM 顺序 = 图层树正序**（先出现的在下层，浏览器后写的元素在上），不要倒序。**出血图层例外**：bbox 超出画布时，crop 会被裁剪到画布内，返回的 offset 也被截到 [0,0] 起始、实际 PNG 尺寸 < bbox 尺寸——此时 width/height 必须用实际 PNG 尺寸（读文件），否则浏览器会拉伸变形。
4. 文本图层也按图片导出（不重建文字 DOM），保证字体渲染 100% 一致；若需要可编辑文本，则用 text_info 另行生成 DOM 文字节点。
5. 验证：无 Playwright 时可等效验证——用 PIL 按树序把各 crop 素材 alpha_composite 到画布（位置用 offset），与 output/<doc_id>/composite.png 逐像素对比（PIL + numpy）；有 Playwright 则以 PSD 尺寸为视口截图对比。
6. 注意：layers.json 里叶子 kind 实际值是 `layer`/`group`（不是 pixel/text/shape）；crop 素材落在 output/<doc_id>/crops/，需自行拷贝到目标目录。

## 交互化改造（1:1 视觉 + 透明交互层）

在 1:1 还原基础上把静态页变成可交互表单/页面。核心模式：**底层图不动，交互控件用透明元素按图层 bbox 坐标绝对定位叠上去**。

1. 从图层树找到交互目标（输入框底、按钮、头像区等）：`psd_find_layers` 按名称搜，或看树里 name/kind 判断。
2. 覆盖层类型与要点：
   - **输入框**：透明 `<input>` 覆盖输入框底图，`background/border/outline` 全 transparent；文字左边距 = 标签文字 x − 输入框底 x（对齐设计稿留白）；focus 加极淡 inset 阴影给反馈。
   - **单选/切换**（如性别）：整个字段区一个透明点击层；首次切换后隐藏 PSD 原字图片、改显 DOM 文字（避免改字后与图片文字错位），勾选态用 CSS `::after` 对勾叠在原勾选框图上。
   - **上传**：透明 label 覆盖上传区 + 隐藏 `<input type=file>`，`FileReader` 读图后 `object-fit:cover` 预览填满该区域。
   - **按钮**：点击区域用按钮条底图的可见范围（出血裁剪后的实际区域），不必只圈文字。
3. 校验/toast：按业务必填顺序逐项校验，toast 提示 + `focus()` 聚焦缺失项；toast 用 fixed 定位、transform 过渡。
4. 字体统一 `-apple-system,"PingFang SC",sans-serif`，字号参照设计稿文字图层高度（如 32px 高 → font-size 32px）。

## 网页版工具

在仓库根目录执行 `./start.sh` 后访问 http://127.0.0.1:8642：上传 PSD、图层树、热区点击标注、px/rpx/% 单位切换、热区间吸附测量（Δx/Δy）、导出素材。用户问"标你妹式标注"即指此工具。该脚本同时后台拉起网络版 MCP（8643）。

## 注意事项

- 大文件上传到网页版可能被内嵌预览面板代理拦截（Failed to fetch）；MCP 路径无此问题。
- 工具调用异常时先确认服务已启动（在仓库根目录重跑 `./start.sh` 可拉起/重启服务）；服务重启后，MCP 连接需断开重连。

## Resources

### references/
- `tools.md` — 7 个 MCP 工具的参数/返回详解。
