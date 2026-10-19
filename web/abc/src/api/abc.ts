/** Typed calls for the ABC endpoints. Paths double as SWR keys. */

import { API_BASE, api } from "./client";
import type { Activity, FileText, Run, RunDetail } from "./types";

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
