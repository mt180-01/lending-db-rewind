"""Checks shared by the tool verifiers. Pure functions of their arguments and the files on disk."""

import hashlib
import json
from pathlib import Path

from .sqlite import DatabaseError, read_database

BAD_SQL = "UPDATE loans SET returned_at = NULL"
BACKUP = "backup.db"
RESTORED = "restored.db"
LOG = "statements.jsonl"


def result(valid, message, *, score=None, **details):
    return {
        "valid": valid,
        "score": float(valid) if score is None else score,
        "message": message,
        "details": details,
    }


def seed_problem(seed):
    if not 1 <= seed <= 9999:
        return "seed must be between 1 and 9999"
    return None


def read_log(workspace):
    """The log's lines as (seq, ts, sql), in file order; raises DatabaseError if it is missing or malformed."""
    path = Path(workspace) / LOG
    if not path.is_file():
        raise DatabaseError(f"{LOG} does not exist")
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        entries.append((record["seq"], record["ts"], record["sql"]))
    return entries


def read_file(workspace, name):
    """The parsed database ``name`` in the workspace; raises DatabaseError if it is missing or unreadable."""
    path = Path(workspace) / name
    if not path.is_file():
        raise DatabaseError(f"{name} does not exist")
    return read_database(path.read_bytes())


def row_digest(row):
    return hashlib.sha256(json.dumps(list(row), separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def table_digest(name, rows):
    """(canonical hash, sorted row digests) of a table: independent of row order, the rowid column included."""
    hashes = sorted(row_digest(row) for row in rows)
    return hashlib.sha256((name + "\n" + "\n".join(hashes)).encode()).hexdigest(), hashes
