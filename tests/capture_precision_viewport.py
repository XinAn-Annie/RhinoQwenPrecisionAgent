import asyncio
import base64
import json
from pathlib import Path

from app.config import load_settings
from app.mcp_rhino_client import RhinoMCPClient


async def main():
    mcp = RhinoMCPClient(load_settings(require_key=False))
    await mcp.connect()
    try:
        slot = (await mcp.status())["slots"][0]["slotId"]
        result = await mcp.call("get_viewport_image", {
            "slot": slot, "width": 1280, "height": 720, "view": "perspective", "displayMode": "Shaded",
            "boxMin": {"x": -90, "y": -60, "z": 0}, "boxMax": {"x": 90, "y": 60, "z": 60}, "zoom": 0.72,
        })
        image = next(item for envelope in result["parsed"] for item in envelope.get("content", []) if item.get("type") == "image")
        path = Path("screenshots") / "product-enclosure-validated.jpg"
        path.write_bytes(base64.b64decode(image["data"]))
        print(json.dumps({"path": str(path.resolve()), "bytes": path.stat().st_size}, ensure_ascii=False))
    finally:
        await mcp.close()


if __name__ == "__main__":
    asyncio.run(main())
