from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RiskDecision:
    level: str
    allowed: bool
    reason: str


READ_TOOLS = {"list_objects", "get_selection", "get_commands", "get_context", "get_viewport_image", "list_slots"}
R1_TOOLS = {"set_layer_material", "zoom_to_layer", "zoom_to_object", "set_camera"}
R2_TOOLS = {"run_command", "run_python", "set_selection"}
R3_TOOLS = {"close_doc", "save_doc", "open_doc", "close_slot"}


def classify_tool(name: str, arguments: dict[str, Any]) -> RiskDecision:
    if name in READ_TOOLS:
        return RiskDecision("R0", True, "read-only query")
    if name in R1_TOOLS:
        return RiskDecision("R1", True, "reversible creation/view operation")
    if name in R2_TOOLS:
        text = str(arguments).lower()
        forbidden = ["subprocess", "powershell", "cmd.exe", "os.system", "socket", "requests", "http://", "https://"]
        hit = next((item for item in forbidden if item in text), None)
        if hit:
            return RiskDecision("R4", False, f"generated script contains forbidden capability: {hit}")
        return RiskDecision("R2", True, "document modification requires visible plan")
    if name in R3_TOOLS:
        return RiskDecision("R3", False, "destructive/file operation requires explicit user confirmation")
    return RiskDecision("R2", False, "unclassified write tool is denied by default")
