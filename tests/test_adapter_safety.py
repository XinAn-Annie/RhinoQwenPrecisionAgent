from app.mcp_tool_adapter import legal_name, normalize_schema
from app.safety import classify_tool


def test_tool_name_and_nullable_schema():
    assert legal_name("rhino tool:1") == "rhino_tool_1"
    schema = normalize_schema({"type": ["object", "null"], "properties": {"x": {"type": ["number", "null"]}}})
    assert schema["type"] == "object" and schema["properties"]["x"]["type"] == "number"


def test_script_safety_blocks_shell_and_network():
    assert classify_tool("run_python", {"script": "import subprocess"}).allowed is False
    assert classify_tool("run_python", {"script": "import Rhino"}).allowed is True
    assert classify_tool("save_doc", {"path": "x.3dm"}).allowed is False
