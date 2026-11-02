from __future__ import annotations

import asyncio
import json
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .config import Settings


class RhinoMCPClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.stack: AsyncExitStack | None = None
        self.session: ClientSession | None = None
        self.tools: list[Any] = []
        self.lock = asyncio.Lock()

    async def connect(self):
        command = Path(self.settings.rhino_mcp_command)
        if not command.exists():
            raise FileNotFoundError(f"Rhino MCP router not found: {command}")
        self.stack = AsyncExitStack()
        params = StdioServerParameters(command=str(command), args=self.settings.rhino_mcp_args)
        reader, writer = await self.stack.enter_async_context(stdio_client(params))
        self.session = await self.stack.enter_async_context(ClientSession(reader, writer))
        init = await self.session.initialize()
        self.tools = (await self.session.list_tools()).tools
        return init

    async def close(self):
        if self.stack:
            await self.stack.aclose()
        self.stack = None
        self.session = None

    async def call(self, name: str, arguments: dict[str, Any], timeout: float = 120) -> dict[str, Any]:
        if not self.session:
            raise RuntimeError("Rhino MCP is not connected")
        async with self.lock:
            result = await asyncio.wait_for(self.session.call_tool(name, arguments), timeout=timeout)
        value = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
        texts = [item.get("text", "") for item in value.get("content", []) if item.get("type") == "text"]
        parsed = []
        for text in texts:
            try:
                parsed.append(json.loads(text))
            except json.JSONDecodeError:
                parsed.append({"text": text})
        payload_error = any(isinstance(item.get("payload"), dict) and item["payload"].get("error") for item in parsed)
        return {"raw": value, "parsed": parsed, "is_error": bool(value.get("isError")) or payload_error}

    async def status(self) -> dict[str, Any]:
        slots = await self.call("list_slots", {})
        payload = slots["parsed"][0].get("payload", []) if slots["parsed"] else []
        return {"connected": True, "tool_count": len(self.tools), "slots": payload}
