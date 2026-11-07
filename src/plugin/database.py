"""SQLite helpers shared by the tools: building the backup, replaying statements, and the canonical digests."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from contract import LogEntry, ReplayOrder, TableCount, TableDigest
from plugin.scenario import SCHEMA, Scenario

BACKUP = "backup.db"
RESTORED = "restored.db"
LOG = "statements.jsonl"
PLACEHOLDERS = {"members": 4, "books": 4, "loans": 6, "fines": 4}


def build_backup(connection: sqlite3.Connection, scenario: Scenario) -> None:
    for statement in SCHEMA:
        connection.execute(statement)
    for table, rows in scenario.rows.items():
        marks = ", ".join("?" * PLACEHOLDERS[table])
        connection.executemany(f"INSERT INTO {table} VALUES ({marks})", rows)
    connection.commit()


def read_log(workspace: Path) -> list[LogEntry]:
    """The log's entries in the order the file holds them."""
    path = workspace / LOG
    if not path.is_file():
        raise FileNotFoundError(f"{LOG} does not exist: call open_incident first")
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        entries.append(LogEntry(seq=record["seq"], ts=record["ts"], sql=record["sql"]))
    return entries


def ordered(entries: list[LogEntry], order: ReplayOrder) -> list[LogEntry]:
    if order is ReplayOrder.SEQ:
        return sorted(entries, key=lambda entry: entry.seq)
    if order is ReplayOrder.TIMESTAMP:
        return sorted(entries, key=lambda entry: entry.ts)  # a stable sort: equal seconds keep the file's order
    return list(entries)


def replay(connection: sqlite3.Connection, entries: list[LogEntry]) -> None:
    for entry in entries:
        connection.execute(entry.sql)
    connection.commit()


def table_names(connection: sqlite3.Connection) -> list[str]:
    query = "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    return [name for (name,) in connection.execute(query)]


def counts(connection: sqlite3.Connection) -> list[TableCount]:
    return [
        TableCount(table=name, row_count=connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0])
        for name in table_names(connection)
    ]


def row_digest(row: tuple) -> str:
    return hashlib.sha256(json.dumps(list(row), separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def digests(connection: sqlite3.Connection) -> list[TableDigest]:
    """Each table's canonical hash: independent of row order, the rowid column included."""
    made = []
    for name in table_names(connection):
        hashes = sorted(row_digest(row) for row in connection.execute(f'SELECT * FROM "{name}"'))
        digest = hashlib.sha256((name + "\n" + "\n".join(hashes)).encode()).hexdigest()
        made.append(TableDigest(table=name, row_count=len(hashes), digest=digest, row_hashes=hashes))
    return made


def schema(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute("SELECT type, name, tbl_name, sql FROM sqlite_master")
    return sorted(json.dumps(list(row), ensure_ascii=False) for row in rows)


def integrity_check(path: Path) -> str:
    connection = sqlite3.connect(path)
    try:
        findings = [finding for (finding,) in connection.execute("PRAGMA integrity_check")]
    finally:
        connection.close()
    return "ok" if findings == ["ok"] else "; ".join(findings)
