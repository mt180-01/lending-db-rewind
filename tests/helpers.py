"""Build tool inputs and the verifier's typed values the way NanoAgent's sandbox does."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from slimconfig import build_output, plain_output

from contract import (
    ExpectedOutput,
    IncidentInput,
    IncidentOutput,
    ReplayOrder,
    RestoredOutput,
    RestoreInput,
    RestoreOutput,
)
from plugin import expected_state, open_incident, restore_database

SEED = 42


def typed(value, cls):
    return build_output(plain_output(value), cls)


def opened(workspace: Path, seed: int = SEED) -> tuple[IncidentOutput, ExpectedOutput]:
    given = IncidentInput(seed=seed)
    return open_incident(given, workspace), expected_state(given, workspace)


def restored(workspace: Path, reference: ExpectedOutput, *, skip=None, last=None, order=ReplayOrder.SEQ) -> RestoreOutput:
    skip = [reference.bad_seq] if skip is None else skip
    incident_last = max(int(line.split(",")[0].split(":")[1]) for line in (workspace / "statements.jsonl").read_text().splitlines())
    return restore_database(RestoreInput(skip_seqs=skip, last_seq=incident_last if last is None else last, order=order), workspace)


def submission(tool_output: RestoreOutput, bad_seq: int) -> RestoredOutput:
    return RestoredOutput(
        restored_path=tool_output.restored_path,
        bad_seq=bad_seq,
        applied=tool_output.applied,
        integrity_check=tool_output.integrity_check,
    )


def edit(workspace: Path, sql: str) -> None:
    """Change restored.db behind the tools' backs, the way a bad result would differ."""
    connection = sqlite3.connect(workspace / "restored.db")
    connection.execute(sql)
    connection.commit()
    connection.close()
