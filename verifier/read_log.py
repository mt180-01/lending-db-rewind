from .checks import read_log, result
from .sqlite import DatabaseError


def verify_input(value):
    if value.start < 0 or not 1 <= value.limit <= 100:
        return result(False, "start must be 0 or more and limit between 1 and 100")
    return result(True, "input is valid")


def verify_output(input_value, output_value, workspace):
    try:
        entries = read_log(workspace)
    except (DatabaseError, KeyError, ValueError) as error:
        return result(False, f"the log is unreadable: {error}")
    page = entries[input_value.start : input_value.start + input_value.limit]
    given = [(e.seq, e.ts, e.sql) for e in output_value.entries]
    if given != page:
        return result(False, "the entries differ from the log file's lines at that position")
    if output_value.more != (input_value.start + input_value.limit < len(entries)):
        return result(False, "more does not say whether the log continues")
    return result(True, "the log lines are exact", returned=len(given))
