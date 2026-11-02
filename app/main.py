from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agent_loop import AgentService
from .config import PROJECT_ROOT, load_settings
from .mcp_rhino_client import RhinoMCPClient
from .mcp_tool_adapter import mcp_tools_to_qwen
from .qwen_client import QwenClient
from .run_logger import RunLogger


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10000)
    mode: Literal["qa", "model"] = "model"
    induce_error: bool = False


state: dict[str, Any] = {"settings": None, "mcp": None, "qwen": None, "agent": None, "qwen_status": {"ok": False}, "mcp_status": {"connected": False}}


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings(require_key=True)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.screenshot_dir.mkdir(parents=True, exist_ok=True)
    mcp = RhinoMCPClient(settings)
    qwen = QwenClient(settings)
    state.update(settings=settings, mcp=mcp, qwen=qwen)
    try:
        await mcp.connect()
        state["mcp_status"] = await mcp.status()
        state["qwen_status"] = await qwen.health()
        adapted, mapping = mcp_tools_to_qwen(mcp.tools)
        state["tool_adapter"] = {"count": len(adapted), "mapping": mapping}
        state["agent"] = AgentService(
            qwen,
            mcp,
            RunLogger(settings.data_dir),
            settings.agent_max_repair_rounds,
            settings.screenshot_dir,
        )
        yield
    finally:
        await mcp.close()


app = FastAPI(title="Rhino Qwen Precision Agent", lifespan=lifespan)
STATIC = PROJECT_ROOT / "app" / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/status")
async def status():
    return {
        "qwen": state["qwen_status"],
        "mcp": state["mcp_status"],
        "tool_adapter": state.get("tool_adapter", {"count": 0}),
        "rhino": {"connected": bool(state.get("mcp_status", {}).get("slots"))},
    }


@app.post("/api/chat")
async def chat(request: ChatRequest):
    agent: AgentService | None = state.get("agent")
    if not agent:
        raise HTTPException(503, "Agent is not ready")
    try:
        if request.mode == "qa":
            return await agent.answer(request.message)
        return await agent.model(request.message, request.induce_error)
    except asyncio.CancelledError:
        raise HTTPException(409, "Task stopped")
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/stop")
async def stop():
    agent: AgentService | None = state.get("agent")
    if agent:
        agent.stop()
    return {"stopped": True}


@app.post("/api/undo")
async def undo():
    agent: AgentService | None = state.get("agent")
    if not agent:
        raise HTTPException(503, "Agent is not ready")
    return await agent.undo()


def run():
    import uvicorn

    settings = load_settings(require_key=True)
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    run()
