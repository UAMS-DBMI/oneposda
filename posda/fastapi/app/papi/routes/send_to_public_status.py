import json
import logging
from fastapi import Depends, APIRouter, HTTPException
from starlette.responses import HTMLResponse
from pydantic import BaseModel
from typing import List
import datetime
from pprint import pformat
from jinja2 import Template as JinjaTemplate
from urllib.parse import quote_plus

from .auth import logged_in_user, User
from ..util import Database

router = APIRouter(
    tags=["Send to Public Status"],
    dependencies=[logged_in_user]
)


def build_curl_command(file_dict):
    """Build the NBIA submitDICOM curl command from a file dict.

    Mirrors the shape ream serializes: subprocess_invocation_id, file_id,
    collection, site, site_id, batch, filename, third_party_analysis_url.
    """
    bits = [
        ('project', quote_plus(str(file_dict.get('collection', '')))),
        ('siteName', quote_plus(str(file_dict.get('site', '')))),
        ('siteID', quote_plus(str(file_dict.get('site_id', '')))),
        ('batch', quote_plus(str(file_dict.get('batch', '')))),
        ('uri', file_dict.get('filename', '')),
    ]

    tpa_url = file_dict.get('third_party_analysis_url')
    if tpa_url is not None:
        bits.append(('third_party_analysis_url', tpa_url))

    out = "&".join(f"{k}={v}" for k, v in bits)

    return (
        'curl -H "Authorization:Bearer $TOKEN" '
        '-k "https://$HOSTNAME/nbia-api/services/submitDICOM" '
        f'-d "{out}" '
    )


LEGACY_ERROR_MARKER = "(legacy error format, see logs)"


def parse_error_message(message):
    """Parse an error_message row from public_copy_status.

    New rows are JSON written by ream's serialize_submit_error. Older rows
    are Python reprs (str(SubmitFailedError(...))) and are no longer parsed
    here — those return a legacy marker so the page still renders.
    """
    if not message:
        return None
    try:
        return json.loads(message)
    except (ValueError, TypeError):
        logging.info("public_copy_status row is in legacy format; skipping parse")
        return None

@router.get("/")
async def get_all_studies():
    raise HTTPException(detail="test error, not allowed", status_code=401)

@router.get("/report/{subprocess_invocation_id}")
async def report(subprocess_invocation_id: int, pretty: bool = False, db: Database = Depends()):

    # Get counts of success/failure/total
    query = """
        select
            success, count(file_id)
        from public_copy_status
        where subprocess_invocation_id = $1
        group by success
    """

    rows = await db.fetch(query, [subprocess_invocation_id])

    total_files = sum([count for _, count in rows])


    # If there were any errors, get a sample of the error text
    query2 = """
        select
            error_message
        from public_copy_status
        where subprocess_invocation_id = $1
          and success = false
          limit 5
    """

    errors = await db.fetch(query2, [subprocess_invocation_id])


    obj_subset = []

    for error in errors:
        parsed = parse_error_message(error['error_message'])

        if parsed is None:
            obj_subset.append({'error_message': LEGACY_ERROR_MARKER})
            continue

        file_dict = dict(parsed.get('file') or {})
        inner_errors = parsed.get('errors') or []
        if inner_errors:
            file_dict['error_message'] = str(inner_errors[0])[:500]
        file_dict['curl'] = build_curl_command(file_dict)

        obj_subset.append(file_dict)

    if pretty:
        return render_pretty(subprocess_invocation_id, 
                             rows, 
                             total_files,
                             obj_subset)
    else:
        return {
            'overal_status': rows,
            'total_files': total_files,
            'first_5_errors': obj_subset,
        }


def render_pretty(invoc_id: int, rows, total_files, file_objs):
    templ = JinjaTemplate("""
<html>
<head>
    <title>Report for {{invoc_id}}</title>
    <style type="text/css">
        body {
            background-color: #EEEEEE;
        }
        td, th {
            border: 2px solid #C7C7C7;
            padding: 10px;
        }
        th {
            text-align: right;
        }
        table {
            margin-bottom: 1em;
            border-collapse: collapse;
        }
    </style>
</head>
<body>
<h1>Public Copy Report for ID#{{invoc_id}}</h1>

<h3>Overall status</h3>
<table>
<tr>
    <th>Count of files</th>
    <th>Sucessful?</th>
</tr>
{% for row in rows %}
<tr>
    <td>{{row.count}}</td>
    <td>{{row.success}}</td>
</tr>
{% endfor %}
<tr>
    <td>{{total_files}}</td>
    <td>Both</td>
</tr>
</table>

<h3>First 5 files that failed</h3>
{% for file in files %}
<table>
<tr>
    <th>file_id</th>
    <td><a href="/viewer/file/{{file.file_id}}" target="_blank">{{file.file_id}}</a></td>
</tr>
<tr>
    <th>collection</th>
    <td>{{file.collection}}</td>
</tr>
<tr>
    <th>site</th>
    <td>{{file.site}}</td>
</tr>
<tr>
    <th>site_id</th>
    <td>{{file.site_id}}</td>
</tr>
<tr>
    <th>filename</th>
    <td>{{file.filename}}</td>
</tr>
<tr>
    <th>batch</th>
    <td>{{file.batch}}</td>
</tr>
<tr>
    <th>third_party_analysis_url</th>
    <td>{{file.third_party_analysis_url}}</td>
</tr>
<tr>
    <th>error_message</th>
    <td>{{file.error_message}}</td>
</tr>
<tr>
    <th>API Command for NBIA Debugging</th>
    <td>
        {{file.curl}}
    </td>
</tr>
</table>
{% endfor %}

</body>
</html>
    """)

    return HTMLResponse(templ.render(invoc_id=invoc_id, 
                                     rows=rows, 
                                     total_files=total_files,
                                     files=file_objs))


@router.get("/find_send_ready_to_begin_status_updates")
async def find_send_ready_to_begin_status_updates(db: Database = Depends()):
    query = """\
        select distinct
                subprocess_invocation_id
        from
                activity_task_status
                natural join public_copy_status
        where
                manual_update = true
    """

    return await db.fetch(query)

@router.get("/get_success_percentage_for_send/{subprocess_invocation_id}")
async def get_success_percentage_for_send(subprocess_invocation_id: int, db: Database = Depends()):
    query = """\
        select
            ('' || success::text || ' ' || ((count(*)/(select  sum(c) as t from
            ( select
                count(file_id) as c
                from
                    activity_timepoint_file
                where
                    activity_timepoint_id = (
                	select max(activity_timepoint_id)
                	from activity_timepoint
                	where activity_id = (
                		select activity_id
                		from activity_task_status
                		where subprocess_invocation_id = $1 )))
                		as sum_table)::float) * 100.0)::int || '%')::text as summary
        from
            public_copy_status
        where
            subprocess_invocation_id = $1
        group by
            success
            """
    return await db.fetch(query, [subprocess_invocation_id])

# TODO This method should be POST/PUT, not GET!
@router.get("/update_activity_status/{subprocess_invocation_id}/{new_status}")
async def update_activity_status(subprocess_invocation_id: int, new_status: str, db: Database = Depends()):
    query = """\
        update
            activity_task_status
        set
            status_text = $2
        where
            activity_task_status.manual_update = true
            and subprocess_invocation_id = $1
    """
    return await db.fetch(query, [subprocess_invocation_id, new_status])

@router.get("/finish_activity_status/{subprocess_invocation_id}")
async def finish_activity_status(subprocess_invocation_id: int, db: Database = Depends()):
    query = """\
        update
            activity_task_status
        set
            manual_update = false
        where
            activity_task_status.manual_update = true
            and subprocess_invocation_id = $1
    """

    return await db.fetch(query, [subprocess_invocation_id])
