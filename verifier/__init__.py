"""The deterministic verifier: each tool's checks live in its own module, on contract instances."""

from contract import Task, Tool

from . import expected, open_incident, query_db, read_log, restore, restore_task

TOOLS = {
    Tool.OPEN_INCIDENT: open_incident,
    Tool.READ_LOG: read_log,
    Tool.QUERY_DB: query_db,
    Tool.RESTORE_DATABASE: restore,
    Tool.EXPECTED_STATE: expected,
}

# task -> its output's check, verify_task(arguments, output, reference, workspace)
TASKS = {Task.RESTORE_LENDING_DB: restore_task.verify_task}


def verify_input(tool, value):
    return TOOLS[Tool(tool)].verify_input(value)


def verify_output(tool, input_value, output_value, workspace):
    return TOOLS[Tool(tool)].verify_output(input_value, output_value, workspace)


def verify_task(task, arguments, output, reference, workspace):
    return TASKS[Task(task)](arguments, output, reference, workspace)
