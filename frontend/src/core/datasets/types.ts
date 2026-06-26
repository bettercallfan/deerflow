export type DatasetResultType = "markdown" | "json" | "html" | string;

export interface DatasetRecordListItem {
  id: number;
  task_id: string | null;
  page_url: string | null;
  title: string | null;
  raw_html_hash: string | null;
  normalized_content_hash: string | null;
  result_type: DatasetResultType | null;
  content_preview: string | null;
  created_at: string | null;
}

export interface DatasetRecordDetail extends DatasetRecordListItem {
  result_json: unknown | null;
  result_markdown: string | null;
  result_html: string | null;
}

export interface DatasetRecordListResponse {
  items: DatasetRecordListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface DatasetStats {
  total_records: number;
  markdown_count: number;
  json_count: number;
  html_count: number;
  task_count: number;
  latest_created_at: string | null;
}

export interface DatasetRecordQuery {
  page?: number;
  page_size?: number;
  keyword?: string;
  result_type?: string;
}
