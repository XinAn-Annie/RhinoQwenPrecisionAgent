from __future__ import annotations

import asyncio
import base64
import math
import time
from pathlib import Path
from typing import Any

from .mcp_rhino_client import RhinoMCPClient
from .qwen_client import QwenClient
from .repair_loop import RepairLoop
from .rhino_executor import RhinoExecutor
from .run_logger import RunLogger
from .validator import DeterministicValidator


class AgentService:
    def __init__(self, qwen: QwenClient, mcp: RhinoMCPClient, logger: RunLogger, max_repairs: int = 2, screenshot_dir: Path | None = None):
        self.qwen = qwen
        self.mcp = mcp
        self.logger = logger
        self.executor = RhinoExecutor(mcp)
        self.validator = DeterministicValidator(mcp)
        self.repair = RepairLoop(qwen, self.executor, self.validator, max_repairs)
        self.cancel_event = asyncio.Event()
        self.last_slot: str | None = None
        self.screenshot_dir = screenshot_dir

    async def _slot(self) -> str | None:
        status = await self.mcp.status()
        slots = status.get("slots") or []
        self.last_slot = slots[0].get("slotId") if slots else None
        return self.last_slot

    async def answer(self, text: str) -> dict[str, Any]:
        slot = await self._slot()
        context = await self.mcp.call("get_context", {"slot": slot} if slot else {})
        return {"mode": "qa", "answer": await self.qwen.answer(text, context), "context": context}

    async def model(self, text: str, induce_error: bool = False) -> dict[str, Any]:
        started = time.perf_counter()
        self.cancel_event.clear()
        slot = await self._slot()
        before_state = await self.mcp.call("list_objects", {"slot": slot} if slot else {})
        spec, generation = await self.qwen.make_spec(text)
        if self.cancel_event.is_set():
            raise asyncio.CancelledError("stopped before execution")
        plan = await self.qwen.approve_execution(spec)
        if self.cancel_event.is_set():
            raise asyncio.CancelledError("stopped before MCP write")
        execution = await self.executor.execute(spec, slot, "offset_second" if induce_error else None)
        report = await self.validator.validate(spec, slot)
        initial_validation = report
        repairs: list[dict[str, Any]] = []
        if not report["passed"] and not self.cancel_event.is_set():
            report, repairs = await self.repair.run(spec, report, slot)
        after_state = await self.mcp.call("list_objects", {"slot": slot} if slot else {})
        screenshot_path = await self._capture_viewport(spec, slot)
        record = {
            "mode": "model",
            "user_request": text,
            "modeling_spec": spec.model_dump(mode="json"),
            "qwen_generation": generation,
            "qwen_plan": plan,
            "before_state": before_state,
            "execution": execution,
            "initial_validation": initial_validation,
            "validation": report,
            "repairs": repairs,
            "after_state": after_state,
            "screenshot_path": screenshot_path,
            "qwen_model": generation["model"],
            "qwen_temperature": 0,
            "runtime_seconds": round(time.perf_counter() - started, 3),
            "manual_modification": None,
            "accepted": None,
            "slot": slot,
        }
        path = self.logger.save(spec.task_id, record)
        return {**record, "run_log": str(path)}

    async def _capture_viewport(self, spec, slot: str | None) -> str | None:
        if not self.screenshot_dir:
            return None
        bounds = []
        for obj in spec.objects:
            d, p = obj.dimensions, obj.position
            if obj.primitive in ("box", "enclosure"):
                width, depth, height = d["width"], d["depth"], d["height"]
            elif obj.primitive == "cylinder":
                width = depth = d["diameter"]; height = d["height"]
            elif obj.primitive == "sphere":
                width = depth = height = d["diameter"]
            elif obj.primitive == "flange":
                width = depth = d["outer_diameter"]; height = d["thickness"]
            elif obj.primitive == "stepped_shaft":
                width = depth = d["max_diameter"]; height = d["overall_length"]
            elif obj.primitive == "sketch_extrusion":
                bounds.append((p.center_x+min(point.x for point in obj.sketch), p.center_y+min(point.y for point in obj.sketch), p.base_z, p.center_x+max(point.x for point in obj.sketch), p.center_y+max(point.y for point in obj.sketch), p.base_z+d["height"]))
                continue
            else:
                section_bounds = []
                for section in obj.sections:
                    angle = section.rotation_deg * 3.141592653589793 / 180
                    rx = ((section.width/2 * math.cos(angle))**2 + (section.depth/2 * math.sin(angle))**2) ** 0.5
                    ry = ((section.width/2 * math.sin(angle))**2 + (section.depth/2 * math.cos(angle))**2) ** 0.5
                    section_bounds.append((p.center_x+section.center_x-rx, p.center_y+section.center_y-ry, p.base_z+section.z, p.center_x+section.center_x+rx, p.center_y+section.center_y+ry, p.base_z+section.z))
                bounds.extend(section_bounds)
                continue
            bounds.append((p.center_x-width/2, p.center_y-depth/2, p.base_z, p.center_x+width/2, p.center_y+depth/2, p.base_z+height))
        minimum = [min(row[index] for row in bounds) for index in range(3)]
        maximum = [max(row[index+3] for row in bounds) for index in range(3)]
        arguments: dict[str, Any] = {
            "width": 960,
            "height": 540,
            "view": "perspective",
            "displayMode": "Shaded",
            "boxMin": {"x": minimum[0], "y": minimum[1], "z": minimum[2]},
            "boxMax": {"x": maximum[0], "y": maximum[1], "z": maximum[2]},
            "zoom": 0.72,
        }
        if slot:
            arguments["slot"] = slot
        result = await self.mcp.call("get_viewport_image", arguments)
        for envelope in result.get("parsed", []):
            for item in envelope.get("content", []):
                if item.get("type") == "image" and item.get("data"):
                    suffix = ".png" if item.get("mimeType") == "image/png" else ".jpg"
                    path = self.screenshot_dir / f"{spec.task_id}{suffix}"
                    path.write_bytes(base64.b64decode(item["data"]))
                    return str(path)
        return None

    def stop(self):
        self.cancel_event.set()

    async def undo(self) -> dict[str, Any]:
        return await self.executor.undo(self.last_slot)
