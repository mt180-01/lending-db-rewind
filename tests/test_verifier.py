from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import verifier
from contract import (
    Database,
    ExpectedOutput,
    IncidentInput,
    QueryInput,
    ReadLogInput,
    ReplayOrder,
    RestoreInput,
)
from plugin import open_incident, query_db, read_log
from tests.helpers import edit, opened, restored, submission, typed

TASK = "restore-lending-db"


def judge(workspace: Path, reference: ExpectedOutput, output, arguments=None):
    return verifier.verify_task(TASK, arguments or IncidentInput(seed=42), output, reference, str(workspace))


def attempt(workspace: Path, **options):
    """Run restore_database as an agent would, then judge what it submits."""
    _, reference = opened(workspace)
    made = restored(workspace, reference, **options)
    return judge(workspace, reference, submission(made, reference.bad_seq)), reference


def test_the_right_recovery_passes_with_every_check_green(tmp_path: Path) -> None:
    verdict, _ = attempt(tmp_path)
    assert verdict["valid"] is True and verdict["score"] == 1.0
    assert all(check["ok"] for check in verdict["details"]["checks"])
    assert [t["match"] for t in verdict["details"]["tables"]] == [True] * 4
    assert verdict["details"]["matches_wrong_recovery"] == []


def test_every_seed_has_one_passing_and_four_distinct_failing_recoveries(tmp_path: Path) -> None:
    for seed in (1, 7, 2026, 9999):
        workspace = tmp_path / str(seed)
        workspace.mkdir()
        _, reference = opened(workspace, seed)
        arguments = IncidentInput(seed=seed)
        options = {
            "right": {},
            "backup_only": {"skip": [], "last": 0},
            "replay_everything": {"skip": []},
            "timestamp_order": {"order": ReplayOrder.TIMESTAMP},
            "file_order": {"order": ReplayOrder.FILE},
        }
        for name, extra in options.items():
            made = restored(workspace, reference, **extra)
            verdict = judge(workspace, reference, submission(made, reference.bad_seq), arguments)
            assert verdict["valid"] is (name == "right"), (seed, name, verdict["message"])
            assert verdict["details"]["matches_wrong_recovery"] == ([] if name == "right" else [name])


def test_backup_alone_loses_the_afternoons_writes(tmp_path: Path) -> None:
    verdict, _ = attempt(tmp_path, skip=[], last=0)
    assert verdict["valid"] is False and verdict["details"]["matches_wrong_recovery"] == ["backup_only"]
    assert {t["table"] for t in verdict["details"]["tables"] if not t["match"]} == {"members", "books", "loans", "fines"}


def test_replaying_the_whole_log_keeps_the_bad_update(tmp_path: Path) -> None:
    verdict, _ = attempt(tmp_path, skip=[])
    assert verdict["valid"] is False and verdict["details"]["matches_wrong_recovery"] == ["replay_everything"]
    loans = next(t for t in verdict["details"]["tables"] if t["table"] == "loans")
    assert loans["match"] is False and loans["missing_rows"] > 20


def test_timestamp_ordering_breaks_the_shared_second(tmp_path: Path) -> None:
    verdict, _ = attempt(tmp_path, order=ReplayOrder.TIMESTAMP)
    assert verdict["valid"] is False and verdict["details"]["matches_wrong_recovery"] == ["timestamp_order"]
    # Only the loans table is touched by the ties, and exactly two loans differ.
    reports = {t["table"]: t for t in verdict["details"]["tables"]}
    assert [name for name, r in reports.items() if not r["match"]] == ["loans"]
    assert (reports["loans"]["missing_rows"], reports["loans"]["unexpected_rows"]) == (2, 2)


def test_file_ordering_is_wrong_too(tmp_path: Path) -> None:
    verdict, _ = attempt(tmp_path, order=ReplayOrder.FILE)
    assert verdict["valid"] is False and verdict["details"]["matches_wrong_recovery"] == ["file_order"]


def test_skipping_a_legitimate_correction_is_wrong(tmp_path: Path) -> None:
    _, reference = opened(tmp_path)
    decoy = next(
        e.seq
        for e in read_log(ReadLogInput(start=0, limit=100), tmp_path).entries
        if e.sql.startswith("UPDATE loans SET returned_at = NULL WHERE")
    )
    made = restored(tmp_path, reference, skip=[reference.bad_seq, decoy])
    verdict = judge(tmp_path, reference, submission(made, reference.bad_seq))
    assert verdict["valid"] is False and "table loans" in verdict["message"]


def test_stopping_one_statement_early_is_a_boundary_failure(tmp_path: Path) -> None:
    incident, reference = opened(tmp_path)
    made = restored(tmp_path, reference, last=incident.last_seq - 1)
    assert judge(tmp_path, reference, submission(made, reference.bad_seq))["valid"] is False


def test_a_correct_file_with_the_wrong_bad_seq_is_not_accepted(tmp_path: Path) -> None:
    _, reference = opened(tmp_path)
    made = restored(tmp_path, reference)
    verdict = judge(tmp_path, reference, submission(made, reference.bad_seq + 1))
    assert verdict["valid"] is False and "bad_seq" in verdict["message"] and 0 < verdict["score"] < 1


def test_one_changed_cell_is_found_in_its_table_only(tmp_path: Path) -> None:
    _, reference = opened(tmp_path)
    made = restored(tmp_path, reference)
    edit(tmp_path, "UPDATE members SET name = 'Someone Else' WHERE id = 2")
    verdict = judge(tmp_path, reference, submission(made, reference.bad_seq))
    reports = {t["table"]: t for t in verdict["details"]["tables"]}
    assert verdict["valid"] is False and [n for n, r in reports.items() if not r["match"]] == ["members"]
    assert (reports["members"]["missing_rows"], reports["members"]["unexpected_rows"]) == (1, 1)


def test_a_changed_schema_is_reported(tmp_path: Path) -> None:
    _, reference = opened(tmp_path)
    made = restored(tmp_path, reference)
    edit(tmp_path, "DROP INDEX idx_loans_member")
    verdict = judge(tmp_path, reference, submission(made, reference.bad_seq))
    assert verdict["valid"] is False and "schema" in verdict["message"]
    assert all(t["match"] for t in verdict["details"]["tables"])  # the data alone was right


def test_a_missing_file_is_refused(tmp_path: Path) -> None:
    _, reference = opened(tmp_path)
    made = restored(tmp_path, reference)
    (tmp_path / "restored.db").unlink()
    verdict = judge(tmp_path, reference, submission(made, reference.bad_seq))
    assert verdict["valid"] is False and verdict["score"] == 0.0 and "does not exist" in verdict["message"]


@pytest.mark.parametrize("damage", ["empty", "text", "truncated", "bitflip"])
def test_a_malformed_file_is_refused(tmp_path: Path, damage: str) -> None:
    _, reference = opened(tmp_path)
    made = restored(tmp_path, reference)
    path = tmp_path / "restored.db"
    data = path.read_bytes()
    path.write_bytes(
        {
            "empty": b"",
            "text": b"restored database goes here",
            "truncated": data[: len(data) // 2],
            "bitflip": data[:4096] + bytes([data[4096] ^ 0xFF]) + data[4097:],
        }[damage]
    )
    verdict = judge(tmp_path, reference, submission(made, reference.bad_seq))
    assert verdict["valid"] is False


def test_a_failed_integrity_check_or_wrong_path_is_refused(tmp_path: Path) -> None:
    _, reference = opened(tmp_path)
    made = restored(tmp_path, reference)
    claim = submission(made, reference.bad_seq)
    claim.integrity_check = "*** in database main ***"
    assert judge(tmp_path, reference, claim)["valid"] is False
    claim = submission(made, reference.bad_seq)
    claim.restored_path = "../restored.db"
    verdict = judge(tmp_path, reference, claim)
    assert verdict["valid"] is False and "restored.db" in verdict["message"]


def test_the_verdict_is_deterministic(tmp_path: Path) -> None:
    _, reference = opened(tmp_path)
    made = restored(tmp_path, reference, order=ReplayOrder.TIMESTAMP)
    claim = submission(made, reference.bad_seq)
    assert json.dumps(judge(tmp_path, reference, claim), sort_keys=True) == json.dumps(
        judge(tmp_path, reference, claim), sort_keys=True
    )


def test_tool_verifiers_accept_good_calls_and_refuse_bad_ones(tmp_path: Path) -> None:
    given = IncidentInput(seed=42)
    incident = open_incident(given, tmp_path)
    assert verifier.verify_input("open_incident", given)["valid"]
    assert verifier.verify_output("open_incident", given, typed(incident, type(incident)), str(tmp_path))["valid"]
    assert not verifier.verify_input("open_incident", IncidentInput(seed=0))["valid"]
    assert not verifier.verify_input("expected_state", IncidentInput(seed=10000))["valid"]

    page_input = ReadLogInput(start=5, limit=10)
    page = read_log(page_input, tmp_path)
    assert verifier.verify_output("read_log", page_input, page, str(tmp_path))["valid"]
    page.entries[0].sql = "DROP TABLE loans"
    assert not verifier.verify_output("read_log", page_input, page, str(tmp_path))["valid"]
    assert not verifier.verify_input("read_log", ReadLogInput(start=-1, limit=10))["valid"]

    query = QueryInput(database=Database.BACKUP, sql="SELECT id FROM loans")
    result = query_db(query, tmp_path)
    assert verifier.verify_output("query_db", query, result, str(tmp_path))["valid"]
    assert not verifier.verify_input("query_db", QueryInput(database=Database.BACKUP, sql="DELETE FROM loans"))["valid"]
    result.rows[0].cells.append("extra")
    assert not verifier.verify_output("query_db", query, result, str(tmp_path))["valid"]


def test_restore_verifier_checks_the_file_against_the_call(tmp_path: Path) -> None:
    incident, reference = opened(tmp_path)
    call = RestoreInput(skip_seqs=[reference.bad_seq], last_seq=incident.last_seq, order=ReplayOrder.SEQ)
    made = restored(tmp_path, reference)
    assert verifier.verify_input("restore_database", call)["valid"]
    assert verifier.verify_output("restore_database", call, made, str(tmp_path))["valid"]
    made.applied += 1
    assert not verifier.verify_output("restore_database", call, made, str(tmp_path))["valid"]
    assert not verifier.verify_input(
        "restore_database", RestoreInput(skip_seqs=[4, 4], last_seq=9, order=ReplayOrder.SEQ)
    )["valid"]
    connection = sqlite3.connect(tmp_path / "restored.db")
    connection.execute("DELETE FROM loans WHERE id = 1")
    connection.commit()
    connection.close()
    made.applied -= 1
    assert not verifier.verify_output("restore_database", call, made, str(tmp_path))["valid"]


def test_the_reference_verifier_checks_its_own_answer(tmp_path: Path) -> None:
    _, reference = opened(tmp_path)
    assert verifier.verify_output("expected_state", IncidentInput(seed=42), reference, str(tmp_path))["valid"]
    reference.alternatives[0].tables = reference.tables
    assert not verifier.verify_output("expected_state", IncidentInput(seed=42), reference, str(tmp_path))["valid"]


def test_an_extra_table_is_refused(tmp_path: Path) -> None:
    _, reference = opened(tmp_path)
    made = restored(tmp_path, reference)
    edit(tmp_path, "CREATE TABLE audit_log (note TEXT)")
    verdict = judge(tmp_path, reference, submission(made, reference.bad_seq))
    assert verdict["valid"] is False and {"tables", "schema"} <= {c["name"] for c in verdict["details"]["checks"] if not c["ok"]}
