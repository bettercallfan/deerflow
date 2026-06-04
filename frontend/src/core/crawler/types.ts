export type CrawlTaskStatus =
  | "PENDING"
  | "RUNNING"
  | "SUCCEEDED"
  | "FAILED"
  | "CANCELED"
  | "SKIPPED_NO_CHANGE";

export type OutputMode = "html" | "markdown" | "json";

export interface CrawlTaskCreatePayload {
  name: string;
  portal_url: string;
  query: string;
  output_mode: OutputMode;
}

export interface CrawlTaskItem {
  id: string;
  name: string;
  portal_url: string;
  query: string;
  output_mode: OutputMode;
  status: CrawlTaskStatus;
  progress: number;
  source: string;
  skip_reason: string | null;
  error_message: string | null;
  result_summary: string | null;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface CrawlTaskDetail {
  task: CrawlTaskItem;
  run_stats: Record<string, unknown>;
}

export interface CrawlResultItem {
  page_id: string;
  url: string;
  title: string | null;
  is_duplicate: boolean;
  duplicate_reason: string;
  raw_html_hash: string;
  normalized_content_hash: string;
  result_type: string | null;
  result_json: Record<string, unknown> | unknown[] | null;
  result_markdown: string | null;
  result_markdown_ocr: string | null;
}

export interface CrawlTaskListResponse {
  items: CrawlTaskItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface CrawlTaskResultsResponse {
  items: CrawlResultItem[];
  total: number;
}
