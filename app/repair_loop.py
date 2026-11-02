from __future__ import annotations

from typing import Any

from .modeling_spec import ModelingSpec
from .qwen_client import QwenClient
from .rhino_executor import RhinoExecutor
from .validator import DeterministicValidator


class RepairLoop:
    def __init__(self, qwen: QwenClient, executor: RhinoExecutor, validator: DeterministicValidator, max_rounds: int = 2):
        self.qwen = qwen
        self.executor = executor
        self.validator = validator
        self.max_rounds = max_rounds

    async def run(self, spec: ModelingSpec, initial_report: dict[str, Any], slot: str | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        report = initial_report
        records = []
        for round_index in range(1, self.max_rounds + 1):
            if report.get("passed"):
                break
            decision = await self.qwen.approve_execution(spec, validation=report)
            undo = await self.executor.undo(slot)
            execution = await self.executor.execute(spec, slot)
            report = await self.validator.validate(spec, slot)
            records.append({"round": round_index, "qwen_decision": decision, "undo": undo, "execution": execution, "validation": report})
        return report, records
