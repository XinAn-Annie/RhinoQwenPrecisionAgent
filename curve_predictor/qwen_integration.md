# Qwen + curve_predictor + Rhino MCP 接入

本地预测服务：`py -3.12 api.py`，监听 `127.0.0.1:8777`。

Rhino Qwen Agent 已新增 `POST /api/curve-preview`：Qwen 只提取数值参数并调用 `curve_predictor`。返回值始终是预览；当前端点不会调用 Rhino MCP 写入。

安全状态机：

1. Qwen 提取 `width/height/depth/length/degree/is_closed`。
2. `curve_predictor` 返回 8×3 控制点、置信度、尺寸误差和警告。
3. `status=rejected` 时立即停止。
4. 只有 `status=preview_only` 才能进入 `RhinoCurveValidator.ValidatePreview`。
5. RhinoCommon 校验通过后仍只展示预览和误差。
6. 必须获得用户明确确认，才允许另一个写入端点调用 Rhino MCP；本交付没有提供自动写入路径。

当前模型的 `meets_qwen_minimum_standard=true`，但只适用于 `classroom_standard_open_and_closed_curve_families_v2`。超出训练范围、低置信度或 RhinoCommon 校验失败时仍必须拒绝。
