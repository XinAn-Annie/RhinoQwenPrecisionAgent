from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class RunLogger:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, task_id: str, record: dict[str, Any]) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        path = self.root / f"{timestamp}_{task_id}.json"
        safe = dict(record)
        safe["saved_at_utc"] = datetime.now(timezone.utc).isoformat()
        path.write_text(json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8")
        jsonl = self.root / "runs.jsonl"
        with jsonl.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(safe, ensure_ascii=False) + "\n")
        return path
