import asyncio
import json

from app.config import load_settings
from app.qwen_client import QwenClient


PROMPT = "在原点创建一个 100×60×30 mm 的盒子，放到 AI_Demo 图层，设为蓝色。"


async def main():
    settings = load_settings(require_key=True)
    qwen = QwenClient(settings)
    health = await qwen.health()
    spec, generation = await qwen.make_spec(PROMPT)
    call = await qwen.approve_execution(spec)
    result = {
        "health": health,
        "model": generation["model"],
        "spec_valid": spec.task_id != "" and spec.acceptance.expected_object_count == 1,
        "spec": spec.model_dump(mode="json"),
        "function_call": {"name": call["name"], "arguments": call["arguments"]},
    }
    print(json.dumps(result, ensure_ascii=False))
    if not health["ok"] or not result["spec_valid"] or call["name"] != "execute_modeling_spec_via_rhino_mcp":
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
