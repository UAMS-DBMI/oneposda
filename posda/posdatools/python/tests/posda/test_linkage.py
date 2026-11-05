"""Tests for how posda.linkage buckets and orders reference reports."""

import csv
import io
from types import SimpleNamespace

from posda.linkage import LinkageChecker

ACTIVITY = "10"
OTHER_ACTIVITY = 20
CURRENT_TP = 200
EARLIER_TP = 100
OTHER_TP = 300


class Report(io.StringIO):
    def close(self):
        pass


class Background:
    def __init__(self):
        self.reports = {}

    def create_report(self, name):
        self.reports[name] = Report()
        return self.reports[name]

    def rows(self, name):
        return list(csv.DictReader(io.StringIO(self.reports[name].getvalue())))


class Cursor:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, query, params):
        self.conn.calls.append((query, params))

    def fetchall(self):
        return self.conn.results

    def close(self):
        pass


class Conn:
    def __init__(self, results=()):
        self.results = list(results)
        self.calls = []

    def cursor(self):
        return Cursor(self)


def checker(conn=None):
    args = SimpleNamespace(activity_id=ACTIVITY)
    return LinkageChecker(args, Background(), conn or Conn())


def entry(uid, **found):
    base = {
        "file_id": 1, "modality": "SEG", "series_instance_uid": "1.2.1",
        "study_instance_uid": "1.2.2", "file_for_uid": "1.2.3", "patient_id": "P",
        "timepoint_id": CURRENT_TP, "path": "<p>", "key_path": "<k>", "uid": uid,
        "category": "sop", "note": "", "missing": False,
    }
    return {**base, **found}


def in_current_timepoint(uid):
    return entry(uid, found_activity_id=int(ACTIVITY), found_timepoint_id=CURRENT_TP)


def in_earlier_timepoint(uid):
    return entry(uid, found_activity_id=int(ACTIVITY), found_timepoint_id=EARLIER_TP)


def in_other_activity(uid):
    return entry(uid, found_activity_id=OTHER_ACTIVITY, found_timepoint_id=OTHER_TP)


def test_only_the_current_timepoint_counts_as_found():
    c = checker()
    c.create_split_reference_reports([
        in_current_timepoint("found"),
        in_earlier_timepoint("earlier"),
        in_other_activity("other"),
    ])
    assert [r["referenced_uid"] for r in c.background.rows("Found_References_0")] == ["found"]
    external = [r["referenced_uid"] for r in c.background.rows("External_References_0")]
    assert sorted(external) == ["earlier", "other"]


def test_external_lists_earlier_timepoints_before_other_activities():
    c = checker()
    c.create_split_reference_reports([
        in_other_activity("other1"),
        in_earlier_timepoint("earlier1"),
        in_other_activity("other2"),
        in_earlier_timepoint("earlier2"),
    ])
    external = [r["referenced_uid"] for r in c.background.rows("External_References_0")]
    assert external == ["earlier1", "earlier2", "other1", "other2"]


def test_notes_say_where_the_reference_was_found():
    c = checker()
    c.create_split_reference_reports([
        in_current_timepoint("found"),
        in_earlier_timepoint("earlier"),
        in_other_activity("other"),
    ])
    found = c.background.rows("Found_References_0")
    external = c.background.rows("External_References_0")
    assert found[0]["note"] == "In current timepoint"
    assert [r["note"] for r in external] == [
        "In earlier timepoint of current activity",
        "In external activity",
    ]


def test_summary_counts_earlier_timepoints_as_external():
    c = checker()
    c.create_split_reference_reports([
        in_current_timepoint("found"),
        in_earlier_timepoint("earlier"),
        in_other_activity("other"),
    ])
    refs = [r for r in c.background.rows("Reference_Summary") if r["level"] == "References"][0]
    assert refs["External (Not in current Activity / Timepoint)"] == "2"
    assert refs["Found (In current Activity / Timepoint)"] == "1"


def test_missing_references_stay_missing():
    c = checker()
    c.create_split_reference_reports([entry("gone", missing=True)])
    assert [r["referenced_uid"] for r in c.background.rows("Missing_References_0")] == ["gone"]
    assert "External_References_0" not in c.background.reports


def test_global_lookup_prefers_the_current_activity_for_every_category():
    for category in ("sop", "series", "study", "for"):
        conn = Conn()
        checker(conn).lookup_uids_globally(category, {"1.2.3"})
        query, params = conn.calls[0]
        assert query.count("%s") == len(params) == 2
        assert params == (["1.2.3"], ACTIVITY)
        order_by = " ".join(query.split("ORDER BY")[1].split())
        assert "at.activity_id = %s DESC, at.activity_id DESC" in order_by


def test_annotated_reference_in_earlier_timepoint_goes_to_external():
    conn = Conn(results=[("1.2.3", int(ACTIVITY), EARLIER_TP, 55)])
    c = checker(conn)
    refs = c.annotate_missing_refs([entry("1.2.3", missing=True)])
    c.create_split_reference_reports(refs)
    external = c.background.rows("External_References_0")
    assert [r["found_timepoint_id"] for r in external] == [str(EARLIER_TP)]
    assert "Found_References_0" not in c.background.reports
