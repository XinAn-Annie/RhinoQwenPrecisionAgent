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
        result = await mcp.call(
            "get_viewport_image",
            {
                "slot": slot,
                "width": 1280,
                "height": 720,
                "view": "perspective",
                "displayMode": "Shaded",
                "boxMin": {"x": -50, "y": -30, "z": 0},
                "boxMax": {"x": 50, "y": 30, "z": 30},
                "zoom": 0.7,
            },
        )
        candidates = result["raw"]["content"]
        image = next((item for item in candidates if item.get("type") == "image"), None)
        if image is None:
            image = next(
                (
                    item
                    for envelope in result["parsed"]
                    for item in envelope.get("content", [])
                    if item.get("type") == "image"
                ),
                None,
            )
        if image is None:
            def summarize(value):
                if isinstance(value, dict):
                    return {key: (f"<string:{len(item)}>" if isinstance(item, str) and len(item) > 200 else summarize(item)) for key, item in value.items()}
                if isinstance(value, list):
                    return [summarize(item) for item in value]
                return value
            print(json.dumps({"content_summary": [{"type": x.get("type"), "keys": list(x)} for x in candidates], "parsed": summarize(result["parsed"])}, ensure_ascii=False))
            raise RuntimeError("Rhino MCP did not return an image content block")
        suffix = ".png" if image.get("mimeType") == "image/png" else ".jpg"
        path = Path("screenshots") / ("rhino-real-viewport" + suffix)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(image["data"]))
        metadata = [item for item in result["parsed"] if "payload" in item]
        print(json.dumps({"path": str(path.resolve()), "bytes": path.stat().st_size, "metadata": metadata}, ensure_ascii=False))
    finally:
        await mcp.close()


if __name__ == "__main__":
    asyncio.run(main())
