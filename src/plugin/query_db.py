from __future__ import annotations

import sqlite3
from pathlib import Path

from contract import QueryInput, QueryOutput, Row

MOST_ROWS = 200


def query_db(given: QueryInput, workspace: Path) -> QueryOutput:
    if not given.sql.lstrip().lower().startswith("select"):
        raise ValueError("sql must be one SELECT statement")
    path = workspace / given.database.value
    if not path.is_file():
        raise FileNotFoundError(f"{given.database.value} does not exist yet")
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only = ON")
        cursor = connection.execute(given.sql)
        columns = [column[0] for column in cursor.description]
        fetched = cursor.fetchmany(MOST_ROWS + 1)
    finally:
        connection.close()
    rows = [Row(cells=["NULL" if cell is None else str(cell) for cell in row]) for row in fetched[:MOST_ROWS]]
    return QueryOutput(columns=columns, rows=rows, truncated=len(fetched) > MOST_ROWS)
