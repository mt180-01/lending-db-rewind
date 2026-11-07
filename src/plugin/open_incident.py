from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from contract import IncidentInput, IncidentOutput
from plugin.database import BACKUP, LOG, RESTORED, build_backup, counts
from plugin.scenario import generate


def open_incident(given: IncidentInput, workspace: Path) -> IncidentOutput:
    if not 1 <= given.seed <= 9999:
        raise ValueError("seed must be between 1 and 9999")
    scenario = generate(given.seed)
    for name in (BACKUP, LOG, RESTORED):
        (workspace / name).unlink(missing_ok=True)
    connection = sqlite3.connect(workspace / BACKUP)
    try:
        build_backup(connection, scenario)
        tables = counts(connection)
    finally:
        connection.close()
    lines = [json.dumps({"seq": e.seq, "ts": e.ts, "sql": e.sql}, ensure_ascii=False) for e in scenario.entries]
    (workspace / LOG).write_text("\n".join(lines) + "\n", encoding="utf-8")
    seqs = [entry.seq for entry in scenario.entries]
    return IncidentOutput(
        backup_path=BACKUP, log_path=LOG, log_entries=len(seqs), first_seq=min(seqs), last_seq=max(seqs), tables=tables
    )
