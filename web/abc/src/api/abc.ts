/** Typed calls for the ABC endpoints. Paths double as SWR keys. */

import { API_BASE, api } from "./client";
import type {
  Activity,
  AdminUser,
  FileText,
  LaunchPreview,
  LaunchSource,
  Launched,
  Run,
  RunDetail,
  Uploaded,
} from "./types";

export const paths = {
  me: "/v1/abc/me",
  bindings: "/v1/abc/me/bindings",
  activities: (includeClosed = false) =>
    `/v1/abc/activities?include_closed=${includeClosed}`,
  activity: (id: number) => `/v1/abc/activities/${id}`,
  taskStatus: (id: number) => `/v1/abc/activities/${id}/task-status`,
  timeline: (id: number) => `/v1/abc/activities/${id}/timeline`,
  timepoints: (id: number) => `/v1/abc/activities/${id}/timepoints`,
  fileText: (fileId: number) => `/v1/abc/files/${fileId}/text`,
  queriesRecent: "/v1/abc/queries/recent",
  queriesSearch: (params: Record<string, string>) => {
    const query = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v.trim() !== ""),
    ).toString();
    return query ? `/v1/abc/queries/search?${query}` : null;
  },
  workflowGroups: "/v1/abc/queries/workflow-groups",
  query: (name: string) => `/v1/abc/queries/${encodeURIComponent(name)}`,
  runs: (includeDismissed = false) =>
    `/v1/abc/query-runs?include_dismissed=${includeDismissed}`,
  run: (id: number) => `/v1/abc/query-runs/${id}`,
  runRows: (id: number, first: number, n: number, filtered: boolean) =>
    `/v1/abc/query-runs/${id}/rows?first=${first}&n=${n}&filtered=${filtered}`,
  runCsv: (id: number, filtered: boolean) =>
    `${API_BASE}/v1/abc/query-runs/${id}/csv?filtered=${filtered}`,
  operations: (q = "") => `/v1/abc/operations${q ? `?q=${encodeURIComponent(q)}` : ""}`,
  operation: (name: string) => `/v1/abc/operations/${encodeURIComponent(name)}`,
  candidatesForRun: (runId: number, filtered: boolean) =>
    `/v1/abc/operations/candidates?query_run_id=${runId}&filtered=${filtered}`,
  candidatesForFile: (fileId: number) => `/v1/abc/operations/candidates?file_id=${fileId}`,
  workflowCategories: "/v1/abc/workflow/categories",
  sheet: (fileId: number) => `/v1/abc/uploads/${fileId}/sheet`,
  inbox: (includeDismissed = false) => `/v1/abc/inbox?include_dismissed=${includeDismissed}`,
  inboxUnread: "/v1/abc/inbox/unread-count",
  inboxUsers: "/v1/abc/inbox/users",
  inboxItem: (id: number) => `/v1/abc/inbox/${id}`,
  backgroundJobs: (mode: string, inLast: string) =>
    `/v1/abc/background-jobs?mode=${mode}&in_last=${encodeURIComponent(inLast)}`,
  downloads: "/v1/abc/downloads",
  downloadTar: (name: string) => `${API_BASE}/v1/abc/downloads/${encodeURIComponent(name)}/tar`,
  fileData: (fileId: number) => `${API_BASE}/v1/files/${fileId}/data`,
  adminUsers: "/v1/abc/admin/users",
  adminUser: (name: string) => `/v1/abc/admin/users/${encodeURIComponent(name)}`,
  adminUserPermissions: (name: string) =>
    `/v1/abc/admin/users/${encodeURIComponent(name)}/permissions`,
  adminPermissions: "/v1/abc/admin/permissions",
};

export function login(username: string, password: string): Promise<void> {
  return api.post<void>("/auth/login", { username, password });
}

export function logout(): Promise<void> {
  return api.post<void>("/auth/logout");
}

export function setBinding(name: string, value: string | null): Promise<void> {
  return api.put<void>(`${paths.bindings}/${encodeURIComponent(name)}`, { value });
}

export function createActivity(briefDescription: string): Promise<number> {
  return api
    .post<{ activity_id: number }>("/v1/abc/activities", {
      brief_description: briefDescription,
    })
    .then((created) => created.activity_id);
}

export function setThirdPartyUrl(
  activityId: number,
  url: string | null,
): Promise<void> {
  return api.patch<void>(paths.activity(activityId), {
    third_party_analysis_url: url,
  });
}

export function dismissTaskStatus(
  activityId: number,
  subprocessInvocationId: number,
): Promise<void> {
  return api.post<void>(
    `${paths.taskStatus(activityId)}/${subprocessInvocationId}/dismiss`,
  );
}

export function fetchFileText(fileId: number): Promise<FileText> {
  return api.get<FileText>(paths.fileText(fileId));
}

export type { Activity };

export function startRun(
  queryName: string,
  args: Record<string, string | null>,
): Promise<number> {
  return api
    .post<{ query_run_id: number }>("/v1/abc/query-runs", {
      query_name: queryName,
      args,
    })
    .then((started) => started.query_run_id);
}

export function rerun(runId: number): Promise<number> {
  return api
    .post<{ query_run_id: number }>(`${paths.run(runId)}/rerun`)
    .then((started) => started.query_run_id);
}

export type RunAction = "pause" | "resume" | "abort" | "dismiss";

export function runAction(runId: number, action: RunAction): Promise<Run> {
  return api.post<Run>(`${paths.run(runId)}/${action}`);
}

export function setRunFilter(
  runId: number,
  filter: Record<string, string> | null,
  viewFiltered: boolean,
): Promise<RunDetail> {
  return api.put<RunDetail>(`${paths.run(runId)}/filter`, {
    filter,
    view_filtered: viewFiltered,
  });
}

export function prepareLaunch(source: LaunchSource): Promise<LaunchPreview> {
  return api.post<LaunchPreview>("/v1/abc/operations/prepare", { source });
}

export function launchOperation(
  source: LaunchSource,
  args: Record<string, string>,
): Promise<Launched> {
  return api.post<Launched>("/v1/abc/operations/launch", { source, args });
}

/** Multipart upload; not JSON, so it bypasses the typed client's body handling. */
export async function uploadFiles(files: File[]): Promise<Uploaded[]> {
  const body = new FormData();
  for (const file of files) body.append("files", file, file.name);
  const response = await fetch(`${API_BASE}/v1/abc/uploads`, {
    method: "POST",
    body,
    credentials: "same-origin",
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${response.status}: ${detail || response.statusText}`);
  }
  return (await response.json()) as Uploaded[];
}

export function dismissInboxItem(id: number): Promise<void> {
  return api.post<void>(`${paths.inboxItem(id)}/dismiss`);
}

export function fileInboxItem(id: number, activityId: number): Promise<void> {
  return api.post<void>(`${paths.inboxItem(id)}/file`, { activity_id: activityId });
}

export function forwardInboxItem(id: number, username: string): Promise<void> {
  return api.post<void>(`${paths.inboxItem(id)}/forward`, { username });
}

export function deleteDownload(name: string): Promise<void> {
  return api.delete<void>(`/v1/abc/downloads/${encodeURIComponent(name)}`);
}

export function createImportEvent(comment: string): Promise<number> {
  return api
    .post<{ import_event_id: number }>("/v1/abc/uploads/import-events", { comment })
    .then((r) => r.import_event_id);
}

export function closeImportEvent(id: number): Promise<void> {
  return api.post<void>(`/v1/abc/uploads/import-events/${id}/close`);
}

export async function uploadFilesToEvent(files: File[], importEventId: number): Promise<Uploaded[]> {
  const body = new FormData();
  for (const file of files) body.append("files", file, file.name);
  const response = await fetch(`${API_BASE}/v1/abc/uploads?import_event_id=${importEventId}`, {
    method: "POST",
    body,
    credentials: "same-origin",
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${response.status}: ${detail || response.statusText}`);
  }
  return (await response.json()) as Uploaded[];
}

export function createAdminUser(body: {
  user_name: string;
  full_name: string;
  email: string | null;
  password: string;
}): Promise<AdminUser> {
  return api.post<AdminUser>(paths.adminUsers, body);
}

export function patchAdminUser(
  name: string,
  body: { full_name?: string; email?: string | null; disabled?: boolean; password?: string },
): Promise<AdminUser> {
  return api.patch<AdminUser>(paths.adminUser(name), body);
}

export function deleteAdminUser(name: string): Promise<void> {
  return api.delete<void>(paths.adminUser(name));
}

export function putAdminPermissions(
  name: string,
  granted: Record<string, string[]>,
): Promise<Record<string, Record<string, boolean>>> {
  return api.put(paths.adminUserPermissions(name), { granted });
}
