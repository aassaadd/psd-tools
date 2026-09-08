# psd-tools

网页版 PSD 设计稿标注工具（类似"标你妹"）：上传 PSD 后在网页上查看效果图与图层热区，点击图层即可查看尺寸/位置/透明度/字体等信息与 CSS 示例，并支持导出图层素材。同时内置 MCP Server，可供 AI 客户端直接解析 PSD、查询图层标注、导出切图。

## 功能特性

**网页版（Web）**

- 上传 `.psd` 文件（最大 500MB），自动渲染整体效果图并构建图层树
- 图层树侧边栏：分组层级、可见性标识、图层与画布双向高亮定位
- 画布热区：鼠标悬停/点击任意图层，查看标注信息
- 标注详情：X/Y/宽/高、透明度、混合模式；文本图层可解析文字内容、字体、字号、颜色
- CSS 示例一键复制（position/left/top/width/height/opacity/mix-blend-mode/字体样式）
- 标注单位切换：`px` / `rpx`（750 设计稿基准）/ `%`
- 测距工具：自由测距 + 自动吸附附近图层，显示与相邻图层的间距参考线
- 图层 PNG 预览与下载（透明背景，支持图层组整体导出，按需懒渲染并缓存）

**MCP Server（供 AI 客户端调用）**

| 工具 | 说明 |
| --- | --- |
| `psd_list_docs` | 列出已解析过的所有 PSD 文档 |
| `psd_parse` | 解析本地 `.psd` 文件，返回 doc_id、画布尺寸与图层树概览 |
| `psd_layer_tree` | 获取图层树（可控制展开深度，防止 token 爆炸） |
| `psd_find_layers` | 按图层名称模糊搜索 |
| `psd_layer_info` | 获取图层完整标注信息 + CSS 示例 |
| `psd_export_layer` | 导出图层为 PNG 素材（默认存到 `~/Downloads/psd-assets`） |

## 目录结构

```
psd-tools
└── psd-annotate
    ├── app.py           # Flask Web 服务与 HTTP 路由（端口 8642）
    ├── core.py          # PSD 解析核心逻辑（Web 与 MCP 共用）
    ├── mcp_server.py    # MCP Server（stdio 传输）
    ├── static
    │   └── index.html   # 前端页面（原生 JS，单文件）
    ├── uploads/         # 上传的 PSD 源文件（按 doc_id 保存，供图层懒渲染）
    └── output/          # 解析产物，按 doc_id 分目录
        └── <doc_id>/
            ├── composite.png   # 整体效果图
            ├── meta.json       # 文档信息（名称/尺寸/图层数/解析时间）
            ├── layers.json     # 图层树
            └── assets/         # 已渲染的图层 PNG 缓存
```

## 环境依赖

- macOS / Linux / Windows
- Python 3.9+
- 依赖库：`flask`、`psd-tools`、`pillow`、`mcp`

## 快速开始

### 1. 安装依赖

```bash
pip install flask psd-tools pillow mcp
```

### 2. 启动网页版

```bash
cd psd-annotate
python app.py
```

浏览器访问 <http://127.0.0.1:8642>，上传 PSD 即可使用。

### 3. 接入 MCP 客户端（可选）

在 Trae / Claude Desktop 等客户端的 MCP 配置中添加：

```json
{
  "mcpServers": {
    "psd-annotate": {
      "command": "python",
      "args": ["/绝对路径/psd-tools/psd-annotate/mcp_server.py"]
    }
  }
}
```

配置后即可让 AI 直接解析 PSD、查询图层标注、导出切图。

## HTTP API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/upload` | 上传并解析 PSD，返回文档 meta |
| GET | `/api/docs` | 列出已解析文档 |
| GET | `/api/doc/<doc_id>` | 获取文档 meta 与图层树 |
| GET | `/api/layer/<doc_id>/<layer_id>/png` | 渲染图层 PNG（`?download=1` 触发下载） |
| GET | `/output/<doc_id>/<file>` | 访问解析产物静态文件 |

## 技术方案

- **解析**：基于 [psd-tools](https://psd-tools.readthedocs.io/) 读取 PSD，`composite()` 渲染效果图与图层像素；文本图层从 engine_data 提取字体/字号/颜色
- **图层定位**：解析时按深度优先顺序给图层编号（`L1`、`L2`…），导出时按同一顺序重新定位图层对象，实现按需懒渲染
- **服务**：Flask 提供 HTTP 接口与静态页面；MCP Server 复用 `core.py`，与网页版能力一致
- **数据**：解析产物落盘为 JSON + PNG，重启服务不丢失，重复上传同一文件生成新 doc_id

## 开发规划与进度

| 模块 | 内容 | 状态 |
| --- | --- | --- |
| PSD 解析核心 | 效果图渲染、图层树、文本信息提取、图层懒渲染 | 已完成 |
| 网页版 | 上传、图层树、热区标注、单位切换、测距吸附、CSS 复制、切图导出 | 已完成 |
| MCP Server | 六个工具（解析/树/搜索/详情/导出/列表） | 已完成 |
| 图层懒渲染缓存 | assets 目录按需生成图层 PNG | 已完成 |

### 后续规划

- 页面/画板（Artboard）多画布支持
- 切图导出可选 2x/3x 缩放与 SVG 格式
- 标注单位支持 dp/pt（移动端、iOS 基准）
- 图层信息展示切图切片（Slice）数据

## License

[MIT](LICENSE)
