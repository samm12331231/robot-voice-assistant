"""Best-effort JSONL event logging for demo troubleshooting."""

import json
from datetime import datetime
from pathlib import Path


def log_turn(**data: object) -> None:
    """Append one event without allowing a logging failure to stop the robot."""
    try:
        now = datetime.now().astimezone()
        path = Path("logs") / f"session_{now.date().isoformat()}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {"timestamp": now.isoformat(), **data}
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass
