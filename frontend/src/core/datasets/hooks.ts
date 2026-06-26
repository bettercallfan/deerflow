import { useQuery } from "@tanstack/react-query";

import {
  fetchDatasetRecordDetail,
  fetchDatasetRecords,
  fetchDatasetStats,
} from "./api";
import type { DatasetRecordQuery } from "./types";

export function useDatasetRecords(query: DatasetRecordQuery) {
  return useQuery({
    queryKey: ["datasets", "records", query],
    queryFn: () => fetchDatasetRecords(query),
  });
}

export function useDatasetRecordDetail(recordId: number | null) {
  return useQuery({
    queryKey: ["datasets", "records", recordId],
    queryFn: () => fetchDatasetRecordDetail(recordId as number),
    enabled: recordId !== null,
  });
}

export function useDatasetStats() {
  return useQuery({
    queryKey: ["datasets", "stats"],
    queryFn: fetchDatasetStats,
  });
}
