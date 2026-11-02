from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI
from pydantic import ValidationError

from .config import Settings
from .modeling_spec import ModelingSpec


SPEC_SYSTEM = """你是 Rhino 精确建模规格工程师。把用户中文要求转换为严格匹配给定 JSON Schema 的 ModelingSpec。
可使用 box、cylinder、sphere、flange、enclosure、stepped_shaft、sketch_extrusion、loft_surface。dimensions 必须严格按 primitive 使用：
box=width/depth/height；cylinder=diameter/height；sphere=diameter；
flange=outer_diameter/thickness/bore_diameter/bolt_circle_diameter/bolt_hole_diameter/bolt_hole_count；
enclosure=width/depth/height/wall_thickness；stepped_shaft 的 dimensions 为空并使用 steps=[{{diameter,length}}]；
sketch_extrusion 使用 dimensions.height 和 sketch=[{{x,y}}] 闭合多边形点（不要重复首点）；
loft_surface 的 dimensions 为空并使用 sections=[{{z,width,depth,center_x,center_y,rotation_deg}}]，至少三截面且 z 递增。
可选 edge_treatment={{type:fillet|chamfer,size,selector:all|vertical|horizontal}}，不得用于 sphere/loft_surface。
flange 表示带中心通孔和等分螺栓通孔的整体法兰；enclosure 表示顶部开口、底部和四壁等厚的产品外壳。
复杂装配用多个 objects 和 center_aligned_xy、z_contact、interference_free 或 clearance 约束表达。位置使用 center_x/center_y/base_z。
法兰和外壳的关键尺寸缺失会显著改变结果，不能擅自猜测，必须返回无法执行的明确错误而不是伪造尺寸。
缺少但可安全默认的值写入 assumptions（字符串数组），并在对象 value_sources 标为 default；
由尺寸推导的值标为 derived；用户明确值标为 user。颜色必须是字符串，例如 blue。
expected_object_count 必须等于 objects 数量；constraint.targets 必须使用对象 name。
禁止输出 Markdown、解释文字或 Schema 之外的字段。"""


class QwenClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = AsyncOpenAI(
            api_key=settings.qwen_api_key.get_secret_value(),
            base_url=settings.qwen_base_url,
            timeout=90,
            max_retries=1,
        )

    async def health(self) -> dict[str, Any]:
        response = await self.client.chat.completions.create(
            model=self.settings.qwen_model,
            messages=[{"role": "user", "content": "只回复 OK"}],
            max_tokens=8,
            temperature=0,
        )
        return {"ok": True, "model": response.model, "text": response.choices[0].message.content}

    async def make_spec(self, request: str) -> tuple[ModelingSpec, dict[str, Any]]:
        schema = ModelingSpec.qwen_schema()
        messages = [
            {"role": "system", "content": SPEC_SYSTEM},
            {
                "role": "user",
                "content": json.dumps(
                    {"request": request, "required_json_schema": schema},
                    ensure_ascii=False,
                ),
            },
        ]
        errors: list[str] = []
        total_usage: dict[str, int] = {}

        for attempt in range(3):
            response = await self.client.chat.completions.create(
                model=self.settings.qwen_model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0,
            )
            if response.usage:
                for key, value in response.usage.model_dump().items():
                    if isinstance(value, int):
                        total_usage[key] = total_usage.get(key, 0) + value
            content = response.choices[0].message.content or "{}"
            try:
                raw = json.loads(content)
                spec = ModelingSpec.model_validate(raw)
                return spec, {
                    "model": response.model,
                    "usage": total_usage,
                    "raw": raw,
                    "attempts": attempt + 1,
                    "validation_errors": errors,
                }
            except (json.JSONDecodeError, ValidationError) as exc:
                error = str(exc)
                errors.append(error)
                messages.extend(
                    [
                        {"role": "assistant", "content": content},
                        {
                            "role": "user",
                            "content": (
                                "上一份 JSON 未通过本地 Pydantic 验证。请只返回完整修正后的 JSON，"
                                "不要解释，不要沿用错误字段。验证错误如下：\n" + error
                            ),
                        },
                    ]
                )

        raise RuntimeError("Qwen failed to produce a valid ModelingSpec after 3 attempts: " + errors[-1])

    async def approve_execution(self, spec: ModelingSpec, validation: dict | None = None) -> dict[str, Any]:
        tool = {
            "type": "function",
            "function": {
                "name": "execute_modeling_spec_via_rhino_mcp",
                "description": "Execute a schema-validated ModelingSpec through the official Rhino MCP",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "action": {"type": "string", "enum": ["execute", "repair"]},
                        "reason": {"type": "string"},
                    },
                    "required": ["task_id", "action", "reason"],
                    "additionalProperties": False,
                },
            },
        }
        prompt = "请审查规格并调用执行工具。"
        if validation:
            prompt = "验证失败。请根据报告调用 repair，提出最小修复理由。"
        response = await self.client.chat.completions.create(
            model=self.settings.qwen_model,
            messages=[
                {"role": "system", "content": "你是 Rhino 建模执行规划器。规格已通过本地 Schema；必须用给定工具继续。"},
                {"role": "user", "content": json.dumps({"prompt": prompt, "spec": spec.model_dump(), "validation": validation}, ensure_ascii=False)},
            ],
            tools=[tool],
            tool_choice="auto",
            temperature=0,
        )
        message = response.choices[0].message
        calls = message.tool_calls or []
        if not calls:
            raise RuntimeError(f"Qwen did not return a tool call: {message.content}")
        call = calls[0]
        return {
            "id": call.id,
            "name": call.function.name,
            "arguments": json.loads(call.function.arguments),
            "assistant_message": message.model_dump(mode="json"),
            "model": response.model,
            "usage": response.usage.model_dump() if response.usage else None,
        }

    async def answer(self, question: str, context: dict[str, Any]) -> dict[str, Any]:
        response = await self.client.chat.completions.create(
            model=self.settings.qwen_model,
            messages=[
                {"role": "system", "content": "你是只读 Rhino 中文助手。不得声称修改文档。明确区分实际观测与推断。"},
                {"role": "user", "content": json.dumps({"question": question, "rhino_context": context}, ensure_ascii=False)},
            ],
            temperature=0.2,
        )
        return {"text": response.choices[0].message.content, "model": response.model}
