import asyncio
import json

from app.config import load_settings
from app.mcp_rhino_client import RhinoMCPClient
from app.modeling_spec import ModelingSpec
from app.rhino_executor import RhinoExecutor
from app.validator import DeterministicValidator
from tests.test_advanced_features import assembly_spec, loft_spec, sketch_spec, stepped_shaft_spec


async def main():
    mcp = RhinoMCPClient(load_settings(require_key=False))
    await mcp.connect()
    try:
        slot = (await mcp.status())["slots"][0]["slotId"]
        executor, validator = RhinoExecutor(mcp), DeterministicValidator(mcp)
        await executor.undo(slot)
        results = []
        for raw in (stepped_shaft_spec(), sketch_spec("fillet"), sketch_spec("chamfer"), loft_spec(), assembly_spec()):
            spec = ModelingSpec.model_validate(raw)
            execution = await executor.execute(spec, slot)
            report = await validator.validate(spec, slot) if not execution["is_error"] else {"passed": False, "summary": {"checks": 0, "passed": 0, "failed": 1}}
            results.append({"task_id": spec.task_id, "mcp_ok": not execution["is_error"], "execution": execution if execution["is_error"] else None, "report": report})
            await executor.undo(slot)
        print(json.dumps(results, ensure_ascii=False))
        if any(not row["mcp_ok"] or not row["report"]["passed"] for row in results):
            raise SystemExit(1)
    finally:
        await mcp.close()


if __name__ == "__main__":
    asyncio.run(main())
