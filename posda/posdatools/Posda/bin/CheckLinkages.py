#!/usr/bin/env python3
"""
A new version of the ApplyMasks script
"""
import argparse
import sys
import csv
from collections import defaultdict
from posda.database import Database
from posda.background.process import BackgroundProcess
from posda.linkage import LinkageChecker, DIVIDER, reference_to_row

TCIA_UID_ROOT = "<!1.3.6.1.4.1.14519.5.2.1>"


class GeneralLinkageChecker(LinkageChecker):

    def detect_uid_anomalies(self, file_rows):
        """Build UID sets and detect cross-category overlaps and duplicate SOPs."""
        sop_uids, series_uids, study_uids, for_uids, sop_to_for, sop_to_series = \
            self.build_uid_context(file_rows)

        sop_counts = defaultdict(list)
        for row in file_rows:
            if row.sop_instance_uid:
                sop_counts[row.sop_instance_uid].append(row.file_id)

        dup_sop            = {k: v for k, v in sop_counts.items() if len(v) > 1}
        sop_series_overlap = sop_uids & series_uids
        sop_study_overlap  = sop_uids & study_uids
        sop_for_overlap    = sop_uids & for_uids
        series_study_overlap = series_uids & study_uids
        series_for_overlap   = series_uids & for_uids
        study_for_overlap    = study_uids & for_uids

        uid_anomalies = []
        for uid_val, fids in dup_sop.items():
            uid_anomalies.append(("duplicate_sop", uid_val, len(fids), ';'.join(map(str, fids))))

        def add_overlap(label, values):
            for u in values:
                uid_anomalies.append((label, u, 1, ''))

        add_overlap("overlap_sop_series",  sop_series_overlap)
        add_overlap("overlap_sop_study",   sop_study_overlap)
        add_overlap("overlap_sop_for",     sop_for_overlap)
        add_overlap("overlap_series_study", series_study_overlap)
        add_overlap("overlap_series_for",  series_for_overlap)
        add_overlap("overlap_study_for",   study_for_overlap)

        print(f"Duplicate SOP UID(s): {len(dup_sop)}")
        print(f"Overlaps - SOP/Series: {len(sop_series_overlap)} - "
              f"SOP/Study: {len(sop_study_overlap)} - "
              f"SOP/FOR: {len(sop_for_overlap)} - "
              f"Series/Study: {len(series_study_overlap)} - "
              f"Series/FOR: {len(series_for_overlap)} - "
              f"Study/For: {len(study_for_overlap)}")
        print(f"Found {len(file_rows)} File(s), {len(sop_uids)} SOP UID(s), "
              f"{len(series_uids)} Series UID(s), {len(study_uids)} Study UID(s), "
              f"{len(for_uids)} Frame of Reference UID(s)")

        return uid_anomalies, sop_uids, series_uids, study_uids, for_uids, sop_to_for, sop_to_series

    def run(self):
        args = self.args
        background = self.background

        print(DIVIDER)
        print("CheckLinkages.py running with the following arguments:")
        print(f"Activity ID: {args.activity_id}")
        print(DIVIDER)

        print(DIVIDER)
        print("UID Analysis")
        print(DIVIDER)
        file_rows = self.get_activity_files()
        uid_anomalies, sop_uids, series_uids, study_uids, for_uids, sop_to_for, sop_to_series = \
            self.detect_uid_anomalies(file_rows)
        _write_uid_report(background.create_report("UID_Report"), uid_anomalies)
        print("  -> UID_Report")

        print(DIVIDER)
        print("Reference Scan")
        print(DIVIDER)
        missing_references, for_mismatches = self.find_missing_references(
            file_rows, sop_uids, series_uids, study_uids, for_uids, sop_to_for, sop_to_series
        )
        missing_references = self.annotate_missing_refs(missing_references)
        missing_references = self.suggest_missing_ref_candidates(missing_references)
        for_mismatches     = self.suggest_relink_candidates(for_mismatches)

        for entry in missing_references:
            if entry.get("missing") is False:
                if str(entry.get("found_activity_id")) == str(args.activity_id):
                    entry["note"] = "In current activity"
                else:
                    entry.setdefault("note", "In external activity")

        missing_rows = [reference_to_row(e) for e in missing_references if e.get("missing")]
        found_rows   = [reference_to_row(e) for e in missing_references if not e.get("missing")]

        print(f"Found {len(missing_rows)} Missing References, {len(found_rows)} Found References")
        for name in self.create_reference_reports(missing_rows, "Missing_References"):
            print(f"  -> {name}")
        for name in self.create_reference_reports(found_rows, "Found_References"):
            print(f"  -> {name}")

        print(DIVIDER)
        print("FOR Mismatches")
        print(DIVIDER)
        print(f"Found {len(for_mismatches)} FOR Mismatches")
        self.create_for_mismatch_report(for_mismatches)
        self.create_for_repair_reports(for_mismatches)

        print(DIVIDER)
        print("Edit Skeleton")
        print(DIVIDER)
        _write_edit_skeleton(background.create_report("Edit_Skeleton"), args.notify, args.activity_id)
        print("  -> Edit_Skeleton")

        print(DIVIDER)
        background.finish("Complete")


def _write_uid_report(report, uid_anomalies):
    writer = csv.writer(report, lineterminator='\n')
    writer.writerow(["type", "uid", "count", "file_ids"])
    for row in uid_anomalies:
        writer.writerow(row)


def _write_edit_skeleton(report, notify, activity_id):
    writer = csv.writer(report, lineterminator='\n')
    writer.writerow(["series_instance_uid", "num_files", "op", "tag", "val1", "val2",
                     "Operation", "edit_description", "notify", "activity_id"])
    writer.writerow([None, None, None, None, None, None,
                     "BackgroundEditTp", "Edits from Linkage Check", notify, activity_id])
    writer.writerow([None, None, "hash_unhashed_uid", None, TCIA_UID_ROOT, "<>",
                     None, None, None, None])


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("background_id", help="the background_subprocess_id")
    parser.add_argument("activity_id",   help="the primary activity to run against")
    parser.add_argument("notify",        help="user to notify when complete")
    return parser.parse_args()


def main(args):
    background = BackgroundProcess(args.background_id, args.notify, args.activity_id)
    background.daemonize()
    conn = Database("posda_files")
    checker = GeneralLinkageChecker(args, background, conn)
    try:
        checker.run()
    except Exception as e:
        print("FATAL ERROR:", e)
        background.finish("Failed")
        raise e
    return 0


if __name__ == "__main__":
    sys.exit(main(parse_args()))
