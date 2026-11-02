from __future__ import annotations

import os
import shlex
from pathlib import Path

from pydantic import BaseModel, Field, SecretStr, field_validator


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


class Settings(BaseModel):
    qwen_api_key: SecretStr
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen3.8-flash"
    qwen_enable_thinking: bool = False
    rhino_mcp_command: Path
    rhino_mcp_args: list[str] = Field(default_factory=lambda: ["--default-version", "8"])
    agent_max_tool_rounds: int = Field(12, ge=1, le=30)
    agent_max_repair_rounds: int = Field(2, ge=0, le=2)
    host: str = "127.0.0.1"
    port: int = Field(8765, ge=1024, le=65535)
    data_dir: Path = PROJECT_ROOT / "evaluation" / "runs"
    screenshot_dir: Path = PROJECT_ROOT / "screenshots"

    @field_validator("qwen_base_url")
    @classmethod
    def local_or_https(cls, value: str) -> str:
        if not value.startswith("https://") and not value.startswith("http://127.0.0.1"):
            raise ValueError("QWEN_BASE_URL must use HTTPS or loopback HTTP")
        return value.rstrip("/")


def load_settings(require_key: bool = True) -> Settings:
    _load_dotenv(PROJECT_ROOT / ".env")
    key = os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY") or ""
    if require_key and not key:
        raise RuntimeError("QWEN_API_KEY (or DASHSCOPE_API_KEY) is not configured")
    command = os.getenv(
        "RHINO_MCP_COMMAND",
        r"D:\codex\2026-10-28\rhino-rhino-rhnio-rhnio-github-rhnio\work\RhinoMCPPlatform\package-v0.3.0\router\win-x64\rhino-mcp-router.exe",
    )
    args = shlex.split(os.getenv("RHINO_MCP_ARGS", "--default-version 8"), posix=False)
    return Settings(
        qwen_api_key=SecretStr(key),
        qwen_base_url=os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        qwen_model=os.getenv("QWEN_MODEL", "qwen3.8-flash"),
        qwen_enable_thinking=os.getenv("QWEN_ENABLE_THINKING", "false").lower() == "true",
        rhino_mcp_command=Path(command),
        rhino_mcp_args=args,
        agent_max_tool_rounds=int(os.getenv("AGENT_MAX_TOOL_ROUNDS", "12")),
        agent_max_repair_rounds=int(os.getenv("AGENT_MAX_REPAIR_ROUNDS", "2")),
        host=os.getenv("AGENT_HOST", "127.0.0.1"),
        port=int(os.getenv("AGENT_PORT", "8765")),
    )
