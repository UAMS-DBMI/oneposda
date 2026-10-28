import csv
from pathlib import Path

import pytest

from posda.background import launch as L

IMPORT_OP = L.Operation(
    operation_name="ImportInPlaceFromPublic",
    command_line=(
        "ImportInPlaceFromPublic.py <?bkgrnd_id?> <activity_id> <notify> "
        '"<collection_name>" "<visibility>" "<site_name>"'
    ),
    operation_type="background_process",
    input_line_format=None,
    tags=["import"],
    worker_priority=0,
)

HELLO_OP = L.Operation(
    operation_name="HelloWorldPython",
    command_line="BackgroundHelloWorldWithInput.py <?bkgrnd_id?> <activity_id> <notify>",
    operation_type="background_process",
    input_line_format="<series_instance_uid>",
    worker_priority=1,
)

PAIR_OP = L.Operation(
    operation_name="Pairs",
    command_line="Pairs.py <?bkgrnd_id?> <notify> <notify>",
    operation_type="background_process",
    input_line_format="<from_sop>|<to_sop>",
)


def test_parse_placeholders_separates_meta_args_and_dedupes():
    args, meta = L.parse_placeholders(PAIR_OP.command_line)
    assert args == ["notify"]
    assert meta == ["bkgrnd_id"]
    assert L.parse_placeholders(None) == ([], [])


def test_operation_properties():
    assert IMPORT_OP.args == [
        "activity_id",
        "notify",
        "collection_name",
        "visibility",
        "site_name",
    ]
    assert IMPORT_OP.fields == []
    assert HELLO_OP.fields == ["series_instance_uid"]
    assert HELLO_OP.queue_name == "work_queue_1"
    assert IMPORT_OP.program == "ImportInPlaceFromPublic.py"
    assert IMPORT_OP.is_background_process


def test_expand_command_replaces_every_occurrence_and_keeps_meta():
    assert (
        L.expand_command(PAIR_OP.command_line, {"notify": "me"})
        == "Pairs.py <?bkgrnd_id?> me me"
    )


def test_resolve_parameters_orders_by_command():
    values = L.resolve_parameters(
        IMPORT_OP,
        {
            "site_name": "S",
            "visibility": "",
            "collection_name": "C",
            "notify": "n",
            "activity_id": "7",
        },
    )
    assert list(values) == IMPORT_OP.args
    assert values["visibility"] == ""


def test_resolve_parameters_reports_missing_and_unknown():
    with pytest.raises(L.ParameterError) as exc:
        L.resolve_parameters(HELLO_OP, {"activity_id": "1", "bogus": "x"})
    message = str(exc.value)
    assert "missing parameters: notify" in message
    assert "unknown parameters: bogus" in message
    assert "takes: activity_id, notify" in message


def test_resolve_parameters_rejects_newlines():
    with pytest.raises(L.ParameterError, match="newline"):
        L.resolve_parameters(HELLO_OP, {"activity_id": "1", "notify": "a\nb"})


def test_check_launchable():
    L.check_launchable(IMPORT_OP)
    legacy = L.Operation("X", "X.pl <a>", "legacy", None)
    with pytest.raises(L.OperationNotLaunchableError, match="legacy"):
        L.check_launchable(legacy)
    old = L.Operation("Y", "Y.pl", "background_process", None, outdated=True)
    with pytest.raises(L.OperationNotLaunchableError, match="outdated"):
        L.check_launchable(old)
    L.check_launchable(old, allow_outdated=True)


def test_read_input_lines_drops_blank_lines():
    assert L.read_input_lines("a\r\n\n  \nb\n") == ["a", "b"]


def test_split_input_line_inverts_the_format():
    assert L.split_input_line(HELLO_OP, "1.2.3") == ["1.2.3"]
    assert L.split_input_line(PAIR_OP, "1.2|3.4") == ["1.2", "3.4"]
    assert L.split_input_line(PAIR_OP, "nopipe") == ["nopipe", ""]
    assert L.split_input_line(IMPORT_OP, "whatever") == []


def test_split_input_line_with_repeated_field():
    op = L.Operation("R", "R.py", "background_process", "<a>,<b>,<a>")
    assert op.fields == ["a", "b"]
    assert L.split_input_line(op, "x,y,x") == ["x", "y"]


def _plan(operation=IMPORT_OP, lines=(), params=None):
    if params is None:
        params = {name: f"v_{name}" for name in operation.args}
    return L.LaunchPlan(
        operation=operation, params=params, input_lines=list(lines), user="tester"
    )


def test_write_launch_csv_matches_gui_layout(tmp_path):
    plan = _plan(
        HELLO_OP, lines=["1.1", "2.2"], params={"activity_id": "7", "notify": "a,b"}
    )
    path = L.write_launch_csv(plan, tmp_path)
    with open(path, newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows == [
        ["series_instance_uid", "Operation", "activity_id", "notify"],
        ["1.1", "HelloWorldPython", "7", "a,b"],
        ["2.2", "", "", ""],
    ]


def test_write_launch_csv_without_input_lines(tmp_path):
    plan = _plan(
        IMPORT_OP,
        params={
            "activity_id": "7",
            "notify": "n",
            "collection_name": "C",
            "visibility": "1",
            "site_name": "S",
        },
    )
    path = L.write_launch_csv(plan, tmp_path)
    with open(path, newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows == [
        [
            "Operation",
            "activity_id",
            "collection_name",
            "notify",
            "site_name",
            "visibility",
        ],
        ["ImportInPlaceFromPublic", "7", "C", "n", "S", "1"],
    ]


def test_write_input_file(tmp_path):
    path = L.write_input_file(_plan(HELLO_OP, lines=["a", "b"]), tmp_path)
    assert path.read_text() == "a\nb\n"


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params):
        self.conn.executed.append((" ".join(sql.split()), list(params)))
        if (
            self.conn.fail_on is not None
            and len(self.conn.executed) == self.conn.fail_on
        ):
            raise RuntimeError("boom")

    def fetchone(self):
        return (self.conn.next_ids.pop(0),)


class FakeConn:
    def __init__(self, fail_on=None):
        self.autocommit = True
        self.executed = []
        self.next_ids = [11, 22, 33]
        self.fail_on = fail_on
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class Recorder:
    def __init__(self, fail_push=False):
        self.imported = []
        self.pushed = []
        self.fail_push = fail_push

    def import_file(self, path, comment):
        self.imported.append((Path(path).read_text(), comment))
        assert Path(path).exists()
        return 100 + len(self.imported)

    def push_work(self, queue, work_id):
        if self.fail_push:
            raise ConnectionError("redis down")
        self.pushed.append((queue, work_id))


def test_launch_records_everything_in_order(tmp_path):
    conn, rec = FakeConn(), Recorder()
    plan = _plan(HELLO_OP, lines=["1.1"], params={"activity_id": "7", "notify": "me"})
    result = L.launch(
        conn,
        plan,
        import_file=rec.import_file,
        push_work=rec.push_work,
        temp_dir=tmp_path,
    )

    assert [c for _, c in rec.imported] == [L.LAUNCH_CSV_COMMENT, L.INPUT_FILE_COMMENT]
    assert rec.imported[1][0] == "1.1\n"
    assert list(tmp_path.iterdir()) == []  # temp files removed after import

    sql_params = [p for _, p in conn.executed]
    assert sql_params[0] == ["tester", 101, 1]
    assert sql_params[1] == [
        L.BUTTON_NAME,
        "BackgroundHelloWorldWithInput.py <?bkgrnd_id?> 7 me",
        11,
        "tester",
        "HelloWorldPython",
    ]
    assert sql_params[2] == [22, 102, "work_queue_1"]
    assert "from_spreadsheet, from_button" in conn.executed[1][0]
    assert "values (false, true, null" in conn.executed[1][0]
    assert conn.commits == 1 and conn.rollbacks == 0
    assert conn.autocommit is True
    assert rec.pushed == [("work_queue_1", 33)]
    assert result == L.LaunchResult(
        subprocess_invocation_id=22,
        work_id=33,
        queue_name="work_queue_1",
        spreadsheet_uploaded_id=11,
        spreadsheet_file_id=101,
        input_file_id=102,
        command_line="BackgroundHelloWorldWithInput.py <?bkgrnd_id?> 7 me",
    )


def test_launch_rolls_back_when_an_insert_fails(tmp_path):
    conn, rec = FakeConn(fail_on=3), Recorder()
    with pytest.raises(RuntimeError, match="boom"):
        L.launch(
            conn,
            _plan(),
            import_file=rec.import_file,
            push_work=rec.push_work,
            temp_dir=tmp_path,
        )
    assert conn.commits == 0 and conn.rollbacks == 1
    assert conn.autocommit is True
    assert rec.pushed == []


def test_launch_reports_a_committed_but_unqueued_work_row(tmp_path):
    conn, rec = FakeConn(), Recorder(fail_push=True)
    with pytest.raises(L.WorkNotQueuedError) as exc:
        L.launch(
            conn,
            _plan(),
            import_file=rec.import_file,
            push_work=rec.push_work,
            temp_dir=tmp_path,
        )
    assert conn.commits == 1
    assert (exc.value.work_id, exc.value.subprocess_invocation_id) == (33, 22)
    assert exc.value.queue == "work_queue_0"


class RowConn:
    def __init__(self, rows):
        self.rows = rows
        self.sql = None
        self.params = None

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params):
        self.sql, self.params = " ".join(sql.split()), params

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


def test_load_operation_builds_the_dataclass():
    row = ("Op", "Op.py <?bkgrnd_id?> <a>", "background_process", "<x>", ["t"], None, 2)
    op = L.load_operation(RowConn([row]), "Op")
    assert op == L.Operation(
        "Op", "Op.py <?bkgrnd_id?> <a>", "background_process", "<x>", ["t"], False, 2
    )


def test_load_operation_unknown():
    with pytest.raises(L.UnknownOperationError, match="'Nope'"):
        L.load_operation(RowConn([]), "Nope")


def test_list_operations_filters_by_tag():
    conn = RowConn([("A", "A.py", "legacy", None, None, True, None)])
    ops = L.list_operations(conn, tag="import")
    assert "any(tags)" in conn.sql and conn.params == ["import"]
    assert ops[0].outdated is True and ops[0].tags == [] and ops[0].worker_priority == 0


def test_render_input_line():
    assert L.render_input_line(PAIR_OP, {"from_sop": "a", "to_sop": "b"}) == "a|b"
    assert L.render_input_line(PAIR_OP, {"from_sop": "a"}) == "a|"


def test_read_input_csv_renders_rows_and_ignores_extra_columns():
    text = "to_sop,extra,from_sop\n2,x,1\n,,\n4,y,3\n"
    lines, cells = L.read_input_csv(PAIR_OP, text)
    assert lines == ["1|2", "3|4"]
    assert cells == [["1", "2"], ["3", "4"]]


def test_read_input_csv_reports_missing_columns():
    with pytest.raises(L.InputError) as exc:
        L.read_input_csv(PAIR_OP, "from_sop,other\n1,2\n")
    assert "missing columns: to_sop" in str(exc.value)
    assert "need: from_sop, to_sop" in str(exc.value)


def test_read_input_csv_refuses_operations_without_input_lines():
    with pytest.raises(L.InputError, match="reads nothing from stdin"):
        L.read_input_csv(IMPORT_OP, "a\n1\n")


def test_read_input_csv_pads_short_rows():
    lines, cells = L.read_input_csv(PAIR_OP, "from_sop,to_sop\n1\n")
    assert lines == ["1|"] and cells == [["1", ""]]


def test_write_launch_csv_uses_csv_cells_when_present(tmp_path):
    plan = L.LaunchPlan(
        operation=PAIR_OP,
        params={"notify": "n"},
        input_lines=["1|2"],
        user="tester",
        input_cells=[["1", "2"]],
    )
    with open(L.write_launch_csv(plan, tmp_path), newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows == [
        ["from_sop", "to_sop", "Operation", "notify"],
        ["1", "2", "Pairs", "n"],
    ]
