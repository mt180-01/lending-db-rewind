from .checks import result

MOST_ROWS = 200


def verify_input(value):
    if not value.sql.lstrip().lower().startswith("select"):
        return result(False, "sql must be one SELECT statement")
    return result(True, "input is valid")


def verify_output(input_value, output_value, workspace):
    rows = output_value.rows
    if len(rows) > MOST_ROWS or any(len(row.cells) != len(output_value.columns) for row in rows):
        return result(False, "rows must be at most 200 and as wide as the columns")
    if output_value.truncated and len(rows) != MOST_ROWS:
        return result(False, "a truncated result must hold exactly 200 rows")
    return result(True, "the query result is well formed", rows=len(rows))
