// Ports papi/routes/importer.py. Import operations do not require a
// logged in user.

import { mkdirSync, renameSync, statSync, unlinkSync } from "node:fs";
import type { App, Ctx } from "../server";
import { doc } from "../openapi";
import { pathInt, queryBool, queryIntPtr } from "../server";
import { HttpError, jsonResponse } from "../httpx";
import { fetchOneOn, type Tx } from "../db";

// Caches the file_storage_root table, mirroring the module-level
// ROOT_MAP_CACHE (loaded once, never invalidated).
let rootMapCache: Map<string, number> | null = null;

export function registerImporter(app: App): void {
  app.pub("PUT", "/v1/import/event", (ctx) => importEvent(app, ctx),
    doc({
      summary: "Import Event",
      description: "Create a new import event.\n\nImport events are a way to group individual file imports together.\n\nArgs:\n    source (str): A human-readable comment.\n    origin (str, optional): The source or origin of the files.\n    expected_count (int, optional): How many files you have to import,\n                                    if known.",
      params: {
        source: { in: "query", required: true },
        origin: { in: "query" },
        expected_count: { in: "query", type: "integer" },
      },
    }),
  );
  app.pub("POST", "/v1/import/event/:import_event_id/close", (ctx) =>
    closeImportEvent(app, ctx),
    doc({
      summary: "Close Import Event",
      description: "Close an import event, by setting it's import_close_time to now.",
      params: {
        import_event_id: { type: "integer" },
      },
    }),
  );
  app.pub("POST", "/v1/import/test", () => importTest(app),
    doc({
      summary: "Import Test",
    }),
  );
  app.pub("PUT", "/v1/import/file", (ctx) => importFile(app, ctx),
    doc({
      summary: "Import File",
      description: "Import a single file.\n\nBoth POST and PUT are accepted for legacy reasons.\n\nThe request body must be the bytes of the file to submit.\n\nIf subprocess_invocation_id AND from_file_digest are given,\na link will be made (via dicom_edit_compare) to indicate the\norigin of this file.",
      params: {
        digest: { in: "query", required: true },
        import_event_id: { in: "query", type: "integer" },
        localpath: { in: "query" },
        subprocess_invocation_id: { in: "query", type: "integer" },
        from_file_digest: { in: "query" },
      },
    }),
  );
  app.pub("POST", "/v1/import/file", (ctx) => importFile(app, ctx),
    doc({
      summary: "Import File",
      description: "Import a single file.\n\nBoth POST and PUT are accepted for legacy reasons.\n\nThe request body must be the bytes of the file to submit.\n\nIf subprocess_invocation_id AND from_file_digest are given,\na link will be made (via dicom_edit_compare) to indicate the\norigin of this file.",
      params: {
        digest: { in: "query", required: true },
        import_event_id: { in: "query", type: "integer" },
        localpath: { in: "query" },
        subprocess_invocation_id: { in: "query", type: "integer" },
        from_file_digest: { in: "query" },
      },
    }),
  );
  app.pub("POST", "/v1/import/file_in_place", (ctx) =>
    importFileInPlace(app, ctx),
    doc({
      summary: "Import File In Place",
      params: {
        localpath: { in: "query", required: true },
        import_event_id: { in: "query", type: "integer" },
        skip_processing: { in: "query", type: "boolean" },
        digest: { in: "query" },
      },
    }),
  );
}

async function importEvent(app: App, ctx: Ctx): Promise<Response> {
  if (!ctx.url.searchParams.has("source")) {
    throw new HttpError(422, 'query parameter "source" is required');
  }
  const source = ctx.url.searchParams.get("source")!;
  const origin = ctx.url.searchParams.get("origin") ?? "";
  const expectedCount = queryIntPtr(ctx, "expected_count");

  const eventId = await app.db.tx((tx) =>
    createImportEvent(tx, source, origin !== "" ? origin : null, expectedCount),
  );

  return jsonResponse({ status: "success", import_event_id: eventId });
}

async function createImportEvent(
  tx: Tx,
  comment: string,
  origin: string | null,
  expectedCount: number | null,
): Promise<number> {
  const row = await fetchOneOn<{ import_event_id: number }>(
    tx,
    `
    insert into import_event
    (import_type, import_comment, import_time, import_origin, import_expected_count)
    values
    ($1, $2, now(), $3, $4)
    returning import_event_id
    `,
    ["posda-api import", comment, origin, expectedCount],
  );
  if (!row) throw new Error("import_event insert returned no row");
  return row.import_event_id;
}

async function closeImportEvent(app: App, ctx: Ctx): Promise<Response> {
  const eventId = pathInt(ctx, "import_event_id");
  const row = await app.db.fetchOne(
    `
    update import_event
    set import_close_time = now()
    where import_event_id = $1
    returning import_event_id
    `,
    [eventId],
  );
  if (!row) throw new HttpError(422, "invalid import_event_id");
  return jsonResponse({ status: "success" });
}

async function importTest(app: App): Promise<Response> {
  await app.db.tx((tx) => createOrGetFileId(tx, "bogus1", 37));
  return jsonResponse("Success");
}

async function importFile(app: App, ctx: Ctx): Promise<Response> {
  if (!ctx.url.searchParams.has("digest")) {
    throw new HttpError(422, 'query parameter "digest" is required');
  }
  const digest = ctx.url.searchParams.get("digest")!;
  const importEventId = queryIntPtr(ctx, "import_event_id");
  const localpath = ctx.url.searchParams.get("localpath") ?? "";
  const subprocessInvocationId = queryIntPtr(ctx, "subprocess_invocation_id");
  const fromFileDigest = ctx.url.searchParams.get("from_file_digest") ?? "";

  // Spool the request body to a temp file, hashing as we go.
  const tmpName = `${app.cfg.tempStoragePath}/upload${crypto.randomUUID()}`;
  const hash = new Bun.CryptoHasher("md5");
  let bytesRead = 0;
  try {
    const writer = Bun.file(tmpName).writer();
    if (ctx.req.body) {
      for await (const chunk of ctx.req.body) {
        hash.update(chunk);
        bytesRead += chunk.byteLength;
        writer.write(chunk);
      }
    }
    await writer.end();
  } catch (err) {
    tryUnlink(tmpName);
    throw err;
  }

  const computedDigest = hash.digest("hex");
  if (computedDigest !== digest) {
    tryUnlink(tmpName);
    throw new HttpError(
      422,
      "digest of received bytes does not match supplied digest",
    );
  }

  const response = await app.db.tx(async (tx) => {
    const [created, fileId] = await createOrGetFileId(
      tx,
      computedDigest,
      bytesRead,
    );

    if (created) {
      const [rootId, relPath] = copyFileIntoPlace(app, tmpName, computedDigest);
      await createFileLocation(tx, fileId, rootId, relPath);
      await setReadyToProcess(tx, fileId, true);
    } else {
      tryUnlink(tmpName);
    }

    const eventId =
      importEventId ??
      (await createImportEvent(tx, "single-file api import", null, null));
    await createFileImport(tx, fileId, eventId, localpath);

    if (subprocessInvocationId !== null && fromFileDigest !== "") {
      await tx.unsafe(
        `
        insert into dicom_edit_compare
        values ($1, $2, 0, 0, null, $3)
        `,
        [fromFileDigest, digest, subprocessInvocationId],
      );
    }

    return {
      status: "success",
      size: bytesRead,
      digest: computedDigest,
      file_id: fileId,
      created,
    };
  });
  return jsonResponse(response);
}

async function importFileInPlace(app: App, ctx: Ctx): Promise<Response> {
  const localpath = ctx.url.searchParams.get("localpath") ?? "";
  if (localpath === "") {
    throw new HttpError(422, 'query parameter "localpath" is required');
  }
  const importEventId = queryIntPtr(ctx, "import_event_id");
  const skipProcessing = queryBool(ctx, "skip_processing", false);
  let digest = ctx.url.searchParams.get("digest") ?? "";

  const rootMap = await getRootMap(app);
  const [matchRoot, relPath] = findBestRoot(rootMap, localpath);

  let size: number;
  if (digest !== "") {
    try {
      size = statSync(localpath).size;
    } catch {
      throw new HttpError(422, "no such file");
    }
  } else {
    try {
      [size, digest] = await md5sumFile(localpath);
    } catch {
      throw new HttpError(422, "no such file");
    }
  }

  const response = await app.db.tx(async (tx) => {
    const [created, fileId] = await createOrGetFileId(tx, digest, size);

    if (created) {
      await createFileLocation(tx, fileId, matchRoot, relPath);
      await setReadyToProcess(tx, fileId, !skipProcessing);
    }

    const eventId =
      importEventId ??
      (await createImportEvent(tx, "single-file in-place api import", null, null));
    await createFileImport(tx, fileId, eventId, localpath);

    return {
      status: "success",
      size,
      digest,
      file_id: fileId,
      created,
    };
  });
  return jsonResponse(response);
}

// --- helpers ----------------------------------------------------------

function tryUnlink(path: string): void {
  try {
    unlinkSync(path);
  } catch {
    // already gone
  }
}

async function getRootMap(app: App): Promise<Map<string, number>> {
  if (rootMapCache) return rootMapCache;
  const rows = await app.db.fetch<{
    file_storage_root_id: number;
    root_path: string | null;
  }>(
    `
    select file_storage_root_id, root_path, current, storage_class
    from file_storage_root
    order by file_storage_root_id
    `,
  );
  rootMapCache = new Map(
    rows.map((row) => [row.root_path ?? "", row.file_storage_root_id]),
  );
  return rootMapCache;
}

/** Pick the longest storage root that prefixes path. */
function findBestRoot(
  rootMap: Map<string, number>,
  path: string,
): [number, string] {
  let best: { rootLen: number; rootId: number; relPath: string } | null = null;
  for (const [root, id] of rootMap) {
    if (path.length > root.length && path.startsWith(root)) {
      const relPath = path.slice(root.length + 1);
      const rootLen = path.length - relPath.length;
      if (!best || rootLen > best.rootLen) {
        best = { rootLen, rootId: id, relPath };
      }
    }
  }
  if (!best) {
    throw new HttpError(422, "no matching file_storage_root");
  }
  return [best.rootId, best.relPath];
}

async function md5sumFile(path: string): Promise<[number, string]> {
  const hash = new Bun.CryptoHasher("md5");
  let size = 0;
  const stream = Bun.file(path).stream();
  for await (const chunk of stream) {
    hash.update(chunk);
    size += chunk.byteLength;
  }
  return [size, hash.digest("hex")];
}

/**
 * Move the spooled upload into the storage tree (sharded by digest
 * prefix) and return the root id and rel path.
 */
function copyFileIntoPlace(
  app: App,
  tmpName: string,
  digest: string,
): [number, string] {
  const shard = `${digest.slice(0, 2)}/${digest.slice(2, 4)}/${digest.slice(4, 6)}`;
  const relPath = `${shard}/${digest}`;

  mkdirSync(`${app.cfg.fileStoragePath}/${shard}`, { recursive: true });
  renameSync(tmpName, `${app.cfg.fileStoragePath}/${relPath}`);
  return [app.cfg.fileStorageRootId, relPath];
}

async function setReadyToProcess(
  tx: Tx,
  fileId: number,
  ready: boolean,
): Promise<void> {
  await tx.unsafe(
    `
    update file
    set ready_to_process = $2
    where file_id = $1
    `,
    [fileId, ready],
  );
}

async function createFileLocation(
  tx: Tx,
  fileId: number,
  rootId: number,
  relPath: string,
): Promise<void> {
  await tx.unsafe(
    `
    insert into file_location
    (file_id, file_storage_root_id, rel_path)
    values
    ($1, $2, $3)
    `,
    [fileId, rootId, relPath],
  );
}

async function createFileImport(
  tx: Tx,
  fileId: number,
  importEventId: number,
  localpath: string,
): Promise<void> {
  await tx.unsafe(
    `
    insert into file_import
    values
    ($1, $2, $3, $4, $5, now())
    `,
    [importEventId, fileId, null, null, localpath !== "" ? localpath : null],
  );
}

async function createOrGetFileId(
  tx: Tx,
  digest: string,
  size: number,
): Promise<[boolean, number]> {
  const inserted = await fetchOneOn<{ file_id: number }>(
    tx,
    `
    insert into file
    (digest, size, processing_priority)
    values
    ($1, $2, 1)
    on conflict do nothing
    returning file_id
    `,
    [digest, size],
  );
  if (inserted) return [true, inserted.file_id];

  const existing = await fetchOneOn<{ file_id: number }>(
    tx,
    `
    select file_id
    from file
    where digest = $1
    `,
    [digest],
  );
  if (!existing) {
    throw new Error(`file with digest ${digest} neither inserted nor found`);
  }
  return [false, existing.file_id];
}
