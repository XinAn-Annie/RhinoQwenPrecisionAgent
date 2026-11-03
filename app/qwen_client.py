from __future__ import annotations

import base64
import json
from pathlib import Path
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
参考图分析存在时，为每个对象设置 material={{name,base_color,metallic,roughness,transparency,finish}}；仅使用分析中有证据的材质观感，不得声称精确复刻厂商材料。
flange 表示带中心通孔和等分螺栓通孔的整体法兰；enclosure 表示顶部开口、底部和四壁等厚的产品外壳。
复杂装配用多个 objects 和 center_aligned_xy、z_contact、interference_free 或 clearance 约束表达。位置使用 center_x/center_y/base_z。
法兰和外壳的关键尺寸缺失会显著改变结果，不能擅自猜测，必须返回无法执行的明确错误而不是伪造尺寸。
缺少但可安全默认的值写入 assumptions（字符串数组），并在对象 value_sources 标为 default；
由尺寸推导的值标为 derived；用户明确值标为 user。颜色必须是字符串，例如 blue。
expected_object_count 必须等于 objects 数量；constraint.targets 必须使用对象 name。
禁止输出 Markdown、解释文字或 Schema 之外的字段。"""

REFERENCE_SYSTEM = """你是 Rhino 参考图分析工程师。只根据可见证据输出 JSON，不得把透视、阴影或单张照片推断为精确尺寸。
识别：主体类别、可见部件、可实现的 Rhino primitive、相对比例、轮廓、主色、材质候选、金属度、粗糙度、透明度和风格标签。
用户文字或图片中明确标注的尺寸可记录；没有可靠毫米尺寸时必须列出 critical_dimensions_missing。
输出字段：analysis_confidence(0..1), object_category, primitive_hint, visible_parts, proportions, dominant_colors[{hex,ratio}], material_candidates[{name,confidence,metallic,roughness,transparency,finish}], style_tags, observed_dimensions, critical_dimensions_missing, warnings, modeling_guidance。只输出 JSON。"""


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

    async def make_spec(self, request: str, reference_analysis: dict[str, Any] | None = None) -> tuple[ModelingSpec, dict[str, Any]]:
        schema = ModelingSpec.qwen_schema()
        messages = [
            {"role": "system", "content": SPEC_SYSTEM},
            {
                "role": "user",
                "content": json.dumps(
                    {"request": request, "reference_analysis": reference_analysis, "required_json_schema": schema},
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

    async def analyze_reference_image(self, request: str, image_path: Path, mime_type: str) -> dict[str, Any]:
        encoded=base64.b64encode(image_path.read_bytes()).decode("ascii")
        response=await self.client.chat.completions.create(
            model=self.settings.qwen_vision_model,
            messages=[
                {"role":"system","content":REFERENCE_SYSTEM},
                {"role":"user","content":[
                    {"type":"text","text":json.dumps({"user_request":request,"instruction":"分析参考图，区分可见证据、推断和缺失尺寸。"},ensure_ascii=False)},
                    {"type":"image_url","image_url":{"url":f"data:{mime_type};base64,{encoded}"},"min_pixels":65536,"max_pixels":2621440},
                ]},
            ],response_format={"type":"json_object"},temperature=0,
        )
        raw=json.loads(response.choices[0].message.content or "{}")
        raw["vision_model"]=response.model
        raw["usage"]=response.usage.model_dump() if response.usage else None
        return raw

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

    async def make_curve_request(self, request: str) -> dict[str, Any]:
        tool = {
            "type": "function",
            "function": {
                "name": "curve_predictor",
                "description": "生成仅供预览的 8 个曲线控制点；不能直接写入 Rhino。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "width": {"type": "number", "exclusiveMinimum": 0},
                        "height": {"type": "number", "minimum": 0},
                        "depth": {"type": "number", "minimum": 0},
                        "length": {"type": "number", "exclusiveMinimum": 0},
                        "degree": {"type": "integer", "minimum": 1, "maximum": 7},
                        "is_closed": {"type": "boolean"},
                    },
                    "required": ["width", "height", "length", "degree", "is_closed"],
                    "additionalProperties": False,
                },
            },
        }
        response = await self.client.chat.completions.create(
            model=self.settings.qwen_model,
            messages=[
                {"role":"system","content":"提取用户曲线的数值尺寸。需要预测控制点时必须调用 curve_predictor；缺少关键尺寸时明确报错，禁止猜测。"},
                {"role":"user","content":request},
            ], tools=[tool], tool_choice="auto", temperature=0,
        )
        calls=response.choices[0].message.tool_calls or []
        if not calls: raise RuntimeError("Qwen did not request curve_predictor; provide width, height, length, degree and closed/open state")
        return json.loads(calls[0].function.arguments)

    async def explain_curve_preview(self, params: dict[str, Any], prediction: dict[str, Any], validation: dict[str, Any] | None) -> str:
        validation_summary = None
        if validation:
            validation_summary = {"passed":validation.get("passed"),"checks":validation.get("checks"),"errors":validation.get("errors")}
        response = await self.client.chat.completions.create(
            model=self.settings.qwen_model,
            messages=[
                {"role":"system","content":"你是 Rhino 曲线预览助手。简洁说明预测置信度、尺寸/长度/端点/曲率校验和警告。只有 RhinoCommon 校验通过时才请求用户明确确认写入；否则明确拒绝写入。不得声称已经写入。"},
                {"role":"user","content":json.dumps({"parameters":params,"prediction":{"status":prediction.get("status"),"confidence":prediction.get("confidence"),"metrics":prediction.get("metrics"),"warnings":prediction.get("warnings")},"rhino_validation":validation_summary},ensure_ascii=False)},
            ],temperature=0.2,
        )
        return response.choices[0].message.content or ""
