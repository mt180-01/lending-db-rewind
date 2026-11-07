# Lending DB Rewind

A `nanoagent.plugin/v0001` plugin that checks whether an agent can do database disaster recovery.

A library's lending database is damaged by one `UPDATE loans SET returned_at = NULL` with no `WHERE`
clause, run at about 14:07. All that is left is the 02:00 nightly `backup.db` and an append-only JSONL log of
every statement since, each with a sequence number and a timestamp to the second. The agent must produce
`restored.db`: the database as it would be if the bad statement had never run, with every legitimate write
after it still applied.

The traps: restoring the backup alone loses the afternoon's writes; replaying the whole log re-runs the bad
statement; a book returned at 14:30 must stay returned; legitimate `UPDATE ... SET returned_at = NULL WHERE ...`
corrections must not be dropped with it; and five statements share the bad statement's second, so they must be
replayed in sequence order, not timestamp or file order.

## Tools

| Tool | Does | Code |
|---|---|---|
| `open_incident` | Builds the incident from a seed: `backup.db` and `statements.jsonl` in the workspace | `src/plugin/open_incident.py` |
| `read_log` | Reads lines of the log, in the order the file holds them | `src/plugin/read_log.py` |
| `query_db` | Runs one read-only `SELECT` on `backup.db` or `restored.db` | `src/plugin/query_db.py` |
| `restore_database` | Copies the backup to `restored.db`, replays the chosen statements in the chosen order, runs `PRAGMA integrity_check` | `src/plugin/restore.py` |
| `expected_state` | The reference: canonical hashes of every table with the bad statement never run (never offered to the agent) | `src/plugin/expected.py` |

### Tasks

| Task | Does | Runner |
|---|---|---|
| `restore-lending-db` | Rebuilds the database without the bad migration, keeping every later legitimate write | `agent`, with `open_incident`, `read_log`, `query_db`, `restore_database`; reference `expected_state` |

The verifier (`verifier/`) is plain Python and calls no model. It reads `restored.db` itself with a pure-Python
SQLite reader (`verifier/sqlite.py`), then checks the reported `PRAGMA integrity_check`, the schema, a canonical
hash of each table, and the named bad statement. It reports every table's differences (rows missing and
unexpected) and names a wrong recovery it recognises: backup only, the full log, timestamp order or file order.

## Layout

```text
.
├── nanoagent.yaml   # manifest (a slimconfig ManifestConfig): id, runtime, permissions, tools, tasks
├── contract.py      # each tool's and task's typed input and output: slimconfig Output classes
├── README.md
├── LICENSE
├── pyproject.toml
├── uv.lock
├── .gitignore
├── .env             # environment variable NAMEs this plugin needs, never values
├── src/plugin/      # the MCP server: __main__.py, its IMPLEMENTATIONS, the scenario and the tools
├── tests/
├── ui/              # how the page draws the outputs: renderers.js and renderers.css
├── product/         # the product page a catalog shows: product.yaml and icon.svg
└── verifier/        # deterministic verifier package
```

## Develop and run

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
```

Publishing checks every plugin rule: push the plugin to a public GitHub
repository and submit it on RUSH Lab.
