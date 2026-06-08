import { getBackendBaseURL } from "../config";

import type {
  CrawlTaskCreatePayload,
  CrawlTaskDetail,
  CrawlTaskItem,
  CrawlTaskListResponse,
  CrawlTaskResultsResponse,
} from "./types";

async function readErrorDetail(
  response: Response,
  fallback: string,
): Promise<string> {
  try {
    const error = await response.json();
    return (error as { detail?: string }).detail ?? fallback;
  } catch {
    return fallback;
  }
}

const BASE = `${getBackendBaseURL()}/api/data-center/crawler`;

export async function createCrawlTask(
  payload: CrawlTaskCreatePayload,
): Promise<CrawlTaskItem> {
  const response = await fetch(`${BASE}/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(
      await readErrorDetail(response, "Failed to create crawl task"),
    );
  }

  return response.json() as Promise<CrawlTaskItem>;
}

export async function listCrawlTasks(params?: {
  page?: number;
  page_size?: number;
  status?: string;
}): Promise<CrawlTaskListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.page) searchParams.set("page", String(params.page));
  if (params?.page_size) searchParams.set("page_size", String(params.page_size));
  if (params?.status) searchParams.set("status", params.status);

  const query = searchParams.toString();
  const url = `${BASE}/tasks${query ? `?${query}` : ""}`;

  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(
      await readErrorDetail(response, "Failed to list crawl tasks"),
    );
  }

  return response.json() as Promise<CrawlTaskListResponse>;
}

export async function getCrawlTaskDetail(
  taskId: string,
): Promise<CrawlTaskDetail> {
  const response = await fetch(`${BASE}/tasks/${encodeURIComponent(taskId)}`);

  if (!response.ok) {
    throw new Error(
      await readErrorDetail(response, "Failed to load crawl task detail"),
    );
  }

  return response.json() as Promise<CrawlTaskDetail>;
}

export async function getCrawlTaskResults(
  taskId: string,
): Promise<CrawlTaskResultsResponse> {
  const response = await fetch(
    `${BASE}/tasks/${encodeURIComponent(taskId)}/results`,
  );

  if (!response.ok) {
    throw new Error(
      await readErrorDetail(response, "Failed to load crawl results"),
    );
  }

  return response.json() as Promise<CrawlTaskResultsResponse>;
}

// ── Schedule API ────────────────────────────────────────────────

export interface ScheduleItem {
  id: string;
  name: string;
  schedule_type: string;
  interval_seconds: number | null;
  interval_minutes: number | null;
  timezone: string;
  payload: Record<string, unknown>;
  status: "ACTIVE" | "PAUSED";
  last_run_at: string | null;
  next_run_at: string | null;
  created_at: string;
}

export interface ScheduleListResponse {
  items: ScheduleItem[];
  total: number;
}

export async function createSchedule(payload: Record<string, unknown>): Promise<ScheduleItem> {
  const response = await fetch(`${BASE}/schedules`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await readErrorDetail(response, "Failed to create schedule"));
  return response.json() as Promise<ScheduleItem>;
}

export async function listSchedules(): Promise<ScheduleListResponse> {
  const response = await fetch(`${BASE}/schedules`);
  if (!response.ok) throw new Error(await readErrorDetail(response, "Failed to list schedules"));
  return response.json() as Promise<ScheduleListResponse>;
}

export async function pauseSchedule(scheduleId: string): Promise<void> {
  const response = await fetch(`${BASE}/schedules/${scheduleId}/pause`, { method: "POST" });
  if (!response.ok) throw new Error(await readErrorDetail(response, "Failed to pause schedule"));
}

export async function resumeSchedule(scheduleId: string): Promise<void> {
  const response = await fetch(`${BASE}/schedules/${scheduleId}/resume`, { method: "POST" });
  if (!response.ok) throw new Error(await readErrorDetail(response, "Failed to resume schedule"));
}

// ── Model config API ──────────────────────────────────────────────

export interface ModelConfigItem {
  target: string;
  label: string;
  has_api_key: boolean;
  base_url: string | null;
  model_name: string | null;
  is_configured: boolean;
  missing_fields: string[];
}

export interface ModelConfigListResponse {
  items: ModelConfigItem[];
}

export async function listModelConfigs(): Promise<ModelConfigListResponse> {
  const response = await fetch(`${BASE}/model-configs`);
  if (!response.ok) throw new Error(await readErrorDetail(response, "Failed to list model configs"));
  return response.json() as Promise<ModelConfigListResponse>;
}

export async function upsertModelConfig(
  target: string,
  payload: { api_key?: string; base_url: string; model_name: string },
): Promise<ModelConfigItem> {
  const response = await fetch(`${BASE}/model-configs/${target}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await readErrorDetail(response, "Failed to update model config"));
  return response.json() as Promise<ModelConfigItem>;
}

export async function cancelCrawlTask(taskId: string): Promise<void> {
  const response = await fetch(`${BASE}/tasks/${encodeURIComponent(taskId)}/cancel`, { method: "POST" });
  if (!response.ok) throw new Error(await readErrorDetail(response, "Failed to cancel task"));
}

export async function deleteSchedule(scheduleId: string): Promise<void> {
  const response = await fetch(`${BASE}/schedules/${scheduleId}`, { method: "DELETE" });
  if (!response.ok) throw new Error(await readErrorDetail(response, "Failed to delete schedule"));
}
