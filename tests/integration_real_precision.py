import asyncio
import json

from app.config import load_settings
from app.mcp_rhino_client import RhinoMCPClient
from app.modeling_spec import ModelingSpec
from app.rhino_executor import RhinoExecutor
from app.validator import DeterministicValidator
from tests.test_modeling_spec import enclosure_spec, flange_spec


async def run_case(spec, executor, validator, slot):
    execution = await executor.execute(spec, slot)
    report = await validator.validate(spec, slot)
    await executor.undo(slot)
    return {"task_id": spec.task_id, "mcp_ok": not execution["is_error"], "report": report}


async def main():
    mcp = RhinoMCPClient(load_settings(require_key=False))
    await mcp.connect()
    try:
        slot = (await mcp.status())["slots"][0]["slotId"]
        executor, validator = RhinoExecutor(mcp), DeterministicValidator(mcp)
        results = [
            await run_case(ModelingSpec.model_validate(flange_spec()), executor, validator, slot),
            await run_case(ModelingSpec.model_validate(enclosure_spec()), executor, validator, slot),
        ]
        print(json.dumps(results, ensure_ascii=False))
        if any(not row["mcp_ok"] or not row["report"]["passed"] for row in results):
            raise SystemExit(1)
    finally:
        await mcp.close()


if __name__ == "__main__":
    asyncio.run(main())
