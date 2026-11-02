import asyncio
import json

from app.config import load_settings
from app.mcp_rhino_client import RhinoMCPClient
from app.modeling_spec import ModelingSpec
from app.rhino_executor import RhinoExecutor
from app.validator import DeterministicValidator


SPEC = ModelingSpec.model_validate({
    "task_id": "real-mcp-box-001", "intent": "create", "units": "mm", "document_tolerance": 0.01,
    "objects": [{
        "name": "RQPA_REAL_MCP_BOX", "primitive": "box",
        "dimensions": {"width": 100, "depth": 60, "height": 30},
        "position": {"center_x": 0, "center_y": 0, "base_z": 0},
        "layer": "AI_Demo", "color": "blue",
        "value_sources": {"width": "user", "depth": "user", "height": "user"},
    }],
    "constraints": [
        {"type": "bbox_dimensions", "targets": ["RQPA_REAL_MCP_BOX"], "tolerance": 0.1},
        {"type": "closed_solid", "targets": ["RQPA_REAL_MCP_BOX"]},
        {"type": "valid_geometry", "targets": ["RQPA_REAL_MCP_BOX"]},
    ],
    "acceptance": {"dimension_tolerance_mm": 0.1, "expected_object_count": 1, "require_valid_geometry": True},
    "assumptions": [],
})


async def main():
    settings = load_settings(require_key=False)
    mcp = RhinoMCPClient(settings)
    await mcp.connect()
    try:
        status = await mcp.status()
        slot = status["slots"][0]["slotId"]
        executor = RhinoExecutor(mcp)
        validator = DeterministicValidator(mcp)
        execution = await executor.execute(SPEC, slot)
        report = await validator.validate(SPEC, slot)
        undo = await executor.undo(slot)
        print(json.dumps({"status": status, "execution": execution, "validation": report, "undo": undo}, ensure_ascii=False))
        if execution["is_error"] or not report["passed"] or undo["is_error"]:
            raise SystemExit(1)
    finally:
        await mcp.close()


if __name__ == "__main__":
    asyncio.run(main())
