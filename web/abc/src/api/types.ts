/** Response shapes of /papi/v1/abc (see posda/fastapi/app/papi/routes/abc). */

export interface Me {
  username: string;
  full_name: string | null;
  permissions: Record<string, string[]>;
  launchable_apps: string[];
}

export type Bindings = Record<string, string | null>;

export interface Activity {
  activity_id: number;
  brief_description: string;
  when_created: string;
  who_created: string;
  when_closed: string | null;
  third_party_analysis_url: string | null;
}

export interface TaskStatus {
  subprocess_invocation_id: number;
  operation_name: string | null;
  start_time: string;
  last_updated: string | null;
  status_text: string | null;
  /** ISO 8601 duration, e.g. "PT5M". */
  expected_remaining_time: string | null;
  end_time: string | null;
  since_update: string | null;
  stale_warning: string | null;
}

export interface Timepoint {
  activity_timepoint_id: number;
  when_created: string;
  comment: string | null;
  creating_user: string | null;
  file_count: number;
}

export interface TimelineEvent {
  inbox_content_id: number;
  subprocess_invocation_id: number;
  operation_name: string | null;
  user_name: string;
  started: string;
  ended: string | null;
  /** ISO 8601 duration, e.g. "PT1M0.03S". */
  duration: string | null;
  command_line: string | null;
  email_file_id: number | null;
  spreadsheet_file_id: number | null;
  timepoint_id: number | null;
  timepoint_file_count: number | null;
  overlap_count: number;
}

export interface FileText {
  file_id: number;
  text: string;
  truncated: boolean;
  size: number;
}
