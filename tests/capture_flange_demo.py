import asyncio
import base64
import json
from pathlib import Path

from app.config import load_settings
from app.mcp_rhino_client import RhinoMCPClient
from app.modeling_spec import ModelingSpec
from app.rhino_executor import RhinoExecutor
from app.validator import DeterministicValidator
from tests.test_modeling_spec import flange_spec


async def main():
    mcp = RhinoMCPClient(load_settings(require_key=False))
    await mcp.connect()
    try:
        slot = (await mcp.status())["slots"][0]["slotId"]
        executor = RhinoExecutor(mcp)
        await executor.undo(slot)
        spec = ModelingSpec.model_validate(flange_spec())
        execution = await executor.execute(spec, slot)
        report = await DeterministicValidator(mcp).validate(spec, slot)
        result = await mcp.call("get_viewport_image", {
            "slot": slot, "width": 1280, "height": 720, "view": "perspective", "displayMode": "Shaded",
            "boxMin": {"x": -80, "y": -80, "z": 0}, "boxMax": {"x": 80, "y": 80, "z": 20}, "zoom": 0.72,
        })
        image = next(item for envelope in result["parsed"] for item in envelope.get("content", []) if item.get("type") == "image")
        path = Path("screenshots") / "precision-flange-validated.jpg"
        path.write_bytes(base64.b64decode(image["data"]))
        print(json.dumps({"mcp_ok": not execution["is_error"], "validation": report["summary"], "path": str(path.resolve()), "bytes": path.stat().st_size}, ensure_ascii=False))
        if execution["is_error"] or not report["passed"]:
            raise SystemExit(1)
    finally:
        await mcp.close()


if __name__ == "__main__":
    asyncio.run(main())
