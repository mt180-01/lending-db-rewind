from .checks import RESTORED, read_file, read_log, result
from .sqlite import DatabaseError


def verify_input(value):
    if len(set(value.skip_seqs)) != len(value.skip_seqs) or any(seq < 1 for seq in value.skip_seqs):
        return result(False, "skip_seqs must be distinct positive sequence numbers")
    if value.last_seq < 0:
        return result(False, "last_seq must be 0 or more")
    return result(True, "input is valid")


def verify_output(input_value, output_value, workspace):
    if output_value.restored_path != RESTORED:
        return result(False, f"the restored file must be {RESTORED}")
    try:
        entries = read_log(workspace)
        database = read_file(workspace, RESTORED)
    except (DatabaseError, KeyError, ValueError) as error:
        return result(False, f"{RESTORED} or the log is unreadable: {error}")
    if output_value.integrity_check != "ok":
        return result(False, f"PRAGMA integrity_check did not pass: {output_value.integrity_check}")
    if list(output_value.skipped_seqs) != list(input_value.skip_seqs) or output_value.last_seq != input_value.last_seq:
        return result(False, "the output does not repeat the input's skip_seqs and last_seq")
    seqs = {seq for seq, _, _ in entries}
    if not set(input_value.skip_seqs) <= seqs:
        return result(False, "a skipped sequence number is not in the log")
    applied = sum(1 for seq in seqs if seq <= input_value.last_seq and seq not in input_value.skip_seqs)
    if output_value.applied != applied:
        return result(False, f"applied is {output_value.applied}, but {applied} statements qualify")
    counts = {name: len(rows) for name, rows in database["tables"].items()}
    if {t.table: t.row_count for t in output_value.tables} != counts:
        return result(False, "the reported table counts differ from restored.db", on_disk=counts)
    return result(True, "restored.db is written and readable", applied=applied)
