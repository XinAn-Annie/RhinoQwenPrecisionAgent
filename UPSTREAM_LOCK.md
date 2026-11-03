# 上游锁定与环境记录

记录日期：2026-10-30（Asia/Shanghai）

## Rhino

- Rhino 8 Educational Lab License
- 文件/产品版本：`8.33.26188.13001`
- 可执行文件：`D:\xiazai\System\Rhino.exe`
- 实测文档 MCP 端点：`http://localhost:10500/`
- 实测槽位：`aardvark`，`adopted: true`（槽位名重启后可能变化）

## McNeel 官方 Rhino MCP

- 项目：[mcneel/RhinoAI](https://github.com/mcneel/RhinoAI)
- 文档：[Rhino MCP Platform](https://mcneel.github.io/RhinoAI/)
- Plugin / Router：`0.3.0`
- Router：`D:\Xiangmu\Rhino\RhinoQwenPrecisionAgent\runtime\router\win-x64\rhino-mcp-router.exe`
- Transport：stdio（Router）→ 本地 Rhino HTTP `10500`
- MCP 协议：`2025-06-18`
- 实测工具数：32；包括 `list_objects`、`get_context`、`list_slots`、`run_command`、`run_python`、视口、选择、文档与 GH1 工具。
- 完整实测 Schema：运行时通过项目内 Router 的 `tools/list` 动态读取。

官方包必须在 Rhino 用户包注册目录留下加载副本；包原件和本项目均在 D 盘。官方 `run_python` 自身会在 Windows 用户临时目录生成瞬时脚本，这是上游实现行为，不是项目下载目录。

## Qwen / 百炼

- 控制台地域：华北 2（北京）
- API 类型：OpenAI-compatible Chat Completions（SDK 仅作协议客户端，不调用 OpenAI 服务）
- 实测模型：`qwen3.8-flash`（Key 权限仅开放此模型）
- Base URL：北京地域业务空间专属 OpenAI-compatible `/compatible-mode/v1` 域名；完整域名保存在 `.env`，本文件不记录 Key。
- API：OpenAI-compatible Chat Completions；`openai` Python 包仅作为协议 SDK，网络请求指向阿里云百炼，不调用 OpenAI 服务。
- 2026-10-30 实测：普通对话、JSON 输出、Function Calling 均成功；真实模型 ID 返回 `qwen3.8-flash`。

## 已知问题

- Rhino 0.3.0 是 1.0 前版本，升级后必须重新读取工具名和 Schema。
- 上游 `run_python` MCP 外层可能 `isError=false`，但 payload 内包含脚本错误；客户端已同时检查 payload。
- Rhino 自带 Yak CLI 在本机因缺少 `DocoptNet.dll` 无法启动；官方包按 Yak 用户目录格式注册后由 Rhino 成功加载。
- Qwen `json_object` 仍可能首次返回不匹配 Schema 的字段；客户端把真实 Pydantic 错误返回 Qwen，最多三次，不通过则停止且不写 Rhino。
