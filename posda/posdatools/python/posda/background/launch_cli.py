"""Command line behind ``start-background-process``.

    start-background-process --list [--tag TAG]
    start-background-process OPERATION --describe
    start-background-process OPERATION [--stdin FILE|-] NAME=VALUE... / --NAME VALUE...
    start-background-process OPERATION --csv FILE|- ...

Operation parameters are the ``<name>`` placeholders of the operation's
command line. They can be given as ``-p name=value`` or as ``--name value``
(any flag the tool itself does not define is taken as a parameter). Use the
``-p`` form for a parameter whose name collides with one of the tool's own
flags. ``--describe`` prints what an operation needs; a launch aborts before
touching anything if a parameter is missing or unknown.

Input lines for the script's stdin come either pre-rendered (``--stdin``) or
from a CSV with a header row (``--csv``), whose columns named by the
operation's input fields are rendered through its input line format, the way
a spreadsheet launch in the GUI does.

Runs where the Posda environment is loaded (inside a posda container): it
needs the posda_files database, POSDA_INTERNAL_API_URL for the file imports
and POSDA_REDIS_HOST for the work queue.
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from posda.background.launch import (
    LaunchError,
    LaunchPlan,
    InputError,
    LaunchResult,
    Operation,
    ParameterError,
    check_launchable,
    launch,
    list_operations,
    load_operation,
    read_input_csv,
    read_input_lines,
    resolve_parameters,
)

PROG = "start-background-process"
EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument("operation", nargs="?", help="spreadsheet operation name")
    parser.add_argument(
        "-p",
        "--param",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="an operation parameter (repeatable)",
    )
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument(
        "--stdin",
        metavar="FILE",
        help="pre-rendered input lines for the script's stdin: a file, or -",
    )
    inputs.add_argument(
        "--csv",
        metavar="FILE",
        help="a header CSV to render into input lines: a file, or - for stdin",
    )
    parser.add_argument(
        "--invoking-user",
        default=getpass.getuser(),
        metavar="USER",
        help="recorded as the launching Posda user (default: current login)",
    )
    parser.add_argument(
        "--describe",
        action="store_true",
        help="show the operation's parameters and input format, then exit",
    )
    parser.add_argument(
        "--list", action="store_true", help="list spreadsheet operations and exit"
    )
    parser.add_argument(
        "--tag", metavar="TAG", help="with --list: only operations carrying TAG"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and show what would be queued without queuing it",
    )
    parser.add_argument(
        "--allow-outdated",
        action="store_true",
        help="launch an operation that is marked outdated",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    return parser


def collect_params(pairs: Iterable[str], extras: Sequence[str]) -> dict[str, str]:
    """Merge ``-p name=value`` pairs with leftover ``--name value`` flags."""
    params: dict[str, str] = {}
    for pair in pairs:
        name, sep, value = pair.partition("=")
        if not sep or not name:
            raise ParameterError(f"expected NAME=VALUE, got {pair!r}")
        _set_param(params, name, value)
    for name, value in _pair_extras(extras):
        _set_param(params, name, value)
    return params


def _set_param(params: dict[str, str], name: str, value: str) -> None:
    if name in params:
        raise ParameterError(f"parameter {name} given more than once")
    params[name] = value


def _pair_extras(extras: Sequence[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    index = 0
    while index < len(extras):
        token = extras[index]
        if not token.startswith("--") or len(token) <= 2:
            raise ParameterError(f"unexpected argument {token!r}")
        name, sep, value = token[2:].partition("=")
        if sep:
            index += 1
        elif index + 1 < len(extras) and not extras[index + 1].startswith("--"):
            value = extras[index + 1]
            index += 2
        else:
            raise ParameterError(f"--{name} needs a value (use --{name}=VALUE)")
        pairs.append((name, value))
    return pairs


def describe_operation(operation: Operation) -> dict[str, Any]:
    return {
        "operation_name": operation.operation_name,
        "operation_type": operation.operation_type,
        "outdated": operation.outdated,
        "worker_priority": operation.worker_priority,
        "queue_name": operation.queue_name,
        "tags": operation.tags,
        "command_line": operation.command_line,
        "parameters": operation.args,
        "input_line_format": operation.input_line_format,
        "input_fields": operation.fields,
    }


def format_description(operation: Operation) -> str:
    info = describe_operation(operation)
    if operation.fields:
        input_lines = (
            f"{operation.input_line_format}  (fields: {', '.join(operation.fields)})"
        )
    else:
        input_lines = "none (the script reads nothing from stdin)"
    rows = [
        ("Operation", info["operation_name"]),
        ("Type", info["operation_type"] or "(none)"),
        ("Outdated", "yes" if info["outdated"] else "no"),
        ("Queue", f"{info['queue_name']} (priority {info['worker_priority']})"),
        ("Tags", ", ".join(info["tags"]) or "(none)"),
        ("Command", info["command_line"]),
        ("Parameters", ", ".join(info["parameters"]) or "(none)"),
        ("Input lines", input_lines),
    ]
    return "\n".join(f"{label + ':':<13}{value}" for label, value in rows)


def format_listing(operations: Iterable[Operation]) -> str:
    lines = []
    for op in operations:
        flags = " (outdated)" if op.outdated else ""
        lines.append(f"{op.operation_name:<45} {op.operation_type or '-'}{flags}")
    return "\n".join(lines)


def _read_source(source: str) -> str:
    if source == "-":
        return sys.stdin.read()
    return Path(source).read_text()


def read_stdin_argument(source: str | None) -> list[str]:
    if source is None:
        return []
    return read_input_lines(_read_source(source))


def read_csv_argument(
    operation: Operation, source: str
) -> tuple[list[str], list[list[str]]]:
    return read_input_csv(operation, _read_source(source))


def plan_as_dict(plan: LaunchPlan) -> dict[str, Any]:
    return {
        "operation_name": plan.operation.operation_name,
        "queue_name": plan.operation.queue_name,
        "invoking_user": plan.user,
        "parameters": plan.params,
        "command_line": plan.expanded_command,
        "input_line_count": len(plan.input_lines),
        "input_lines": plan.input_lines,
    }


def format_plan(plan: LaunchPlan) -> str:
    lines = [
        f"Operation:   {plan.operation.operation_name}",
        f"Queue:       {plan.operation.queue_name}",
        f"User:        {plan.user}",
        f"Command:     {plan.expanded_command}",
        f"Input lines: {len(plan.input_lines)}",
    ]
    lines += [f"  {line}" for line in plan.input_lines[:10]]
    if len(plan.input_lines) > 10:
        lines.append(f"  ... {len(plan.input_lines) - 10} more")
    return "\n".join(lines)


def result_as_dict(result: LaunchResult) -> dict[str, Any]:
    return {
        "subprocess_invocation_id": result.subprocess_invocation_id,
        "work_id": result.work_id,
        "queue_name": result.queue_name,
        "spreadsheet_uploaded_id": result.spreadsheet_uploaded_id,
        "spreadsheet_file_id": result.spreadsheet_file_id,
        "input_file_id": result.input_file_id,
        "command_line": result.command_line,
    }


def format_result(result: LaunchResult) -> str:
    return (
        f"queued subprocess_invocation_id={result.subprocess_invocation_id} "
        f"work_id={result.work_id} on {result.queue_name}"
    )


# --- environment-bound pieces; imported lazily so the pure parts stay light ---


def connect() -> Any:
    from posda.database import Database

    return Database("posda_files").connection()


def import_file(path: str, comment: str) -> int:
    from posda.main.file import insert_file

    return int(insert_file(path, comment))


def push_work(queue_name: str, work_id: int) -> None:
    from posda.config import Config
    from posda.worker import workqueue

    redis_db = workqueue.connect(Config.get("redis-host", default="redis"))
    workqueue.push_work_id(redis_db, queue_name, work_id)


def emit(args: argparse.Namespace, text: str, data: Mapping[str, Any]) -> None:
    print(json.dumps(data, indent=2) if args.json else text)


def warn(message: str) -> None:
    print(f"{PROG}: {message}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args, extras = parser.parse_known_args(argv)
    try:
        params = collect_params(args.param, extras)
    except ParameterError as exc:
        parser.error(str(exc))

    if args.list:
        operations = list_operations(connect(), args.tag)
        if args.json:
            print(json.dumps([describe_operation(op) for op in operations], indent=2))
        else:
            print(format_listing(operations))
        return EXIT_OK

    if not args.operation:
        parser.error("an operation name is required (or --list)")

    try:
        return run_operation(args, params)
    except (ParameterError, InputError) as exc:
        warn(str(exc))
        return EXIT_USAGE
    except LaunchError as exc:
        warn(str(exc))
        return EXIT_FAILURE


def run_operation(args: argparse.Namespace, params: Mapping[str, str]) -> int:
    conn = connect()
    operation = load_operation(conn, args.operation)
    if args.describe:
        emit(args, format_description(operation), describe_operation(operation))
        return EXIT_OK

    check_launchable(operation, allow_outdated=args.allow_outdated)
    values = resolve_parameters(operation, params)
    input_cells = None
    if args.csv:
        input_lines, input_cells = read_csv_argument(operation, args.csv)
    else:
        input_lines = read_stdin_argument(args.stdin)
    if operation.fields and not input_lines:
        warn(
            f"{operation.operation_name} expects input lines "
            f"({operation.input_line_format}) but none were given"
        )
    plan = LaunchPlan(
        operation=operation,
        params=values,
        input_lines=input_lines,
        user=args.invoking_user,
        input_cells=input_cells,
    )
    if args.dry_run:
        emit(args, format_plan(plan), plan_as_dict(plan))
        return EXIT_OK

    result = launch(conn, plan, import_file=import_file, push_work=push_work)
    emit(args, format_result(result), result_as_dict(result))
    return EXIT_OK
