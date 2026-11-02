from __future__ import annotations

import re
from typing import Any


def legal_name(name: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_-]", "_", name)[:64]
    if not value or not re.match(r"^[A-Za-z_]", value):
        value = "tool_" + value
    return value


def normalize_schema(schema: dict[str, Any]) -> dict[str, Any]:
    result = dict(schema or {"type": "object", "properties": {}})
    if isinstance(result.get("type"), list):
        choices = [item for item in result["type"] if item != "null"]
        result["type"] = choices[0] if choices else "string"
    if result.get("type") == "object":
        result.setdefault("properties", {})
        result.setdefault("additionalProperties", True)
    for key, value in list(result.get("properties", {}).items()):
        result["properties"][key] = normalize_schema(value) if isinstance(value, dict) else value
    if isinstance(result.get("items"), dict):
        result["items"] = normalize_schema(result["items"])
    return result


def mcp_tools_to_qwen(tools: list[Any]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    adapted = []
    mapping = {}
    for tool in tools:
        source = tool.model_dump(mode="json") if hasattr(tool, "model_dump") else tool
        original = source["name"]
        public = legal_name(original)
        mapping[public] = original
        adapted.append({
            "type": "function",
            "function": {
                "name": public,
                "description": (source.get("description") or source.get("title") or original)[:1500],
                "parameters": normalize_schema(source.get("inputSchema") or {}),
            },
        })
    return adapted, mapping
