# 运行数据格式

每次任务在 `evaluation/runs/` 保存一个 JSON，并追加到 `runs.jsonl`。真实 Key 永不写入。

主要字段：

- `user_request`：原始中文要求。
- `modeling_spec`：通过 Schema 的结构化规格及 `value_sources` / `assumptions`。
- `qwen_generation`：实际模型 ID、用量和原始结构化结果。
- `qwen_plan`：完整 assistant 工具调用消息、调用 ID、名称与参数。
- `before_state` / `after_state`：写操作前后由官方 MCP 读取的对象状态。
- `execution`：MCP 工具结果；长结果可在后续版本拆分为摘要和原始文件。
- `initial_validation`：自动修复前的完整确定性报告；未失败时与最终报告相同。
- `validation`：每项 expected / actual / error / tolerance / object_ids。
- `repairs`：验证失败、Qwen 修复理由、Undo、重建与重新验收。
- `screenshot_path`：本次任务结束时经官方 MCP 捕获的 Rhino 视口图。
- `qwen_model` / `qwen_temperature` / `runtime_seconds`：模型、温度和端到端耗时。
- `manual_modification`：用户手工修改说明；未提供时为 `null`。
- `slot`：本次 Rhino 槽位；槽位名称不是稳定身份。
- `accepted`：用户是否接受（PoC UI 预留）。
- `saved_at_utc`：保存时间。

未来训练前仍应由用户填写 `manual_modification` 与 `accepted`，并在汇总前执行严格脱敏检查；一天版本不进行微调。
