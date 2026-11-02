import asyncio
import json

from app.config import load_settings
from app.mcp_rhino_client import RhinoMCPClient
from app.modeling_spec import ModelingSpec
from app.rhino_executor import RhinoExecutor
from app.validator import DeterministicValidator


NAMES = ["RQPA_BASE", "RQPA_LEG", "RQPA_TOP"]
SPEC = ModelingSpec.model_validate({
    "task_id": "real-table-repair-001", "intent": "create", "units": "mm", "document_tolerance": 0.01,
    "objects": [
        {"name": NAMES[0], "primitive": "cylinder", "dimensions": {"diameter": 600, "height": 40}, "position": {"center_x": 0, "center_y": 0, "base_z": 0}, "layer": "底座", "color": "gray", "value_sources": {"diameter": "user", "height": "user"}},
        {"name": NAMES[1], "primitive": "cylinder", "dimensions": {"diameter": 180, "height": 650}, "position": {"center_x": 0, "center_y": 0, "base_z": 40}, "layer": "桌腿", "color": "gray", "value_sources": {"diameter": "user", "height": "derived"}},
        {"name": NAMES[2], "primitive": "cylinder", "dimensions": {"diameter": 1200, "height": 60}, "position": {"center_x": 0, "center_y": 0, "base_z": 690}, "layer": "桌面", "color": "blue", "value_sources": {"diameter": "user", "height": "user"}},
    ],
    "constraints": [
        {"type": "center_aligned_xy", "targets": NAMES, "tolerance": 0.1},
        {"type": "z_contact", "targets": [NAMES[0], NAMES[1]], "tolerance": 0.1},
        {"type": "z_contact", "targets": [NAMES[1], NAMES[2]], "tolerance": 0.1},
        {"type": "closed_solid", "targets": NAMES},
        {"type": "valid_geometry", "targets": NAMES},
    ],
    "acceptance": {"dimension_tolerance_mm": 0.1, "expected_object_count": 3, "require_valid_geometry": True},
    "assumptions": ["桌腿高度由 750-40-60=650 mm 推导"],
})


async def main():
    mcp = RhinoMCPClient(load_settings(require_key=False)); await mcp.connect()
    try:
        slot = (await mcp.status())["slots"][0]["slotId"]
        executor, validator = RhinoExecutor(mcp), DeterministicValidator(mcp)
        failed_execution = await executor.execute(SPEC, slot, intentional_error="offset_second")
        failed_report = await validator.validate(SPEC, slot)
        await executor.undo(slot)
        repaired_execution = await executor.execute(SPEC, slot)
        repaired_report = await validator.validate(SPEC, slot)
        await executor.undo(slot)
        result = {
            "failed_execution_mcp_ok": not failed_execution["is_error"],
            "failed_validation": failed_report,
            "repaired_execution_mcp_ok": not repaired_execution["is_error"],
            "repaired_validation": repaired_report,
        }
        print(json.dumps(result, ensure_ascii=False))
        if failed_execution["is_error"] or failed_report["passed"] or repaired_execution["is_error"] or not repaired_report["passed"]:
            raise SystemExit(1)
    finally:
        await mcp.close()


if __name__ == "__main__":
    asyncio.run(main())
