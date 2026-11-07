from .checks import result, seed_problem


def verify_input(value):
    problem = seed_problem(value.seed)
    return result(False, problem) if problem else result(True, "input is valid")


def verify_output(input_value, output_value, workspace):
    if output_value.bad_seq < 1 or not output_value.schema:
        return result(False, "the reference must name the bad statement and hold the schema")
    names = [table.table for table in output_value.tables]
    if names != sorted(names) or not names:
        return result(False, "the reference tables must be listed by name")
    snapshots = [output_value.tables] + [snapshot.tables for snapshot in output_value.alternatives]
    for tables in snapshots:
        for table in tables:
            if len(table.digest) != 64 or table.row_count != len(table.row_hashes):
                return result(False, f"table {table.table} has a malformed digest")
    expected = [table.digest for table in output_value.tables]
    for snapshot in output_value.alternatives:
        if [table.digest for table in snapshot.tables] == expected:
            return result(False, f"the wrong recovery {snapshot.name} is not told apart from the right state")
    return result(True, "the reference separates the right state from every wrong recovery")
