from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from app.config import load_settings
from app.mcp_rhino_client import RhinoMCPClient
from app.modeling_spec import ModelingSpec
from app.qwen_client import QwenClient
from app.repair_loop import RepairLoop
from app.rhino_executor import RhinoExecutor
from app.safety import classify_tool
from app.validator import DeterministicValidator


CASES = json.loads((Path(__file__).with_name("cases.json")).read_text(encoding="utf-8"))

BASELINE_SYSTEM = """你是直接操作 Rhino MCP 的建模智能体。必须调用 run_python，一次创建用户要求的全部对象。
使用 __rhino_doc__ 和 RhinoCommon；所有实体必须是封闭 Brep；设置对象 Name、LayerIndex 和颜色；
把所有创建放在一个 BeginUndoRecord/EndUndoRecord 内；最后 Redraw。禁止文件、网络、进程、Shell、PowerShell。
固定命名：box 案例用 box_1；table 案例用 base/leg/tabletop；repair 案例用 post/top。
圆桌底座 base_z=0、高40；桌腿 base_z=40、高650；桌面 base_z=690、高60。
repair 案例支柱直径120、高500、base_z=0；顶板直径500、厚30、base_z=500。"""


def reference_spec(case_id: str) -> ModelingSpec:
    common = {"intent": "create", "units": "mm", "document_tolerance": 0.01, "assumptions": []}
    if case_id == "box":
        data = {**common, "task_id": "eval-box", "objects": [
            {"name": "box_1", "primitive": "box", "dimensions": {"width": 100, "depth": 60, "height": 30}, "position": {"center_x": 0, "center_y": 0, "base_z": 0}, "layer": "AI_Demo", "color": "blue"}],
            "constraints": [{"type": "center_aligned_xy", "targets": ["box_1"], "tolerance": 0.1}],
            "acceptance": {"expected_object_count": 1, "dimension_tolerance_mm": 0.1, "require_valid_geometry": True}}
    elif case_id == "table":
        objects = [
            {"name": "base", "primitive": "cylinder", "dimensions": {"diameter": 600, "height": 40}, "position": {"center_x": 0, "center_y": 0, "base_z": 0}, "layer": "底座", "color": "gray"},
            {"name": "leg", "primitive": "cylinder", "dimensions": {"diameter": 180, "height": 650}, "position": {"center_x": 0, "center_y": 0, "base_z": 40}, "layer": "桌腿", "color": "gray"},
            {"name": "tabletop", "primitive": "cylinder", "dimensions": {"diameter": 1200, "height": 60}, "position": {"center_x": 0, "center_y": 0, "base_z": 690}, "layer": "桌面", "color": "blue"}]
        data = {**common, "task_id": "eval-table", "objects": objects,
            "constraints": [{"type": "center_aligned_xy", "targets": ["base", "leg", "tabletop"], "tolerance": 0.1}, {"type": "z_contact", "targets": ["base", "leg"], "tolerance": 0.1}, {"type": "z_contact", "targets": ["leg", "tabletop"], "tolerance": 0.1}],
            "acceptance": {"expected_object_count": 3, "dimension_tolerance_mm": 0.1, "require_valid_geometry": True}}
    else:
        data = {**common, "task_id": "eval-repair", "objects": [
            {"name": "post", "primitive": "cylinder", "dimensions": {"diameter": 120, "height": 500}, "position": {"center_x": 0, "center_y": 0, "base_z": 0}, "layer": "支柱", "color": "gray"},
            {"name": "top", "primitive": "cylinder", "dimensions": {"diameter": 500, "height": 30}, "position": {"center_x": 0, "center_y": 0, "base_z": 500}, "layer": "顶板", "color": "blue"}],
            "constraints": [{"type": "center_aligned_xy", "targets": ["post", "top"], "tolerance": 0.1}, {"type": "z_contact", "targets": ["post", "top"], "tolerance": 0.1}],
            "acceptance": {"expected_object_count": 2, "dimension_tolerance_mm": 0.1, "require_valid_geometry": True}}
    return ModelingSpec.model_validate(data)


async def baseline(qwen, mcp, validator, executor, case, slot):
    tool = {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": "Run a Rhino Python script in the active document",
            "parameters": {
                "type": "object",
                "properties": {"script": {"type": "string"}},
                "required": ["script"],
                "additionalProperties": False,
            },
        },
    }
    started = time.perf_counter()
    response = await qwen.client.chat.completions.create(
        model=qwen.settings.qwen_model,
        messages=[{"role": "system", "content": BASELINE_SYSTEM}, {"role": "user", "content": case["prompt"]}],
        tools=[tool],
        tool_choice="auto",
        temperature=0,
    )
    call = (response.choices[0].message.tool_calls or [None])[0]
    if call is None:
        return {"id": case["id"], "passed": False, "reason": "no_tool_call", "seconds": time.perf_counter() - started}
    args = json.loads(call.function.arguments)
    decision = classify_tool("run_python", args)
    if not decision.allowed:
        return {"id": case["id"], "passed": False, "reason": decision.reason, "seconds": time.perf_counter() - started}
    execution = await mcp.call("run_python", {**args, "slot": slot})
    spec = reference_spec(case["id"])
    report = await validator.validate(spec, slot)
    await executor.undo(slot)
    usage = response.usage.model_dump() if response.usage else {}
    return {
        "id": case["id"], "passed": report["passed"], "first_passed": report["passed"],
        "checks": report["summary"], "max_error_mm": max((float(x.get("error") or 0) for x in report["checks"] if x.get("unit") == "mm"), default=None),
        "tool_failures": int(execution["is_error"]), "repairs": 0, "manual_adjustments": 0,
        "seconds": round(time.perf_counter() - started, 3), "tokens": usage.get("total_tokens", 0),
    }


async def experiment(qwen, mcp, validator, executor, case, slot):
    started = time.perf_counter()
    spec, generation = await qwen.make_spec(case["prompt"])
    await qwen.approve_execution(spec)
    execution = await executor.execute(spec, slot, "offset_second" if case["id"] == "repair" else None)
    initial = await validator.validate(spec, slot)
    final, repairs = initial, []
    if not initial["passed"]:
        final, repairs = await RepairLoop(qwen, executor, validator, 2).run(spec, initial, slot)
    await executor.undo(slot)
    return {
        "id": case["id"], "passed": final["passed"], "first_passed": initial["passed"],
        "checks": final["summary"], "max_error_mm": max((float(x.get("error") or 0) for x in final["checks"] if x.get("unit") == "mm"), default=None),
        "tool_failures": int(execution["is_error"]), "repairs": len(repairs), "manual_adjustments": 0,
        "seconds": round(time.perf_counter() - started, 3), "tokens": (generation.get("usage") or {}).get("total_tokens", 0),
    }


def aggregate(rows):
    total = len(rows)
    checks = sum(row["checks"]["checks"] for row in rows)
    passed_checks = sum(row["checks"]["passed"] for row in rows)
    mm_errors = [row["max_error_mm"] for row in rows if row["max_error_mm"] is not None]
    return {
        "cases": total,
        "first_pass_rate": sum(row["first_passed"] for row in rows) / total,
        "final_pass_rate": sum(row["passed"] for row in rows) / total,
        "mean_max_abs_error_mm": sum(mm_errors) / len(mm_errors) if mm_errors else None,
        "constraint_satisfaction_rate": passed_checks / checks if checks else 0,
        "tool_failures": sum(row["tool_failures"] for row in rows),
        "repairs": sum(row["repairs"] for row in rows),
        "manual_adjustments": sum(row["manual_adjustments"] for row in rows),
        "mean_seconds": sum(row["seconds"] for row in rows) / total,
        "tokens": sum(row["tokens"] for row in rows),
    }


async def main():
    settings = load_settings(require_key=True)
    qwen, mcp = QwenClient(settings), RhinoMCPClient(settings)
    await mcp.connect()
    try:
        slot = (await mcp.status())["slots"][0]["slotId"]
        validator, executor = DeterministicValidator(mcp), RhinoExecutor(mcp)
        baseline_rows = [await baseline(qwen, mcp, validator, executor, case, slot) for case in CASES]
        experiment_rows = [await experiment(qwen, mcp, validator, executor, case, slot) for case in CASES]
        result = {
            "scope": "three-case real Qwen + Rhino MCP PoC; not statistically generalizable",
            "model": settings.qwen_model,
            "baseline": {"rows": baseline_rows, "summary": aggregate(baseline_rows)},
            "experiment": {"rows": experiment_rows, "summary": aggregate(experiment_rows)},
        }
        out = Path(__file__).with_name("real_comparison.json")
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
    finally:
        await mcp.close()


if __name__ == "__main__":
    asyncio.run(main())
