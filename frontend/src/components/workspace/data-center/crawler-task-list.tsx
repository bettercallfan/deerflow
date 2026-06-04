"use client";

import { GlobeIcon, Loader2Icon } from "lucide-react";

import { useI18n } from "@/core/i18n/hooks";
import type { CrawlTaskItem } from "@/core/crawler";
import { cn } from "@/lib/utils";

interface CrawlerTaskCardListProps {
  tasks: CrawlTaskItem[];
  isLoading: boolean;
  error: Error | null;
  selectedTaskId: string | null;
  onSelectTask: (task: CrawlTaskItem) => void;
  t: ReturnType<typeof useI18n>["t"];
}

function statusBadgeStyle(status: CrawlTaskItem["status"]) {
  if (status === "SUCCEEDED") return "bg-green-100 text-green-700";
  if (status === "RUNNING") return "bg-blue-100 text-blue-700";
  if (status === "FAILED") return "bg-red-100 text-red-700";
  if (status === "CANCELED") return "bg-gray-100 text-gray-500";
  if (status === "SKIPPED_NO_CHANGE") return "bg-yellow-100 text-yellow-700";
  return "bg-muted text-muted-foreground";
}

function formatTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const normalized = iso.replace(/(\.\d{3})\d+/, "$1");
  const d = new Date(normalized);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export function CrawlerTaskCardList({
  tasks,
  isLoading,
  error,
  selectedTaskId,
  onSelectTask,
  t,
}: CrawlerTaskCardListProps) {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
      <div className="space-y-2 p-4 pb-20">
        {error && (
          <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-4 text-sm text-red-700">
            {error instanceof Error ? error.message : "Failed to load tasks"}
          </div>
        )}

        {isLoading && (
          <div className="text-muted-foreground rounded-2xl border px-4 py-6 text-center text-sm">
            {t.common.loading}
          </div>
        )}

        {!isLoading && !error && tasks.length === 0 && (
          <div className="text-muted-foreground rounded-2xl border px-4 py-6 text-center text-sm">
            暂无爬取任务
          </div>
        )}

        {tasks.map((task) => {
          const selected = selectedTaskId === task.id;
          return (
            <button
              key={task.id}
              type="button"
              onClick={() => onSelectTask(task)}
              className={cn(
                "w-full rounded-2xl border px-4 py-4 text-left transition",
                selected
                  ? "border-primary/40 bg-primary/5 shadow-sm"
                  : "hover:bg-muted/60 bg-background",
              )}
            >
              <div className="flex items-start gap-3">
                <div className="bg-muted mt-0.5 rounded-xl p-2">
                  <GlobeIcon className="size-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <div
                      className="min-w-0 flex-1 truncate text-sm font-medium"
                      title={task.name}
                    >
                      {task.name}
                    </div>
                    <span
                      className={cn(
                        "shrink-0 rounded-full px-2 py-0.5 text-[11px]",
                        statusBadgeStyle(task.status),
                      )}
                    >
                      {t.dataCenter.crawler.status[task.status] ?? task.status}
                    </span>
                  </div>

                  <p
                    className="text-muted-foreground mt-1 line-clamp-1 text-xs break-all"
                    title={task.portal_url}
                  >
                    {task.portal_url}
                  </p>

                  {task.status === "RUNNING" && (
                    <>
                      <div className="bg-muted mt-2 h-1.5 w-full rounded-full">
                        <div
                          className="bg-primary h-1.5 rounded-full transition-all"
                          style={{ width: `${task.progress}%` }}
                        />
                      </div>
                      <div className="text-muted-foreground mt-1 flex items-center gap-1 text-[11px]">
                        <Loader2Icon className="size-3 animate-spin" />
                        {task.progress}%
                      </div>
                    </>
                  )}

                  <div className="text-muted-foreground mt-2 text-[11px]">
                    {formatTime(task.created_at)}
                  </div>
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
