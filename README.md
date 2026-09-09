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
- 一键导出：静态网页 zip（vw 自适应 / px 固定，多画板多页面 + 目录页）、Figma 可导入 SVG zip（拖入 Figma 画布即转为可编辑矢量图层与文本）

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
    ├── mcp_server.py    # MCP Server（streamable-http 网络传输，端口 8643；保留 stdio 兜底）
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
- 依赖库：见 [requirements.txt](requirements.txt)（`flask`、`psd-tools[composite]`、`pillow`、`mcp`）

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动服务

```bash
./start.sh
```

脚本会自动停止旧服务、创建虚拟环境、按需安装依赖，并启动两个服务：
- 网页版 <http://127.0.0.1:8642>（前台运行，上传 PSD 即可使用）
- 网络版 MCP `http://127.0.0.1:8643/mcp`（后台常驻，日志 `/tmp/psd-annotate-mcp.log`）

可重复执行，无需手动清理端口。

也可以手动启动网络版 MCP：

```bash
cd psd-annotate
python mcp_server.py --http --port 8643
```

### 3. 接入 MCP 客户端（可选）

网络版 MCP（推荐）：在客户端的 MCP 配置中添加 URL 条目（如 `~/.workbuddy/mcp.json`）：

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

stdio 兜底：也可以让客户端以子进程方式拉起（`command` + `args` 指向 `mcp_server.py`，不带 `--http`）。

配置后即可让 AI 直接解析 PSD、查询图层标注、导出切图。

### Windows 免安装 exe（可选）

在 Windows 机器上把项目打包成单文件 `psd-annotate.exe`，之后双击即可运行、无需安装 Python：

```bat
build_exe.bat
```

脚本会自动创建独立构建虚拟环境（`.venv-build`）、安装依赖与 PyInstaller，并按 [psd-annotate.spec](psd-annotate/psd-annotate.spec) 生成 `psd-annotate\dist\psd-annotate.exe`（单文件，首次打包约需几分钟）。

使用说明：

- 把 `psd-annotate.exe` 复制到任意目录，双击运行；控制台窗口显示日志，关闭窗口或 `Ctrl+C` 退出
- 启动后自动打开浏览器 <http://127.0.0.1:8642>，同时提供网络版 MCP `http://127.0.0.1:8643/mcp`（启动失败会降级，不影响网页版）
- `uploads/`、`output/` 数据目录生成在 exe 同级目录
- 前置条件：打包机需安装 Python 3.9+ 并加入 PATH（exe 的最终使用者无需任何环境）

## HTTP API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/upload` | 上传并解析 PSD，返回文档 meta |
| GET | `/api/docs` | 列出已解析文档 |
| GET | `/api/doc/<doc_id>` | 获取文档 meta 与图层树 |
| GET | `/api/layer/<doc_id>/<layer_id>/png` | 渲染图层 PNG（`?download=1` 触发下载） |
| GET | `/api/export/<doc_id>/html` | 导出静态网页 zip（`?layout=vw` 自适应 / `px` 固定，默认 vw；含 index.html、css/style.css、assets 切图；多画板自动多页面 + 目录页） |
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
| 静态网页导出 | 一键导出 zip（HTML + CSS + 切图），vw 自适应/px 固定双模式，文本图层真实渲染，多画板自动多页面 + 目录页 | 已完成 |
| Figma 导出 | 一键导出 SVG zip（Figma 官方支持的导入格式），组/文本/位图分层映射，多画板多文件，文本可编辑 | 已完成 |
| MCP Server | 八个工具（解析/文档搜索/树/图层搜索/详情/导出×2/列表） | 已完成 |
| 图层懒渲染缓存 | assets 目录按需生成图层 PNG | 已完成 |

### 后续规划

- 切图导出可选 2x/3x 缩放与 SVG 格式
- 标注单位支持 dp/pt（移动端、iOS 基准）
- 图层信息展示切图切片（Slice）数据
- 网页导出文本行高/字距精确度量

## License

[MIT](LICENSE)
