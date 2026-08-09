// Ports papi/routes/edits.py.

import type { App, Ctx } from "../server";
import { doc } from "../openapi";
import { HttpError, jsonResponse } from "../httpx";
import { decodeJsonBody } from "./common";

// The Python version interpolated the client-supplied table/column
// names into SQL verbatim; this keeps the flexibility while refusing
// anything that isn't a plain identifier.
const identifierRe = /^[a-zA-Z_][a-zA-Z0-9_]*$/;

interface EditStateBody {
  edit_id?: number;
  expected_state?: string;
  new_state?: string;
  table_name?: string;
  column_name?: string;
}

export function registerEdits(app: App): void {
  app.prot("POST", "/v1/edits/state", (ctx) => setEditState(app, ctx),
    doc({
      summary: "Set State",
      description: "Modify the state of an edit",
      requestBody: {
        contentType: "application/json",
        fields: {
          edit_id: { type: "integer", required: true },
          expected_state: { required: true },
          new_state: { required: true },
          table_name: {  },
          column_name: {  },
        },
      },
    }),
  );
}

async function setEditState(app: App, ctx: Ctx): Promise<Response> {
  const body = await decodeJsonBody<EditStateBody>(ctx.req);
  const tableName = body.table_name ?? "dicom_edit_compare_disposition";
  const columnName = body.column_name ?? "current_disposition";
  if (!identifierRe.test(tableName) || !identifierRe.test(columnName)) {
    throw new HttpError(
      422,
      "table_name and column_name must be plain identifiers",
    );
  }

  const rows = await app.db.fetch(
    `
    update ${tableName}
    set ${columnName} = $1
    where subprocess_invocation_id = $2
    and ${columnName} = $3
    returning subprocess_invocation_id
    `,
    [body.new_state ?? null, body.edit_id ?? null, body.expected_state ?? null],
  );

  if (rows.length === 0) {
    const current = await app.db.fetchOne(
      `
      select ${columnName}
      from ${tableName}
      where subprocess_invocation_id = $1
      `,
      [body.edit_id ?? null],
    );
    if (!current) {
      throw new HttpError(404, "Not Found");
    }
    return jsonResponse(
      {
        detail: "Column was not in expected state",
        expected_state: body.expected_state ?? null,
        actual_state: Object.values(current)[0],
      },
      409,
    );
  }

  return new Response(null, { status: 200 });
}
