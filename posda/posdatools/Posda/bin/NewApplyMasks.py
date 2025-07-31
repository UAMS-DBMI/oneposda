#!/usr/bin/env python3
"""
A new version of the ApplyMasks script
"""
import argparse
import hashlib
import pydicom
import csv
from collections import defaultdict
from posda.database import Database

from posda.database import Database
from pydicom.sequence import Sequence

from pprint import pprint

TCIA_UID_ROOT = "1.3.6.1.4.1.14519.5.2.1"
filename = "/nas/public/posda/storage/0e/f6/07/0ef60727f2866730c97e87973001ddc1"

def hash_uid(uid, uid_root):
    md5 = hashlib.md5(uid.encode())
    new_uid = f"{uid_root}.{int(md5.hexdigest(), 16)}"[:64]
    return new_uid

def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('background_id', help='the background_subprocess_id')
    parser.add_argument(
        'activity_id',
        help='the primary activity to run against'
    )
    parser.add_argument('notify', help='user to notify when complete')
    parser.add_argument(
        'visual_review_instance_id',
        help='the visual review the masks were created in'
    )
    parser.add_argument(
        'process_masks',
        help='if set, process the Mask items'
    )
    parser.add_argument(
        'process_sliceremove',
        help='if set, process the Slice Remove items'
    )
    parser.add_argument(
        'process_blackout',
        help='if set, process the Blackout items'
    )
    parser.add_argument(
        'premasked_site_name',
        help=(
            'if set, all pre-masked series will have their site name set'
            'to this value'
        )
    )
    parser.add_argument(
        'premasked_activity_id',
        # a trick to make it an int or empty string
        type=lambda x: int(x) if x.lower() != '' else None,
        help=(
            "if set, all pre-masked series will be moved to this activity_id; use 'None' for no value"
        )
    )
    return parser.parse_args()

def generate_arg_report(args):
    to_process = []
    if args.process_masks:
        to_process.append("Masks")
    if args.process_sliceremove:
        to_process.append("Slice Remove")
    if args.process_blackout:
        to_process.append("Blackout")
    
    print("NewApplyMasks.py running with the following arguments:")
    print(f"Activity ID: {args.activity_id}")
    print(f"Visual Review Instance ID: {args.visual_review_instance_id}")

    print("Will process:", ', '.join(to_process))

    # determine path
    if args.premasked_site_name:
        print(f"Pre-masked files will be edited to have site name: {args.premasked_site_name}")
    if args.premasked_activity_id is not None:
        print(f"Pre-masked files will be moved to activity_id: {args.premasked_activity_id}")

    if not (args.premasked_site_name and args.premasked_activity_id is not None):
        args.delete_premasked = True
        print("No pre-masked site name or activity ID provided, pre-masked files will be DELETED.")

    print("------------------------------------------")

def verify_iec_status(visual_review_instance_id, conn):
        cur = conn.cursor()
        cur.execute("""
            select
                masking_status,
                count(*)
            from
                masking
                natural join image_equivalence_class
            where
                visual_review_instance_id = %s
                and masking_status not in ('accepted', 'skipped')
            group by 1
        """, (visual_review_instance_id,))

        invalid_statuses = cur.fetchall()

        if len(invalid_statuses) > 0:
            print("ERROR: There are IECs in the VR that are not 'accepted' or 'skipped'.")
            print("Please resolve these before proceeding.")


            print("Invalid IEC statuses:")
            for status, count in invalid_statuses:
                # print(f"{count} are set to {status}")
                print(f"\t{status}: {count} IECs")

            # raise ValueError("IEC status verification failed.")
            print("NOTE: continuing anyway, uncomment above for PROD")

def get_orphaned_iecs(visual_review_instance_id, conn):
    cur = conn.cursor()
    cur.execute("""
        /*
                Get "orphaned" IECs in the VR: those IECs (which are NOT going to be
                processed) that are part of series which ARE going to be processed

                Inputs:
                        visual_review_instance_id
        */
        with all_iecs_with_function as (
                /*
                        Gets all IECs in the given Visual Review (that have been flagged
                        for masking) along with the selected function, and status.
                */
                select distinct
                        series_instance_uid,
                        image_equivalence_class_id,
                        masking_parameters ->> 'function' as function,
                        masking_status
                from
                        image_equivalence_class
                        natural join image_equivalence_class_input_image
                        natural join masking
                        natural join file_series
                where
                        visual_review_instance_id = %s
                order by 1
        ), iecs_to_work_on as (
                /*
                        Gets the IECs in the VR we plan to work on (along with their series)
                */
                select
                        image_equivalence_class_id,
                        series_instance_uid
                from
                        all_iecs_with_function
                where
                        masking_status = 'accepted'
                        /* and function = 'mask' */
        ), iecs_not_to_work_on as (
                /*
                        Gets the IECs in the VR we do not plan to work on (along with their series)
                        (This is mostly the opposite of the previous one)
                */
                select
                        image_equivalence_class_id,
                        series_instance_uid,
                        function,
                        masking_status
                from all_iecs_with_function
                /* NOTE: We include all functions here, not just the selected one,
                                under the assumption that anything set to 'accepted' is
                                not an orphan, but will be processed eventually */
                where not masking_status = 'accepted'
        )

        select
            series_instance_uid,
            iecs_not_to_work_on.image_equivalence_class_id,
                iecs_not_to_work_on.function,
                iecs_not_to_work_on.masking_status
        from
            iecs_not_to_work_on
            join iecs_to_work_on using (series_instance_uid)
    """, (visual_review_instance_id,))

    return [row.image_equivalence_class_id for row in cur]

def get_referencing_segs(visual_review_instance_id, activity_id, function, conn):
    cur = conn.cursor()
    cur.execute("""
        with all_iecs_with_function as (
            /*
            Gets all IECs in the given Visual Review (that have been flagged
            for masking) along with the selected function, and status.
            */
            select distinct
                series_instance_uid,
                image_equivalence_class_id,
                masking_parameters ->> 'function' as function,
                masking_status
            from
                image_equivalence_class
                natural join image_equivalence_class_input_image
                natural join masking
                natural join file_series
            where
                visual_review_instance_id = %s
            order by
                1
        ), iecs_to_work_on as (
            /*
            Gets the IECs in the VR we plan to work on (along with their series)
            */
            select
                image_equivalence_class_id,
                series_instance_uid
            from
                all_iecs_with_function
            where
                masking_status = 'accepted'
                and function = %s
        ), files_to_work_on as (
                select file_id
                from image_equivalence_class_input_image
                natural join iecs_to_work_on
        ), files_in_activity as (
                select
                    file_id
                from
                    activity_timepoint_file
                where
                    activity_timepoint_id = (
                            select max(activity_timepoint_id)
                            from activity_timepoint
                            where activity_id = %s
                    )
        )
        /* Find seg files that reference any of the files we plan to modify */
        select distinct seg_id as file_id
        from files_to_work_on
        natural join file_seg_image_linkage
        natural join files_in_activity
    """, (visual_review_instance_id, function, activity_id))

    return [row.file_id for row in cur]

def get_referencing_rois(visual_review_instance_id, activity_id, function, conn):
    # TODO: this query is wrong, roi_id is NOT a file_id, the query needs to be
    # adjusted to find the actual file_id via the referenced_sop_instance_uid
    cur = conn.cursor()
    cur.execute("""
        with all_iecs_with_function as (
            /*
            Gets all IECs in the given Visual Review (that have been flagged
            for masking) along with the selected function, and status.
            */
            select distinct
                series_instance_uid,
                image_equivalence_class_id,
                masking_parameters ->> 'function' as function,
                masking_status
            from
                image_equivalence_class
                natural join image_equivalence_class_input_image
                natural join masking
                natural join file_series
            where
                visual_review_instance_id = %s
            order by
                1
        ), iecs_to_work_on as (
            /*
            Gets the IECs in the VR we plan to work on (along with their series)
            */
            select
                image_equivalence_class_id,
                series_instance_uid
            from
                all_iecs_with_function
            where
                masking_status = 'accepted'
                and function = %s
        ), files_to_work_on as (
                select file_id
                from image_equivalence_class_input_image
                natural join iecs_to_work_on
        ), files_in_activity as (
                select
                    file_id
                from
                    activity_timepoint_file
                where
                    activity_timepoint_id = (
                            select max(activity_timepoint_id)
                            from activity_timepoint
                            where activity_id = %s
                    )
        )
        /* Find seg files that reference any of the files we plan to modify */
        select distinct roi_id as file_id
        from files_to_work_on
        natural join file_roi_image_linkage
        natural join files_in_activity
    """, (visual_review_instance_id, function, activity_id))

    return [row.file_id for row in cur]

def get_referencing_regs(visual_review_instance_id, activity_id, function, conn):
    """
    
    The plan:
    1. Identify all REGs in the activity
    2. For each REG, check if it references any of the files we plan to work on 
        (in the VR and of the function)
    3. If it does, return the REG file_id
    
    """

    cur = conn.cursor()
    # TODO: this is not done, look at the other ones, this needs to select only
    # files that we are "working on" (in the activity, the function, and the VR)
    cur.execute("""
    with files_in_activity as (
            select
                    file_id
            from
                    activity_timepoint_file
            where
                    activity_timepoint_id = (
                            select max(activity_timepoint_id)
                            from activity_timepoint
                            where activity_id = %s
                    )
    )

    select storage_path(file_id), file_id
    from files_in_activity
    natural join file_series
    where modality = 'REG'
    """, (activity_id,))

    for row in cur:
        print(row)

def get_dicom_sequence_items_list(ds, sequence_name, item_names):
    """
    Extracts items from a DICOM sequence given a sequence and item names.

    sequence_name: The name of a top‐level sequence attribute in the DICOM file.
    item_names: A list of leaf item names (DataElement keywords) to extract.

    Recursively searches all items under sequence_name looking for any
    DataElements with a keyword listed in item_names, and returns a list of
    tuples containing their value and their full path.
    """

    if not hasattr(ds, sequence_name):
        return []

    seq = getattr(ds, sequence_name)
    if not isinstance(seq, (Sequence, list)):
        return []

    results = []

    def recurse(dataset, path):
        # if it is not a Dataset or Sequence, we can't recurse further
        if not isinstance(dataset, (pydicom.dataset.Dataset, Sequence)):
            return
        for data_element in dataset:
            keyword = data_element.keyword
            # if this element is one of the requested leaf items, collect its value and path
            if keyword in item_names:
                full_path = ".".join(path + [keyword])
                results.append((data_element.value, full_path, data_element))
            # if the value is itself a sequence of datasets, recurse into each
            val = data_element.value
            if isinstance(val, (Sequence, list)):
                for idx, item in enumerate(val):
                    recurse(item, path + [f"{keyword}[{idx}]"])

    # start recursion on each item in the top-level sequence
    for idx, item in enumerate(seq):
        recurse(item, [f"{sequence_name}[{idx}]"])

    return results

def load_map():
    """
    Load the mapping of SOP Class UIDs to sequence keys and element keys,
    used to identify which elements need to have their UIDs hashed.
    """

    # eventual structure:
    # sop_map = {
    #     'sop_class_uid': {
    #         'seq_key': [ ele_key1, ele_key2, ... ],
    #     }
    # }
    sop_map = defaultdict(lambda: defaultdict(set))

    ## The DICOM standard is stored in the dicom_dd database.
    with Database("dicom_dd") as conn:
        cur = conn.cursor()
        cur.execute("""
            with sequences as
            (
                select tag as seq_tag, 
                    name as seq_name, 
                    keyword as seq_key 
                from dicom_element
                where lower(name) like '%sequence%'
                and (
                    lower(name) like '%reference%'
                    or lower(name) like '%source%'
                    or lower(name) like '%derivation%'
                    or lower(name) like '%evidence%'
                    or lower(name) like '%procedure%'
                    or lower(name) like '%instance%'
                    or lower(name) like '%matrix%'
                    or lower(name) like '%fiducial%'
                    or lower(name) like '%contour%'
                    or lower(name) like '%functional%'
                )
            ),
            elements as
            (
                select tag as ele_tag, 
                    name as ele_name, 
                    keyword as ele_key
                from dicom_element
                where lower(name) like '%instance%uid%'
                and (
                    lower(name) like '%series%'
                    or lower(name) like '%sop%'
                )
            )
            select
            req.sop_class_uid,
            dsc.sop_class_name,
            req.tag_full,
            seq.seq_tag,
            seq.seq_key,
            ele.ele_tag,
            ele.ele_key
            from dicom_class_iod_requirements req
            join dicom_sop_classes dsc 
            on dsc.sop_class_uid = req.sop_class_uid 
            join dicom_class_iod_requirements_tags rt_seq
            on req.tag_full = rt_seq.tag_full
            join sequences seq
            on rt_seq.tag = seq.seq_tag
            join dicom_class_iod_requirements_tags rt_ele
            on req.tag_full = rt_ele.tag_full
            join elements ele
            on rt_ele.tag = ele.ele_tag
            order by req.sop_class_uid, req.tag_full
        """)

        for row in cur:
            sop_map[row.sop_class_uid][row.seq_key].add(row.ele_key)

    return sop_map

def get_referencing_files(visual_review_instance_id, activity_id, function, sop_map, conn):
    cur = conn.cursor()
    cur.execute("""
        with all_iecs_with_function as (
                /*
                Gets all IECs in the given Visual Review (that have been flagged
                for masking) along with the selected function, and status.
                */
                select distinct
                        series_instance_uid,
                        image_equivalence_class_id,
                        masking_parameters ->> 'function' as function,
                        masking_status
                from
                        image_equivalence_class
                        natural join image_equivalence_class_input_image
                        natural join masking
                        natural join file_series
                where
                        visual_review_instance_id = %s
                order by
                        1
        ), iecs_to_work_on as (
                /*
                Gets the IECs in the VR we plan to work on (along with their series)
                */
                select
                        image_equivalence_class_id,
                        series_instance_uid
                from
                        all_iecs_with_function
                where
                        masking_status = 'accepted'
                        and function = %s
        ), files_to_work_on as (
                        select file_id
                        from image_equivalence_class_input_image
                        natural join iecs_to_work_on
        ), files_in_activity as (
                        select
                                file_id
                        from
                                activity_timepoint_file
                        where
                                activity_timepoint_id = (
                                                select max(activity_timepoint_id)
                                                from activity_timepoint
                                                where activity_id = %s
                                )
        )
        select file_id, storage_path(file_id), media_storage_sop_class
        from files_in_activity
        natural join file_meta
    """, (visual_review_instance_id, function, activity_id))

    for row in cur:
        if row.media_storage_sop_class in sop_map:
            print(row)

def main(args):
    generate_arg_report(args)

    conn = Database("posda_files")
    ## Step 1: Verify all IECs in the VR are set to "accepted" or "skipped"
    verify_iec_status(args.visual_review_instance_id, conn)

    ## Step 2: Identify orphaned files from masked series that didn’t get masked (scouts, etc.)
    orphans = get_orphaned_iecs(args.visual_review_instance_id, conn)
    print(orphans)

    ## Step 3: Identify referencing files that reference the pre-masked images (regs, segs, etc.).
    # how? I don't think we have this in the database, do we?
    # well, we do have:
        # public │ file_roi_image_linkage │ table │ posda
        # public │ file_seg_image_linkage │ table │ posda

    #### This is the old way, now we are going to identify all referencing
    #### files based on their SOP Class UID

    # ## Collect all referencing SEGs (based on function)
    # referencing_segs = []
    # if args.process_masks:
    #     referencing_segs += get_referencing_segs(
    #         args.visual_review_instance_id,
    #         args.activity_id,
    #         'mask',
    #         conn
    #     )
    # if args.process_sliceremove:
    #     referencing_segs += get_referencing_segs(
    #         args.visual_review_instance_id,
    #         args.activity_id,
    #         'sliceremove',
    #         conn
    #     )
    # if args.process_blackout:
    #     referencing_segs += get_referencing_segs(
    #         args.visual_review_instance_id,
    #         args.activity_id,
    #         'blackout',
    #         conn
    #     )

    # print("Referencing Segs:")
    # print(referencing_segs)

    # ## TODO: do the same for RTSTRUCTs ("rois"?)
    # t = get_referencing_rois(
    #     args.visual_review_instance_id,
    #     args.activity_id,
    #     'blackout',
    #     conn
    # )

    # print("Referencing ROIs:")
    # print(t)

    sop_map = load_map()

    ## Because basically every file could have a reference, we need to scan them
    ## all somehow. And we need to check each reference and see if it matches
    ## one of the files we masked. So we need a list of sop_instance_uids for all 
    ## masked files.
    get_referencing_files(args.visual_review_instance_id, args.activity_id, 'blackout', sop_map, conn)





    # Make copies of orphaned and referencing files
        # Update Instance UID to make unique
        # Update Series UID to match UIDs of corresponding masked images.
        # Update referencing sequence UIDs to point to masked files
        # Update source image sequence UIDs to point to masked files ???


def test():
    sop_map = load_map()

    filename = "test.dcm"
    ds = pydicom.dcmread(filename)

    # look up it's sop class uid in the map
    sop_class_uid = ds.SOPClassUID

    this_map = sop_map.get(sop_class_uid, None)
    if not this_map:
        print(f"No mapping found for SOP Class UID: {sop_class_uid}")
        return

    for seq_key, ele_keys in this_map.items():
        for value, full_path, ele in get_dicom_sequence_items_list(ds, seq_key, list(ele_keys)):
            # hash these UIDs
            ele.value = hash_uid(ele.value, TCIA_UID_ROOT)

    # save the updated DICOM file
    ds.save_as("updated_" + filename)

if __name__ == '__main__':
    # test()
    main(parse_args())