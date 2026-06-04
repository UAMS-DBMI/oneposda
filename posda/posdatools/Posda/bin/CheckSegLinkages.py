#!/usr/bin/env python3
"""
Check segmentation linkage: walks all SEG files in the activity, finds missing
references and Frame of Reference mismatches, and generates repair reports.
"""
import sys
import argparse
from posda.database import Database
from posda.background.process import BackgroundProcess
from posda.linkage import LinkageChecker, DIVIDER, reference_to_row, REFERENCE_SEQUENCES_SEG


class SegLinkageChecker(LinkageChecker):
    reference_sequences = REFERENCE_SEQUENCES_SEG

    def run(self):
        background = self.background

        print(DIVIDER)
        print("CheckSegLinkages.py running with the following arguments:")
        print(f"Activity ID: {self.args.activity_id}")
        print(DIVIDER)

        # All files supply the UID context (reference targets).
        all_file_rows = self.get_activity_files()
        sop_uids, series_uids, study_uids, for_uids, sop_to_for, sop_to_series = \
            self.build_uid_context(all_file_rows)

        # Only SEG files are walked as source files.
        seg_file_rows = self.get_activity_files(modality_filter='SEG')
        if not seg_file_rows:
            print("No Segmentation objects found in activity.")
            background.finish("Process complete")
            return

        print(f"Found {len(seg_file_rows)} SEG file(s) "
              f"({len(all_file_rows)} total files in activity).")

        print(DIVIDER)
        print("Reference Scan")
        print(DIVIDER)
        missing_refs, for_mismatches = self.find_missing_references(
            seg_file_rows, sop_uids, series_uids, study_uids,
            for_uids, sop_to_for, sop_to_series,
        )
        missing_refs   = self.annotate_missing_refs(missing_refs)
        missing_refs   = self.suggest_missing_ref_candidates(missing_refs)
        for_mismatches = self.suggest_relink_candidates(for_mismatches)

        for entry in missing_refs:
            if entry.get("missing") is False:
                entry["note"] = (
                    f"Found in activity {entry['found_activity_id']} "
                    f"timepoint {entry['found_timepoint_id']}"
                )
            else:
                entry["note"] = "Not found anywhere in Posda"

        missing_rows = [reference_to_row(e) for e in missing_refs if e.get("missing")]
        found_rows   = [reference_to_row(e) for e in missing_refs if not e.get("missing")]

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
        self.create_for_repair_reports(
            for_mismatches,
            description_a="Repairing SEG Frame of Reference: align SEG to image FOR",
            description_b="Repairing SEG Frame of Reference: align image to SEG FOR",
        )
        print(DIVIDER)
        background.finish("Process complete")
        print(DIVIDER)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('background_id', nargs='?', default='',
                        help='the background_subprocess_id (blank for CL mode)')
    parser.add_argument('activity_id', help='the activity SEG files are in')
    parser.add_argument('notify',      help='user to notify when complete')
    return parser.parse_args()


def main(args):
    background = BackgroundProcess(args.background_id, args.notify, args.activity_id)
    background.daemonize()
    conn = Database("posda_files")
    checker = SegLinkageChecker(args, background, conn)
    try:
        checker.run()
    except Exception as e:
        print("FATAL ERROR:", e)
        background.finish("Failed")
        raise e


if __name__ == '__main__':
    main(parse_args())
