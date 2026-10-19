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

// --- operations ------------------------------------------------------------

export interface Operation {
  operation_name: string;
  command_line: string;
  operation_type: string | null;
  input_line_format: string;
  tags: string[];
  can_chain: boolean;
  outdated: boolean;
  worker_priority: number;
  args: string[];
  meta_args: string[];
  fields: string[];
  program: string | null;
  program_found: boolean | null;
}

export interface Candidate {
  operation: Operation;
  matches: number;
}

export interface Candidates {
  columns: string[];
  row_count: number;
  named_operation: string | null;
  candidates: Candidate[];
}

export type LaunchSource =
  | { type: "workflow"; operation: string; caption?: string; prior_args?: Record<string, string> }
  | { type: "table"; query_run_id: number; filtered: boolean; operation: string; caption?: string }
  | { type: "row"; query_run_id: number; filtered: boolean; row_index: number; operation: string; caption?: string }
  | { type: "compare_timepoints"; activity_id: number; from_timepoint_id: number; to_timepoint_id: number }
  | { type: "spreadsheet"; file_id: number; operation?: string };

export type ArgSource =
  | "from spreadsheet"
  | "from current_settings"
  | "from bindings"
  | "not present"
  | "entered";

export interface ResolvedArg {
  value: string;
  source: ArgSource;
}

export interface LaunchPreview {
  operation: Operation;
  button_name: string;
  args: Record<string, ResolvedArg>;
  expanded_command: string;
  input_line_count: number;
  input_head: string[];
  input_tail: string[];
  spreadsheet_file_id: number | null;
  query_invoked_by_dbif_id: number | null;
}

export interface Launched {
  subprocess_invocation_id: number;
  work_id: number;
  queue_name: string;
  pending_work: number;
  command_line: string;
}

export interface WorkflowOperation {
  action: string;
  caption: string;
  special: string | null;
  defined: boolean;
}

export interface WorkflowCategory {
  id: string;
  name: string;
  description: string;
  note: string | null;
  operations: WorkflowOperation[];
  query_groups: { caption: string; query_list_name: string }[];
  operation_picker: boolean;
}

export interface Uploaded {
  name: string;
  size: number;
  mime_type: string | null;
  file_id: number;
  created: boolean;
  is_spreadsheet: boolean;
}

export interface Sheet {
  columns: string[];
  row_count: number;
  first_row: Record<string, string> | null;
  named_operation: string | null;
}

// --- inbox, background jobs, downloads ------------------------------------

export interface InboxItem {
  user_inbox_content_id: number;
  background_subprocess_report_id: number | null;
  current_status: string | null;
  date_entered: string | null;
  date_dismissed: string | null;
  operation_name: string | null;
  report_name: string | null;
}

export interface InboxOperation {
  operation_type: string | null;
  when_occurred: string | null;
  invoking_user: string | null;
  how_invoked: string | null;
}

export interface InboxItemDetail extends InboxItem {
  file_id: number | null;
  subprocess_invocation_id: number | null;
  command_line: string | null;
  invoking_user: string | null;
  filed_activity_id: number | null;
  text: string | null;
  text_truncated: boolean;
  operations: InboxOperation[];
}

export interface BackgroundJob {
  subprocess_invocation_id: number;
  work_id: number | null;
  background_subprocess_id: number | null;
  activity_id: number | null;
  status: string | null;
  input_file_id: number | null;
  stdout_file_id: number | null;
  stderr_file_id: number | null;
  invoking_user: string | null;
  /** ISO 8601 duration */
  since_invocation: string | null;
  command_line: string | null;
  when_invoked: string | null;
  user_to_notify: string | null;
  node_hostname: string | null;
  background_queue_name: string | null;
}

export interface BackgroundJobs {
  jobs: BackgroundJob[];
  total: number;
  limit: number;
}

export interface DownloadDir {
  name: string;
  modified: string;
  entries: number;
}
