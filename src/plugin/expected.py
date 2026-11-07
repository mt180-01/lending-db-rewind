from __future__ import annotations

import sqlite3
from pathlib import Path

from contract import ExpectedOutput, IncidentInput, ReplayOrder, Snapshot
from plugin.database import build_backup, digests, ordered, replay, schema
from plugin.scenario import generate


def state(scenario, entries, order):
    """The tables of the backup after ``entries`` are replayed in ``order``, and the schema."""
    connection = sqlite3.connect(":memory:")
    try:
        build_backup(connection, scenario)
        replay(connection, ordered(entries, order))
        return digests(connection), schema(connection)
    finally:
        connection.close()


def expected_state(given: IncidentInput, workspace: Path) -> ExpectedOutput:
    if not 1 <= given.seed <= 9999:
        raise ValueError("seed must be between 1 and 9999")
    scenario = generate(given.seed)
    entries = list(scenario.entries)
    good = [entry for entry in entries if entry.seq != scenario.bad_seq]
    tables, expected_schema = state(scenario, good, ReplayOrder.SEQ)
    wrong = {
        "backup_only": state(scenario, [], ReplayOrder.SEQ)[0],
        "replay_everything": state(scenario, entries, ReplayOrder.SEQ)[0],
        "timestamp_order": state(scenario, good, ReplayOrder.TIMESTAMP)[0],
        "file_order": state(scenario, good, ReplayOrder.FILE)[0],
    }
    for name, other in wrong.items():
        if [t.digest for t in other] == [t.digest for t in tables]:
            raise ValueError(f"seed {given.seed} does not separate {name} from the right state")
    return ExpectedOutput(
        bad_seq=scenario.bad_seq,
        schema=expected_schema,
        tables=tables,
        alternatives=[Snapshot(name=name, tables=other) for name, other in wrong.items()],
    )
