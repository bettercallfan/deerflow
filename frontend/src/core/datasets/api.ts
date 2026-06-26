import { getBackendBaseURL } from "../config";

import type {
  DatasetRecordDetail,
  DatasetRecordListResponse,
  DatasetRecordQuery,
  DatasetStats,
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

const BASE = `${getBackendBaseURL()}/api/data-center/datasets`;

function buildQuery(params: Record<string, string | number | undefined>) {
  const searchParams = new URLSearchParams();

  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      searchParams.set(key, String(value));
    }
  });

  const query = searchParams.toString();
  return query ? `?${query}` : "";
}

export async function fetchDatasetRecords(
  query: DatasetRecordQuery,
): Promise<DatasetRecordListResponse> {
  const url = `${BASE}/records${buildQuery(query)}`;
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(
      await readErrorDetail(response, "Failed to fetch dataset records"),
    );
  }

  return response.json() as Promise<DatasetRecordListResponse>;
}

export async function fetchDatasetRecordDetail(
  recordId: number,
): Promise<DatasetRecordDetail> {
  const response = await fetch(`${BASE}/records/${recordId}`);

  if (!response.ok) {
    throw new Error(
      await readErrorDetail(response, "Failed to fetch dataset record detail"),
    );
  }

  return response.json() as Promise<DatasetRecordDetail>;
}

export async function fetchDatasetStats(): Promise<DatasetStats> {
  const response = await fetch(`${BASE}/stats`);

  if (!response.ok) {
    throw new Error(
      await readErrorDetail(response, "Failed to fetch dataset stats"),
    );
  }

  return response.json() as Promise<DatasetStats>;
}
