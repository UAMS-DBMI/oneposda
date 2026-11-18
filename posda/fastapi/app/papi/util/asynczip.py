"""
asynzip - Build a zip file from a directory, with asyncio?

"""

import asyncio
import zipstream
import os
from starlette.responses import StreamingResponse



async def stream_directory(path, dl_filename):
    if not path.endswith('/'):
        path += '/'


    z = zipstream.ZipFile(allowZip64=True)

    for dirpath, dirnames, filenames in os.walk(path):
        for filename in filenames:
            full_filename = os.path.join(dirpath, filename)

            z.write(full_filename)
            await asyncio.sleep(0)

    return StreamingResponse(z, media_type="application/zip",
                             headers={'Content-Disposition': f'attachment; filename="{dl_filename}"'})


async def stream_files(filelist, dl_filename):
    z = zipstream.ZipFile(allowZip64=True)

    for filename in filelist:
        z.write(str(filename))
        await asyncio.sleep(0)

    return StreamingResponse(iter(z), media_type="application/zip",
                             headers={'Content-Disposition': f'attachment; filename="{dl_filename}"'})


async def stream_named_files(files, dl_filename):
    """Like stream_files, but each entry is a (path, arcname) pair, so the zip
    holds the given names rather than the files' full server paths."""
    z = zipstream.ZipFile(allowZip64=True)

    for path, arcname in files:
        z.write(str(path), arcname=arcname)
        await asyncio.sleep(0)

    return StreamingResponse(iter(z), media_type="application/zip",
                             headers={'Content-Disposition': f'attachment; filename="{dl_filename}"'})
