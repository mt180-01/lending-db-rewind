from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from contract import Database, IncidentInput, QueryInput, ReadLogInput, ReplayOrder, RestoreInput
from plugin import open_incident, query_db, read_log, restore_database
from plugin.scenario import BAD_SQL
from tests.helpers import SEED, opened, restored


def test_open_incident_writes_a_backup_and_a_log(tmp_path: Path) -> None:
    incident, reference = opened(tmp_path)
    assert (tmp_path / "backup.db").is_file() and (tmp_path / "statements.jsonl").is_file()
    assert incident.log_entries == len((tmp_path / "statements.jsonl").read_text().splitlines())
    assert {t.table: t.row_count for t in incident.tables} == {"books": 20, "fines": 5, "loans": 40, "members": 12}
    lines = [json.loads(line) for line in (tmp_path / "statements.jsonl").read_text().splitlines()]
    assert [line["seq"] for line in lines if line["sql"] == BAD_SQL] == [reference.bad_seq]


def test_the_same_seed_gives_the_same_incident(tmp_path: Path) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir(), second.mkdir()
    opened(first), opened(second)
    assert (first / "statements.jsonl").read_bytes() == (second / "statements.jsonl").read_bytes()
    other = tmp_path / "c"
    other.mkdir()
    opened(other, seed=7)
    assert (other / "statements.jsonl").read_bytes() != (first / "statements.jsonl").read_bytes()


def test_the_shared_second_is_appended_out_of_order(tmp_path: Path) -> None:
    _, reference = opened(tmp_path)
    entries = read_log(ReadLogInput(start=0, limit=100), tmp_path).entries
    shared = [e for e in entries if e.ts == next(x.ts for x in entries if x.seq == reference.bad_seq)]
    assert len(shared) == 5
    assert [e.seq for e in shared] != sorted(e.seq for e in shared)  # file order is not sequence order


def test_open_incident_refuses_a_bad_seed(tmp_path: Path) -> None:
    for seed in (0, 10000, -3):
        with pytest.raises(ValueError, match="seed"):
            open_incident(IncidentInput(seed=seed), tmp_path)


def test_read_log_pages_cover_the_log_once(tmp_path: Path) -> None:
    incident, _ = opened(tmp_path)
    seen, start = [], 0
    while True:
        page = read_log(ReadLogInput(start=start, limit=10), tmp_path)
        seen += [entry.seq for entry in page.entries]
        start += 10
        if not page.more:
            break
    assert sorted(seen) == list(range(incident.first_seq, incident.last_seq + 1))


def test_read_log_refuses_bad_paging_and_a_missing_log(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="open_incident"):
        read_log(ReadLogInput(start=0, limit=10), tmp_path)
    opened(tmp_path)
    for start, limit in ((-1, 10), (0, 0), (0, 101)):
        with pytest.raises(ValueError):
            read_log(ReadLogInput(start=start, limit=limit), tmp_path)


def test_query_db_reads_and_refuses_writes(tmp_path: Path) -> None:
    opened(tmp_path)
    result = query_db(QueryInput(database=Database.BACKUP, sql="SELECT id, returned_at FROM loans ORDER BY id"), tmp_path)
    assert result.columns == ["id", "returned_at"] and len(result.rows) == 40 and not result.truncated
    assert any(row.cells[1] == "NULL" for row in result.rows)
    for sql in ("DELETE FROM loans", "UPDATE loans SET returned_at = NULL", "  drop table loans"):
        with pytest.raises(ValueError, match="SELECT"):
            query_db(QueryInput(database=Database.BACKUP, sql=sql), tmp_path)
    with pytest.raises(sqlite3.Error):
        query_db(QueryInput(database=Database.BACKUP, sql="SELECT 1; DROP TABLE loans"), tmp_path)
    with pytest.raises(FileNotFoundError):
        query_db(QueryInput(database=Database.RESTORED, sql="SELECT 1"), tmp_path)
    assert sqlite3.connect(tmp_path / "backup.db").execute("SELECT COUNT(*) FROM loans").fetchone() == (40,)


def test_query_db_truncates_at_200_rows(tmp_path: Path) -> None:
    opened(tmp_path)
    sql = "SELECT a.id FROM loans a, loans b"
    result = query_db(QueryInput(database=Database.BACKUP, sql=sql), tmp_path)
    assert len(result.rows) == 200 and result.truncated


def test_restore_replays_everything_but_the_bad_statement(tmp_path: Path) -> None:
    incident, reference = opened(tmp_path)
    output = restored(tmp_path, reference)
    assert output.applied == incident.log_entries - 1 and output.integrity_check == "ok"
    connection = sqlite3.connect(tmp_path / "restored.db")
    # The 14:30 return stays returned, and the backup's old returns survived the bad update.
    assert connection.execute("SELECT COUNT(*) FROM loans WHERE returned_at = '2026-03-14T14:30:00'").fetchone() == (1,)
    assert connection.execute("SELECT COUNT(*) FROM loans WHERE returned_at IS NOT NULL").fetchone()[0] > 25


def test_restore_refuses_unknown_or_repeated_skips_and_keeps_no_partial_file(tmp_path: Path) -> None:
    incident, _ = opened(tmp_path)
    for skip in ([incident.last_seq + 1], [3, 3]):
        with pytest.raises(ValueError, match="skip_seqs"):
            restore_database(RestoreInput(skip_seqs=skip, last_seq=incident.last_seq, order=ReplayOrder.SEQ), tmp_path)
    assert not (tmp_path / "restored.db").exists()


def test_restore_fails_loudly_when_a_statement_cannot_run(tmp_path: Path) -> None:
    opened(tmp_path)
    log = (tmp_path / "statements.jsonl").read_text().splitlines()
    record = json.loads(log[0])
    record["sql"] = "UPDATE no_such_table SET x = 1"
    (tmp_path / "statements.jsonl").write_text("\n".join([json.dumps(record), *log[1:]]) + "\n")
    with pytest.raises(sqlite3.Error):
        restore_database(RestoreInput(skip_seqs=[], last_seq=999, order=ReplayOrder.SEQ), tmp_path)
    assert not (tmp_path / "restored.db").exists()


def test_reopening_clears_the_old_restored_file(tmp_path: Path) -> None:
    _, reference = opened(tmp_path)
    restored(tmp_path, reference)
    opened(tmp_path, seed=SEED + 1)
    assert not (tmp_path / "restored.db").exists()
