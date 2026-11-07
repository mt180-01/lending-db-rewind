"""Each tool's and task's typed input and output (see nanoagent.plugin.v0001.contract): declarations only."""

from dataclasses import dataclass
from enum import Enum
from typing import Annotated

from slimconfig import Output


class Tool(Enum):
    OPEN_INCIDENT = "open_incident"
    READ_LOG = "read_log"
    QUERY_DB = "query_db"
    RESTORE_DATABASE = "restore_database"
    EXPECTED_STATE = "expected_state"


class Task(Enum):
    RESTORE_LENDING_DB = "restore-lending-db"


class Database(Enum):
    BACKUP = "backup.db"
    RESTORED = "restored.db"


class ReplayOrder(Enum):
    SEQ = "seq"
    TIMESTAMP = "timestamp"
    FILE = "file"


SEED = "Which incident to open, 1 to 9999: the same seed always gives the same backup, log and bad statement"
SEQ = "A statement's sequence number: unique, and the order the database applied the statements in"
TS = "When the statement ran, to the second, e.g. 2026-03-14T14:07:03; statements in one second share it"
INTEGRITY = "The result of PRAGMA integrity_check on the finished file: ok, or what it found"
ROW_COUNT = "How many rows the table holds"
TABLE = "The table's name"


@dataclass
class TableCount(Output):
    table: Annotated[str, TABLE]
    row_count: Annotated[int, ROW_COUNT]


@dataclass
class LogEntry(Output):
    seq: Annotated[int, SEQ]
    ts: Annotated[str, TS]
    sql: Annotated[str, "The SQL statement, exactly as the database ran it"]


@dataclass
class Row(Output):
    cells: Annotated[list[str], "The row's values as text, in column order; NULL is written NULL"]


@dataclass
class TableDigest(Output):
    table: Annotated[str, TABLE]
    row_count: Annotated[int, ROW_COUNT]
    digest: Annotated[str, "SHA-256 of the table's name and its sorted row digests: the canonical hash of the table"]
    row_hashes: Annotated[list[str], "The SHA-256 of each row's canonical JSON, sorted"]


@dataclass
class Snapshot(Output):
    name: Annotated[str, "Which wrong recovery this is the state of, for diagnosis"]
    tables: Annotated[list[TableDigest], "That state's tables"]


@dataclass
class IncidentInput(Output):
    seed: Annotated[int, SEED]


@dataclass
class IncidentOutput(Output):
    backup_path: Annotated[str, "The 02:00 nightly backup, relative to the plugin workspace"]
    log_path: Annotated[str, "The append-only JSONL log of every statement since the backup, relative to the workspace"]
    log_entries: Annotated[int, "How many statements the log holds"]
    first_seq: Annotated[int, "The smallest sequence number in the log"]
    last_seq: Annotated[int, "The largest sequence number in the log"]
    tables: Annotated[list[TableCount], "The backup's tables and their row counts"]


@dataclass
class ReadLogInput(Output):
    start: Annotated[int, "The log line to start at, counting from 0: lines come back in the order they were appended"]
    limit: Annotated[int, "How many lines to return, 1 to 100"]


@dataclass
class ReadLogOutput(Output):
    entries: Annotated[list[LogEntry], "The lines from start, in the order the file holds them"]
    more: Annotated[bool, "Whether the log has lines after these"]


@dataclass
class QueryInput(Output):
    database: Annotated[Database, "Which database to read: the backup, or the restored file once it exists"]
    sql: Annotated[str, "One read-only SELECT statement"]


@dataclass
class QueryOutput(Output):
    columns: Annotated[list[str], "The result's column names"]
    rows: Annotated[list[Row], "Up to 200 result rows"]
    truncated: Annotated[bool, "Whether the result had more than 200 rows"]


@dataclass
class RestoreInput(Output):
    skip_seqs: Annotated[list[int], "Sequence numbers of the statements to leave out; each must be in the log"]
    last_seq: Annotated[int, "Replay statements up to and including this sequence number"]
    order: Annotated[
        ReplayOrder,
        "How to order the statements to replay: by sequence number, by timestamp (ties keep file order), or by file order",
    ]


@dataclass
class RestoreOutput(Output):
    restored_path: Annotated[str, "The file written, relative to the plugin workspace: restored.db"]
    applied: Annotated[int, "How many statements were replayed onto a copy of the backup"]
    skipped_seqs: Annotated[list[int], "The sequence numbers left out, as asked"]
    last_seq: Annotated[int, "The last sequence number replayed, as asked"]
    integrity_check: Annotated[str, INTEGRITY]
    tables: Annotated[list[TableCount], "The restored file's tables and their row counts"]


@dataclass
class ExpectedOutput(Output):
    bad_seq: Annotated[int, "The sequence number of the unqualified UPDATE loans SET returned_at = NULL"]
    schema: Annotated[list[str], "Every sqlite_master entry the restored file must have, as canonical JSON, sorted"]
    tables: Annotated[list[TableDigest], "The tables of the state with the bad statement never run, by name"]
    alternatives: Annotated[list[Snapshot], "States a wrong recovery would leave, to name the mistake"]


@dataclass
class RestoredOutput(Output):
    restored_path: Annotated[str, "The restored database, relative to the plugin workspace: restored.db"]
    bad_seq: Annotated[int, "The sequence number of the one bad migration statement that was left out"]
    applied: Annotated[int, "How many statements were replayed onto the backup"]
    integrity_check: Annotated[str, INTEGRITY]


TOOLS = {
    Tool.OPEN_INCIDENT: (IncidentInput, IncidentOutput),
    Tool.READ_LOG: (ReadLogInput, ReadLogOutput),
    Tool.QUERY_DB: (QueryInput, QueryOutput),
    Tool.RESTORE_DATABASE: (RestoreInput, RestoreOutput),
    Tool.EXPECTED_STATE: (IncidentInput, ExpectedOutput),
}
TASKS = {Task.RESTORE_LENDING_DB: (IncidentInput, RestoredOutput)}
