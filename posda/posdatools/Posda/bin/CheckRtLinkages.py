#!/usr/bin/env python3
"""
Check RT object linkages: walks all RT files (RTSTRUCT, RTPLAN, RTDOSE, RTIMAGE)
in the activity, finds missing references and Frame of Reference mismatches,
and generates repair reports and a structural relink worklist for RTSTRUCT files.

Future internal-consistency checks (ROI/contour cross-validation) will be added
to RTLinkageChecker as the Perl CheckStructLinkagesTpId.pl logic is ported.
"""
import sys
import argparse
from collections import defaultdict
from posda.database import Database
from posda.background.process import BackgroundProcess
from posda.linkage import LinkageChecker, DIVIDER, REFERENCE_SEQUENCES_RT

RT_MODALITIES = ['RTSTRUCT', 'RTPLAN', 'RTDOSE', 'RTIMAGE']


class RTLinkageChecker(LinkageChecker):
    reference_sequences = REFERENCE_SEQUENCES_RT

    def run(self):
        background = self.background
        args = self.args

        print(DIVIDER)
        print("CheckRtLinkages.py running with the following arguments:")
        print(f"Activity ID: {args.activity_id}")
        print(DIVIDER)

        # All files supply the UID context (reference targets include images, etc.)
        all_file_rows = self.get_activity_files()
        sop_uids, series_uids, study_uids, for_uids, sop_to_for, sop_to_series, sop_to_file_id = \
            self.build_uid_context(all_file_rows)

        # All RT object types are walked as source files in a single pass.
        rt_file_rows = [r for r in all_file_rows if r.modality in RT_MODALITIES]
        if not rt_file_rows:
            print("No RT objects found in activity.")
            background.finish("Process complete")
            return

        modality_counts = defaultdict(int)
        for f in rt_file_rows:
            modality_counts[f.modality or 'unknown'] += 1
        for modality in RT_MODALITIES:
            if modality in modality_counts:
                print(f"  {modality}: {modality_counts[modality]} file(s)")
        print(f"  Total: {len(rt_file_rows)} RT file(s) "
              f"({len(all_file_rows)} total files in activity)")

        print(DIVIDER)
        print("Reference Scan")
        print(DIVIDER)
        missing_refs, for_mismatches = self.find_missing_references(
            rt_file_rows, sop_uids, series_uids, study_uids,
            for_uids, sop_to_for, sop_to_series, sop_to_file_id,
        )
        missing_refs   = self.annotate_missing_refs(missing_refs)
        missing_refs   = self.suggest_missing_ref_candidates(missing_refs)
        for_mismatches = self.suggest_relink_candidates(for_mismatches)

        self.create_split_reference_reports(missing_refs)

        print(DIVIDER)
        print("FOR Mismatches")
        print(DIVIDER)
        print(f"Found {len(for_mismatches)} FOR Mismatches")
        self.create_for_mismatch_report(for_mismatches)
        self.create_for_repair_reports(for_mismatches)

        # Relink worklist is RTSTRUCT-specific: structural surgery is needed when
        # the entire image series reference is wrong (not just a FOR tag edit).
        # RTPLAN/RTDOSE/RTIMAGE FOR mismatches are handled by the tag-level repair CSVs above.
        print(DIVIDER)
        print("Relink Worklist (RTSTRUCT)")
        print(DIVIDER)
        seen_relinks = set()
        relink_items = []
        for m in for_mismatches:
            if m.get("modality") != "RTSTRUCT":
                continue
            target     = m.get("candidate_series_uid") or m.get("referenced_series_uid")
            confidence = m.get("candidate_confidence", "")
            if not target:
                continue
            key = (m["file_id"], target)
            if key not in seen_relinks:
                seen_relinks.add(key)
                relink_items.append({
                    "file_id":              m["file_id"],
                    "target_series_uid":    target,
                    "candidate_confidence": confidence,
                })

        print(f"Found {len(relink_items)} RTSTRUCT file(s) needing structural relink")
        self.create_relink_report(relink_items)

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
    checker = RTLinkageChecker(args, background, conn)
    try:
        checker.run()
    except Exception as e:
        print("FATAL ERROR:", e)
        background.finish("Failed")
        raise e
    return 0


if __name__ == "__main__":
    sys.exit(main(parse_args()))
