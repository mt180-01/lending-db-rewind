"""The verifier's pure-Python SQLite reader against sqlite3 itself, on files that exercise the format."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from plugin.database import digests, schema
from plugin.scenario import generate
from tests.helpers import opened, restored
from verifier.checks import table_digest
from verifier.sqlite import DatabaseError, read_database


def rows_of(path: Path, table: str) -> list[list]:
    connection = sqlite3.connect(path)
    try:
        return [list(row) for row in connection.execute(f'SELECT * FROM "{table}" ORDER BY rowid')]
    finally:
        connection.close()


def test_reads_every_table_and_the_schema_like_sqlite3(tmp_path: Path) -> None:
    _, reference = opened(tmp_path)
    restored(tmp_path, reference)
    database = read_database((tmp_path / "restored.db").read_bytes())
    connection = sqlite3.connect(tmp_path / "restored.db")
    assert database["schema"] == schema(connection)
    for table, rows in database["tables"].items():
        assert rows == rows_of(tmp_path / "restored.db", table)
    # Both sides hash a table the same way.
    for made in digests(connection):
        digest, hashes = table_digest(made.table, database["tables"][made.table])
        assert (digest, hashes) == (made.digest, made.row_hashes)


def test_reads_large_multilevel_overflow_and_odd_values(tmp_path: Path) -> None:
    path = tmp_path / "odd.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, a TEXT, b INTEGER, c TEXT)")
    values = [0, 1, -1, 127, 128, -129, 32768, 8388608, 2**31, 2**40, -(2**47), 2**63 - 1, -(2**63)]
    rows = [(i, "é" * (i % 7), values[i % len(values)], None if i % 5 == 0 else "x" * (i % 40)) for i in range(1, 4000)]
    rows += [(5000, "long" * 5000, 3, "y" * 9000)]  # text that spills onto overflow pages
    connection.executemany("INSERT INTO t VALUES (?, ?, ?, ?)", rows)
    connection.execute("CREATE TABLE no_alias (a TEXT, b INTEGER)")
    connection.executemany("INSERT INTO no_alias VALUES (?, ?)", [(f"r{i}", i) for i in range(50)])
    connection.commit()
    connection.close()
    database = read_database(path.read_bytes())
    assert database["tables"]["t"] == rows_of(path, "t") and len(database["tables"]["t"]) == 3999 + 1
    assert database["tables"]["no_alias"] == rows_of(path, "no_alias")


def test_a_freed_page_and_a_deleted_row_do_not_confuse_it(tmp_path: Path) -> None:
    _, reference = opened(tmp_path)
    restored(tmp_path, reference)
    connection = sqlite3.connect(tmp_path / "restored.db")
    connection.execute("DELETE FROM fines")
    connection.commit()
    connection.close()
    assert read_database((tmp_path / "restored.db").read_bytes())["tables"]["fines"] == []


def test_refuses_what_it_cannot_read(tmp_path: Path) -> None:
    opened(tmp_path)
    good = (tmp_path / "backup.db").read_bytes()
    for bad in (b"", b"not a database" * 20, good[:5000], good[:-1], b"X" + good[1:]):
        with pytest.raises(DatabaseError):
            read_database(bad)
    flipped = bytearray(good)
    flipped[4096] = 0x99  # the first byte of page 2 is a b-tree page type
    with pytest.raises(DatabaseError):
        read_database(bytes(flipped))


def test_refuses_real_values(tmp_path: Path) -> None:
    path = tmp_path / "real.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, x REAL)")
    connection.execute("INSERT INTO t VALUES (1, 2.5)")
    connection.commit()
    connection.close()
    with pytest.raises(DatabaseError, match="unsupported"):
        read_database(path.read_bytes())


def test_every_seed_builds_a_backup_the_reader_reads(tmp_path: Path) -> None:
    for seed in (1, 17, 300, 4096, 9999):
        workspace = tmp_path / str(seed)
        workspace.mkdir()
        opened(workspace, seed)
        database = read_database((workspace / "backup.db").read_bytes())
        assert {name: len(rows) for name, rows in database["tables"].items()} == {
            name: len(rows) for name, rows in generate(seed).rows.items()
        }
