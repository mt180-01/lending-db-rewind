from __future__ import annotations

from pathlib import Path

from contract import ReadLogInput, ReadLogOutput
from plugin.database import read_log as load


def read_log(given: ReadLogInput, workspace: Path) -> ReadLogOutput:
    if given.start < 0 or not 1 <= given.limit <= 100:
        raise ValueError("start must be 0 or more and limit between 1 and 100")
    entries = load(workspace)
    page = entries[given.start : given.start + given.limit]
    return ReadLogOutput(entries=page, more=given.start + given.limit < len(entries))
