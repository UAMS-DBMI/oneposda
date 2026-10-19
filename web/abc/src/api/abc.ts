/** Typed calls for the ABC endpoints. Paths double as SWR keys. */

import { api } from "./client";
import type { Activity, FileText } from "./types";

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
