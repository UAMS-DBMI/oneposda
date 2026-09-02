#!/usr/bin/env python3
"""
An experimental script to apply Private Dispositions to an activity,
and create a new timepoint.

"""

import os
import argparse
import tempfile
import subprocess
import hashlib
from concurrent.futures import ProcessPoolExecutor, as_completed
import requests

from posda.database import Database
from posda.queries import Query
from posda.util import md5sum
from posda.config import Config
from posda.background.process import BackgroundProcess

# Number of parallel processes
MAX_WORKERS = 10   # choose based on your CPU / desired concurrency
EDIT_SCRIPT = "ApplyPrivateDispositionUnconditionalDate3.pl"
API_URL = Config.get("internal-api-url")

def create_import_event(message: str, expected_count: int) -> int:
    payload = {
        'source': message,
        'origin': 'ApplyPrivateDispositions.py',
        'expected_count': str(expected_count)
    }
    r = requests.put(f"{API_URL}/v1/import/event", params=payload)

    if r.status_code == 200:
        obj = r.json()
        return obj['import_event_id']
    else:
        print(r.content)
        raise RuntimeError("Failed to insert file into posda!")

def insert_file_via_api(import_event_id, filename, from_file_digest, subprocess_invocation_id):
    payload = {
        'import_event_id': import_event_id,
        'digest': md5sum(filename),
        'from_file_digest': from_file_digest,
        'subprocess_invocation_id': subprocess_invocation_id,
    }
    with open(filename, "rb") as infile:
        r = requests.put(f"{API_URL}/v1/import/file", params=payload, data=infile)

    if r.status_code == 200:
        obj = r.json()
        return obj['file_id']
    else:
        print(r.content)
        raise RuntimeError("Failed to insert file into posda!")


def make_filename(val):
    md5 = hashlib.md5()
    md5.update(val.encode())
    digest = md5.hexdigest()

    return digest + ".dcm"

def run_command(item):
    """Run EDIT_SCRIPT for a single item."""
    invoc_id, details = item
    file_id, path, output_path, digest, uid_root, offset = details
    cmd = [EDIT_SCRIPT, str(invoc_id), str(file_id), path, output_path, uid_root, str(offset)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return item, result.returncode, result.stdout, result.stderr

class Editor:
    def __init__(self, tempdir, invoc_id):
        self.files = []
        self.invoc_id = invoc_id
        self.tempdir = tempdir
        self.patients = {}
        print(tempdir)

    def get_patient_mapping(self, patient_id: str):
        if patient_id in self.patients:
            return self.patients[patient_id]

        # load it
        val = list(Query("GetPatientMappingByPatientId").run(patient_id))
        if len(val) > 1:
            raise RuntimeError(f"FATAL: {patient_id} has more than one mapping!")
        if len(val) < 1:
            raise RuntimeError(f"FATAL: {patient_id} has no mapping!")

        self.patients[patient_id] = val[0]
        return self.patients[patient_id]


    def add(self, file_id: int, path: str, digest: str, uid_root: str, offset: str) -> None:
        output_path = os.path.join(self.tempdir, 
                                   make_filename(str(file_id)))
        self.files.append((file_id, path, output_path, digest, uid_root, offset))

    def edit(self) -> None:

        with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(run_command, [self.invoc_id, item]) for item in self.files]

            for future in as_completed(futures):
                item, rc, out, err = future.result()
                # print(f"Finished {item} (rc={rc})")
                # if out:
                #     print("STDOUT:", out)
                # if err:
                #     print("STDERR:", err)


    def count(self) -> int:
        return len(self.files)

class Importer:
    def __init__(self, message: str, expected_count: int):
        self.import_event_id = create_import_event(
            message,
            expected_count)

        self.file_ids = []

    def import_from_editor(self, editor: Editor, invoc_id: int) -> None:
        for _, _, path, from_digest, _, _ in editor.files:
            file_id = insert_file_via_api(self.import_event_id, path, from_digest, invoc_id)
            self.file_ids.append(file_id)

    def create_timepoint(self, activity_id: int) -> int:
        file_list = self.file_ids

        # Create the new timepoint
        Query("CreateActivityTimepoint").execute(
            actiity_id=activity_id,
            who_created='none',
            comment='ApplyPrivateDispositions.py',
            creating_user='none'
        )
        tp_id = Query("GetActivityTimepointId").get_single_value()

        with Database("posda_files").cursor() as cur:
            # build a single giant insert query
            args = b','.join([cur.mogrify("(%s, %s)", [tp_id, f]) for f in file_list])
            query = b"""\
                insert into activity_timepoint_file values
            """ + args

            cur.execute(query)
        return tp_id

def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('background_id', help='a required positional argument for %(prog)s')
    parser.add_argument('activity_id', help='a required positional argument for %(prog)s')
    parser.add_argument('notify', help='a required positional argument for %(prog)s')

    return parser.parse_args()

def get_files_in_activity(activity_id, conn):
    with conn.cursor() as cur:
        cur.execute("""\
            select distinct
                file_id,
                patient_id,
                digest,
                root_path || '/' || rel_path as path
            from
                activity_timepoint_file
                natural join file
                natural join file_patient
                natural join file_location
                natural join file_storage_root
            where
                activity_timepoint_id = (
                    select max(activity_timepoint_id)
                    from activity_timepoint
                    where activity_id = %s)
        """, [activity_id])

        return cur.fetchall()

def main(args):
    background = BackgroundProcess(args.background_id, args.notify, args.activity_id)
    print("All processing in background")
    background.daemonize()
    background.set_activity_status("Starting...")

    ## get list of files in current activity
    with Database("posda_files") as conn:
        files_in_activity = get_files_in_activity(args.activity_id, conn)

    background.set_activity_status("Processing files...")
    with tempfile.TemporaryDirectory() as tempdir:
        editor = Editor(tempdir, args.background_id)

        for i, file in enumerate(files_in_activity):
            mapping = editor.get_patient_mapping(file.patient_id)
            editor.add(file.file_id, file.path, file.digest, mapping.uid_root, mapping.date_shift)

            # if i == 9: # break at 10
            #     break

        background.set_activity_status("Editing files...")
        editor.edit()

        background.set_activity_status("Importing files...")
        importer = Importer("Applying private dispositions", editor.count())
        importer.import_from_editor(editor, args.background_id)

    ## Create a new timepoint from the import_event?
    tp_id = importer.create_timepoint(args.activity_id)

    background.finish(f"Done! New timepoint is {tp_id}")

if __name__ == '__main__':
    main(parse_args())
