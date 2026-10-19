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

// --- saved queries ---------------------------------------------------------

export interface QuerySummary {
  name: string;
  args: string[];
  columns: string[];
  schema_name: string;
  tags: string[];
}

export interface QueryLists {
  recent: QuerySummary[];
  frequent: QuerySummary[];
}

export interface ChainedQuery {
  chained_query_id: string;
  caption: string;
  to_query: string;
  /** from column name -> to parameter name */
  arg_map: Record<string, string>;
}

export interface ProcessingButton {
  caption: string;
  operation: string;
}

export interface ColumnButton {
  button_id: string;
  caption: string;
  column: string;
  /** The Perl popup class; only the Mirabelle/Kohlrabi ones become links. */
  obj: string;
  col_to_param: Record<string, string>;
  operation: string | null;
}

export interface QueryDetail extends QuerySummary {
  description: string;
  query: string;
  is_select: boolean;
  runnable: boolean;
  not_runnable_reason: string | null;
  chained_queries: ChainedQuery[];
  processing_buttons: ProcessingButton[];
  column_buttons: ColumnButton[];
}

export interface WorkflowGroupEntry {
  caption: string;
  query_name: string;
  query: QuerySummary | null;
}

export interface WorkflowGroup {
  name: string;
  title: string;
  queries: WorkflowGroupEntry[];
}

// --- query runs ------------------------------------------------------------

export type RunState =
  | "queued"
  | "running"
  | "paused"
  | "done"
  | "ended"
  | "aborted"
  | "error"
  | "lost";

export const ACTIVE_RUN_STATES: RunState[] = ["queued", "running", "paused"];

export interface Run {
  query_run_id: number;
  query_name: string;
  args: Record<string, string | null>;
  caption: string;
  state: RunState;
  requested_action: "pause" | "resume" | "abort" | null;
  is_select: boolean | null;
  row_count: number;
  rows_affected: number | null;
  error_text: string | null;
  filter: Record<string, string> | null;
  view_filtered: boolean;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  dismissed_at: string | null;
  owner: string | null;
}

export interface RunDetail extends Run {
  columns: string[];
  filtered_count: number | null;
}

export type Cell = string | number | boolean | null | Cell[];

export interface RowsPage {
  first: number;
  rows: Cell[][];
  total: number;
  filtered: boolean;
  partial: boolean;
}
