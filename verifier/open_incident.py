from .checks import BACKUP, BAD_SQL, LOG, read_file, read_log, result, seed_problem
from .sqlite import DatabaseError


def verify_input(value):
    problem = seed_problem(value.seed)
    return result(False, problem) if problem else result(True, "input is valid")


def verify_output(input_value, output_value, workspace):
    if output_value.backup_path != BACKUP or output_value.log_path != LOG:
        return result(False, f"the incident's files must be {BACKUP} and {LOG}")
    try:
        entries = read_log(workspace)
        database = read_file(workspace, BACKUP)
    except (DatabaseError, KeyError, ValueError) as error:
        return result(False, f"the incident files are unreadable: {error}")
    seqs = [seq for seq, _, _ in entries]
    if len(set(seqs)) != len(seqs) or output_value.log_entries != len(seqs):
        return result(False, "the log must hold log_entries statements with distinct sequence numbers")
    if (output_value.first_seq, output_value.last_seq) != (min(seqs), max(seqs)):
        return result(False, "first_seq and last_seq are not the log's smallest and largest sequence numbers")
    by_seq = sorted(entries)
    if [ts for _, ts, _ in by_seq] != sorted(ts for _, ts, _ in by_seq):
        return result(False, "timestamps must not go backwards in sequence order")
    if sum(1 for _, _, sql in entries if sql == BAD_SQL) != 1:
        return result(False, "the log must hold exactly one unqualified UPDATE loans SET returned_at = NULL")
    counts = {name: len(rows) for name, rows in database["tables"].items()}
    if {t.table: t.row_count for t in output_value.tables} != counts:
        return result(False, "the reported table counts differ from backup.db", on_disk=counts)
    return result(True, "the incident is open", log_entries=len(seqs))
