#!/usr/bin/python3 -u
ABOUT = """\
A program to create a new timepoint in the current activity
from the DICOM files belonging to an import event.

Pass 1 (or any value other than 0) as include_all_files to
include every file in the import event, not just DICOM files.

Expects nothing on STDIN.

"""

from posda.database import Database
from posda.background.process import BackgroundProcess
from psycopg2.extras import execute_values

import argparse
from typing import List


def is_truthy(value: str) -> bool:
    return value.strip() not in ("", "0")


def get_files_by_import_event_id(db: Database,
                                 import_event_id: int,
                                 include_all_files: bool) -> List[int]:
    if include_all_files:
        query = """
            select distinct file_id
            from import_event
            natural join file_import
            where import_event_id = %s
        """
    else:
        query = """
            select distinct file_id
            from import_event
            natural join file_import
            natural join dicom_file
            where import_event_id = %s
        """

    with db.cursor() as cur:
        cur.execute(query, [import_event_id])
        results = cur.fetchall()

        return [r[0] for r in results]


def create_activity_timepoint(args, db: Database) -> int:
    query = """\
        insert into activity_timepoint(
            activity_id,
            when_created,
            who_created,
            comment,
            creating_user
        ) values (
            %s, now(), %s, %s, %s
        )
        returning activity_timepoint_id
    """

    with db.cursor() as cur:
        cur.execute(
            query,
            [
                args.activity_id,
                args.notify,
                args.comment,
                args.notify
            ]
        )

        for activity_timepoint_id, in cur:
            return activity_timepoint_id


def insert_files_into_timepoint(db: Database,
                                timepoint_id: int,
                                file_ids: List[int]) -> None:

    with db.cursor() as cur:
        query = """\
            insert into activity_timepoint_file
            values %s
        """
        value_list = [(timepoint_id, file_id)
                      for file_id in file_ids]
        execute_values(cur, query, value_list)


def main(args):
    background = BackgroundProcess(args.background_id,
                                   args.notify,
                                   args.activity_id)
    background.daemonize()

    print(f"Preparing to create a timepoint in activity_id "
          f"{args.activity_id} from import_event_id {args.import_event_id}.")

    db = Database("posda_files")

    include_all_files = is_truthy(args.include_all_files)
    file_kind = "files" if include_all_files else "DICOM files"

    file_ids = get_files_by_import_event_id(
        db, args.import_event_id, include_all_files)

    if len(file_ids) <= 0:
        print(f"Import event has no {file_kind}! Aborting!")
        background.finish(
            f"No {file_kind} found for import_event_id "
            f"{args.import_event_id}; no timepoint created")
        return

    print(f"Import event has {len(file_ids)} {file_kind}.")
    background.set_activity_status(
        f"Read files from import event, found {len(file_ids)}")

    new_tp_id = create_activity_timepoint(args, db)

    print(f"New activity_timepoint_id is {new_tp_id}")
    insert_files_into_timepoint(db, new_tp_id, file_ids)

    background.finish(
        f"Created activity_timepoint {new_tp_id} "
        f"with {len(file_ids)} files")


def parse_args():
    parser = argparse.ArgumentParser(description=ABOUT)
    parser.add_argument('background_id', help='the background_subprocess_id')
    parser.add_argument(
        'activity_id',
        help='the activity to create the new timepoint in'
    )
    parser.add_argument(
        'import_event_id',
        help='the import event whose DICOM files fill the new timepoint'
    )
    parser.add_argument('comment', help='comment for the new timepoint')
    parser.add_argument('notify', help='user to notify when complete')
    parser.add_argument(
        'include_all_files',
        nargs='?',
        default='0',
        help='pass 1 to include all files, not just DICOM files (default 0)'
    )

    return parser.parse_args()


if __name__ == '__main__':
    main(parse_args())
