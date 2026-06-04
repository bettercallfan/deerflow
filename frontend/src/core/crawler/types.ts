export type CrawlTaskStatus =
  | "PENDING"
  | "RUNNING"
  | "SUCCEEDED"
  | "FAILED"
  | "CANCELED"
  | "SKIPPED_NO_CHANGE";

export type OutputMode = "html" | "markdown" | "json";

/**
 * 后端 storage_db_type 语义：
 * - null / undefined：使用本地文件输出，默认保存到 crawler-backend outputs 目录
 * - mysql：写入已配置的 MySQL 存储
 * - milvus：写入已配置的 Milvus 向量库
 */
export type StorageDbType = "mysql" | "milvus";

/**
 * 前端表单展示用：
 * - local：本地文件
 * - mysql：MySQL
 * - milvus：Milvus
 *
 * 提交给后端时：
 * - local -> storage_db_type: null
 * - mysql -> storage_db_type: "mysql"
 * - milvus -> storage_db_type: "milvus"
 */
export type StorageTarget = "local" | StorageDbType;

export interface CrawlTaskCreatePayload {
  name: string;
  portal_url: string;
  query: string;
  output_mode: OutputMode;
  storage_db_type?: StorageDbType | null;
  json_schema?: Record<string, unknown> | unknown[] | null;
}

export interface CrawlTaskItem {
  id: string;
  name: string;
  portal_url: string;
  query: string;
  output_mode: OutputMode;
  storage_db_type?: StorageDbType | null;
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