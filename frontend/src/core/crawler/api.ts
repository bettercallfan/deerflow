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
