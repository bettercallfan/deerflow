import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createCrawlTask,
  getCrawlTaskDetail,
  getCrawlTaskResults,
  listCrawlTasks,
} from "./api";

export function useCrawlTasks(params?: {
  page?: number;
  page_size?: number;
  status?: string;
}) {
  return useQuery({
    queryKey: ["crawler", "tasks", params],
    queryFn: () => listCrawlTasks(params),
    refetchOnWindowFocus: false,
    refetchInterval: 5000,
  });
}

export function useCrawlTaskDetail(taskId: string | null | undefined) {
  return useQuery({
    queryKey: ["crawler", "tasks", taskId],
    queryFn: () => getCrawlTaskDetail(taskId!),
    enabled: Boolean(taskId),
    refetchOnWindowFocus: false,
    refetchInterval: taskId ? 5000 : false,
  });
}

export function useCrawlTaskResults(taskId: string | null | undefined) {
  return useQuery({
    queryKey: ["crawler", "tasks", taskId, "results"],
    queryFn: () => getCrawlTaskResults(taskId!),
    enabled: Boolean(taskId),
    refetchOnWindowFocus: false,
    refetchInterval: taskId ? 5000 : false,
  });
}

export function useCreateCrawlTask() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: createCrawlTask,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["crawler", "tasks"] });
    },
  });
}