#!/usr/bin/env python3
"""
Check the internal consistency of RT Structure Set (RTSTRUCT) files: reads
every RTSTRUCT in the activity's latest timepoint, runs the rules in
posda.rtstruct over each one, and reports the findings.

Findings that are safe to fix by deleting a sequence item are also written to
a BackgroundEditTp spreadsheet. Anything else is report-only.

A file that doesn't come back as the expected RTSTRUCT (wrong SOP Class or
SOP Instance UID, or unreadable) is reported as file_not_checked rather than
being treated as clean.

Each rule enforces a DICOM PS3.3 requirement, cited in posda.rtstruct:
  - Structure Set ROI items with no ROI Number (3006,0022)
  - Duplicate ROI Numbers
  - ROI Frame of Reference missing, or not listed once in (3006,0010)
  - ROI Contour items, RT ROI Observations and RT Related ROIs referencing
    an undeclared ROI
  - Missing or duplicate Observation Numbers
  - CLOSEDPLANAR_XOR mixed with other geometric types in one ROI
"""
import os
import sys
import argparse
from collections import Counter
from posda.database import Database
from posda.background.process import BackgroundProcess
from posda.linkage import LinkageChecker, DIVIDER
from posda import rtstruct

EDIT_DESCRIPTION = "Delete unreferenceable RTSTRUCT items (CheckRtStructRois)"
STATUS_EVERY = 100


class RtStructRoiChecker(LinkageChecker):
    """Reuses LinkageChecker's activity file query and dataset loading."""

    def describe_api_response(self, file_id):
        """Print what the file API returned, to diagnose files that won't read.

        Only applies when files are fetched through the API (POSDA_API_ONLY).
        The bearer token is sent as a header, so the printed URL has no secret.
        """
        if not os.getenv("POSDA_API_ONLY"):
            return
        resp, url, ok = self.call_api(f"/files/{file_id}/data")
        print(f"  First unreadable file -- API response for file_id {file_id}:")
        print(f"    url:          {url}")
        if not ok:
            print("    request failed (see message above)")
            return
        print(f"    status:       {resp.status_code}")
        print(f"    content-type: {resp.headers.get('Content-Type')}")
        print(f"    bytes:        {len(resp.content)}")
        print(f"    starts with:  {resp.content[:120]!r}")

    def run(self):
        background = self.background
        args = self.args

        print(DIVIDER)
        print("CheckRtStructRois.py running with the following arguments:")
        print(f"Activity ID: {args.activity_id}")
        print(DIVIDER)

        file_rows = self.get_activity_files("RTSTRUCT")
        if not file_rows:
            print("No RTSTRUCT files found in activity.")
            background.finish("Process complete")
            return
        files_per_series = Counter(r.series_instance_uid for r in file_rows)
        print(f"  {len(file_rows)} RTSTRUCT file(s) in {len(files_per_series)} series")

        findings = []
        not_checked = []
        roi_items_per_file = Counter()
        for n, row in enumerate(file_rows, 1):
            if n % STATUS_EVERY == 0 or n == len(file_rows):
                background.set_activity_status(f"Checked {n} of {len(file_rows)} RTSTRUCTs")
            try:
                ds = self.load_dataset(row)
                problem = ("no data returned" if ds is None
                           else rtstruct.dataset_problem(ds, row.sop_instance_uid))
            except Exception as e:
                problem = f"could not read ({e})"
            if problem:
                if not not_checked:
                    self.describe_api_response(row.file_id)
                not_checked.append(rtstruct.Finding(
                    row.file_id, row.series_instance_uid, row.sop_instance_uid,
                    rule="file_not_checked", action=rtstruct.REPORT,
                    location="", detail=problem,
                ))
                continue
            ss = rtstruct.structure_set_from_dataset(
                ds, file_id=row.file_id, series_instance_uid=row.series_instance_uid)
            roi_items_per_file[len(ss.roi_items)] += 1
            findings.extend(rtstruct.check(ss))

        print(DIVIDER)
        print("Findings")
        print(DIVIDER)
        checked = len(file_rows) - len(not_checked)
        print(f"  {checked} of {len(file_rows)} file(s) checked; "
              f"Structure Set ROI items per file: {dict(sorted(roi_items_per_file.items()))}")
        if not_checked:
            print(f"  WARNING: {len(not_checked)} file(s) could not be checked "
                  f"(rule file_not_checked in the findings report), e.g.:")
            for f in not_checked[:5]:
                print(f"    file_id {f.file_id}: {f.detail}")
        files_with_findings = {f.file_id for f in findings}
        by_action = Counter(f.action for f in findings)
        print(f"  {len(files_with_findings)} file(s) with findings")
        print(f"  {by_action[rtstruct.DELETE]} item(s) to delete, "
              f"{by_action[rtstruct.REPORT]} report-only finding(s)")

        report = background.create_report("RTSTRUCT_ROI_Findings")
        rtstruct.write_findings(report, not_checked + findings)
        print("  -> RTSTRUCT_ROI_Findings")

        groups, skipped = rtstruct.plan_item_deletes(findings, files_per_series)
        for series_uid, reason in skipped:
            print(f"  No edits for series {series_uid}: {reason}")
        if groups:
            num_series = sum(len(series) for _, series in groups)
            print(f"  {num_series} series in {len(groups)} edit group(s)")
            report = background.create_report("RTSTRUCT_ROI_Edits")
            rtstruct.write_edit_sheet(report, groups, files_per_series,
                                      EDIT_DESCRIPTION, args.notify, args.activity_id)
            print("  -> RTSTRUCT_ROI_Edits")

        if not_checked:
            background.finish(f"Complete; {len(not_checked)} file(s) could not be checked")
        else:
            background.finish("Complete")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("background_id", help="the background_subprocess_id")
    parser.add_argument("activity_id",   help="the activity to run against")
    parser.add_argument("notify",        help="user to notify when complete")
    return parser.parse_args()


def main(args):
    background = BackgroundProcess(args.background_id, args.notify, args.activity_id)
    background.daemonize()
    conn = Database("posda_files")
    checker = RtStructRoiChecker(args, background, conn)
    try:
        checker.run()
    except Exception as e:
        print("FATAL ERROR:", e)
        background.finish("Failed")
        raise e
    return 0


if __name__ == "__main__":
    sys.exit(main(parse_args()))
