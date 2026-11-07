"""verify_task for restore-lending-db: restored.db judged against the reference, check by check."""

from collections import Counter

from .checks import RESTORED, read_file, result, table_digest
from .sqlite import DatabaseError


def check(name, ok, message):
    return {"name": name, "ok": ok, "message": message}


def verdict(checks, **details):
    passed = sum(1 for item in checks if item["ok"])
    failed = [item for item in checks if not item["ok"]]
    if not failed:
        return result(True, "restored.db is exactly the database without the bad migration", checks=checks, **details)
    return result(
        False,
        "; ".join(f"{item['name']}: {item['message']}" for item in failed),
        score=passed / len(checks),
        checks=checks,
        **details,
    )


def table_report(expected, rows):
    """How a table differs from the reference: its hashes, and the rows missing and unexpected."""
    digest, hashes = table_digest(expected.table, rows)
    missing = Counter(expected.row_hashes) - Counter(hashes)
    unexpected = Counter(hashes) - Counter(expected.row_hashes)
    return {
        "table": expected.table,
        "match": digest == expected.digest,
        "expected_rows": expected.row_count,
        "actual_rows": len(rows),
        "missing_rows": sum(missing.values()),
        "unexpected_rows": sum(unexpected.values()),
        "expected_digest": expected.digest,
        "actual_digest": digest,
    }


def verify_task(arguments, output, reference, workspace):
    if output.restored_path != RESTORED:
        return result(False, f"the restored database must be {RESTORED}, not {output.restored_path!r}")
    try:
        database = read_file(workspace, RESTORED)
    except DatabaseError as error:
        return result(False, f"{RESTORED} is not a readable database: {error}", score=0.0)
    checks = [check("integrity", output.integrity_check == "ok", f"integrity_check said {output.integrity_check!r}")]
    # The file parsed: its header, page count and every b-tree page are consistent.
    checks.append(check("structure", True, "every page of the file reads back"))
    schema_ok = database["schema"] == sorted(reference.schema)
    checks.append(check("schema", schema_ok, "the schema matches" if schema_ok else "the schema differs from the backup's"))
    tables = database["tables"]
    reports = []
    names_ok = sorted(tables) == [expected.table for expected in reference.tables]
    checks.append(check("tables", names_ok, "the same tables" if names_ok else f"tables are {sorted(tables)}"))
    for expected in reference.tables:
        report = table_report(expected, tables.get(expected.table, []))
        reports.append(report)
        message = "hash matches" if report["match"] else (
            f"{report['missing_rows']} rows missing and {report['unexpected_rows']} unexpected"
        )
        checks.append(check(f"table {expected.table}", report["match"], message))
    checks.append(
        check(
            "bad_seq",
            output.bad_seq == reference.bad_seq,
            "the bad statement is named" if output.bad_seq == reference.bad_seq else f"seq {output.bad_seq} is not the bad one",
        )
    )
    mistakes = [
        snapshot.name
        for snapshot in reference.alternatives
        if all(
            table_report(expected, tables.get(expected.table, []))["actual_digest"] == expected.digest
            for expected in snapshot.tables
        )
    ]
    return verdict(checks, tables=reports, matches_wrong_recovery=mistakes)
