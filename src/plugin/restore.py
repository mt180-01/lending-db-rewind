from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from contract import RestoreInput, RestoreOutput
from plugin.database import BACKUP, RESTORED, counts, integrity_check, ordered, read_log, replay


def restore_database(given: RestoreInput, workspace: Path) -> RestoreOutput:
    entries = read_log(workspace)
    seqs = {entry.seq for entry in entries}
    if len(set(given.skip_seqs)) != len(given.skip_seqs) or not set(given.skip_seqs) <= seqs:
        raise ValueError("skip_seqs must be distinct sequence numbers that are in the log")
    if given.last_seq < 0:
        raise ValueError("last_seq must be 0 or more")
    chosen = [e for e in entries if e.seq <= given.last_seq and e.seq not in given.skip_seqs]
    target = workspace / RESTORED
    shutil.copyfile(workspace / BACKUP, target)
    connection = sqlite3.connect(target)
    try:
        replay(connection, ordered(chosen, given.order))
        tables = counts(connection)
    except Exception:
        connection.close()
        target.unlink()
        raise
    connection.close()
    return RestoreOutput(
        restored_path=RESTORED,
        applied=len(chosen),
        skipped_seqs=list(given.skip_seqs),
        last_seq=given.last_seq,
        integrity_check=integrity_check(target),
        tables=tables,
    )
