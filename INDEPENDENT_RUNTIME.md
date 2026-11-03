# 独立运行架构

```text
用户自然语言
  → 本程序（FastAPI，127.0.0.1:8766）
  → Qwen API（直接 HTTPS）
  → curve_predictor（127.0.0.1:8777）
  → RhinoCommon 内存校验
  → 预览与误差
  → 用户确认令牌
  → 项目内 Rhino MCP Router
  → Rhino 8
```

Codex 不在运行链路中。项目启动后可以关闭 Codex；Qwen API、预测器、RhinoCommon 校验和 Rhino MCP 写入均由本程序独立完成。

写入门禁：预测拒绝、Rhino 未连接、RhinoCommon 校验失败、确认令牌缺失/过期或用户未确认时，均禁止调用 Rhino 写入。
