"use client";

import { useState } from "react";
import {
  GlobeIcon,
  ClockIcon,
  FileTextIcon,
  ChevronDownIcon,
  ChevronRightIcon,
} from "lucide-react";

import { useI18n } from "@/core/i18n/hooks";
import {
  useCrawlTaskDetail,
  useCrawlTaskResults,
  type CrawlTaskItem,
  type CrawlResultItem,
} from "@/core/crawler";
import { cn } from "@/lib/utils";

interface CrawlerTaskDetailProps {
  task: CrawlTaskItem;
}

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "-";
  const normalized = iso.replace(/(\.\d{3})\d+/, "$1");
  const d = new Date(normalized);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function statusBadgeStyle(status: CrawlTaskItem["status"]) {
  if (status === "SUCCEEDED") return "bg-green-100 text-green-700";
  if (status === "RUNNING") return "bg-blue-100 text-blue-700";
  if (status === "FAILED") return "bg-red-100 text-red-700";
  if (status === "CANCELED") return "bg-gray-100 text-gray-500";
  if (status === "SKIPPED_NO_CHANGE") return "bg-yellow-100 text-yellow-700";
  return "bg-muted text-muted-foreground";
}

function labelOfMode(mode: string) {
  if (mode === "html") return "HTML";
  if (mode === "markdown") return "Markdown";
  if (mode === "json") return "JSON";
  return mode;
}

export function CrawlerTaskDetail({ task }: CrawlerTaskDetailProps) {
  const { t } = useI18n();
  const { data: detail, isLoading: detailLoading } = useCrawlTaskDetail(task.id);
  const { data: resultsData, isLoading: resultsLoading } = useCrawlTaskResults(task.id);

  const taskData = detail?.task ?? task;
  const results = resultsData?.items ?? [];

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Task Info Header */}
      <div className="shrink-0 border-b px-6 py-5">
        <h2
          className="max-w-full break-all text-lg font-semibold"
          title={taskData.name}
        >
          {taskData.name}
        </h2>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span
            className={cn(
              "rounded-full px-3 py-1 text-xs",
              statusBadgeStyle(taskData.status),
            )}
          >
            {t.dataCenter.crawler.status[taskData.status] ?? taskData.status}
          </span>
          <span className="bg-muted rounded-full px-3 py-1 text-xs">
            {labelOfMode(taskData.output_mode)}
          </span>
          {taskData.status === "RUNNING" && (
            <span className="bg-muted rounded-full px-3 py-1 text-xs">
              {taskData.progress}%
            </span>
          )}
        </div>

        {taskData.status === "RUNNING" && (
          <div className="bg-muted mt-3 h-1.5 w-full rounded-full">
            <div
              className="bg-primary h-1.5 rounded-full transition-all"
              style={{ width: `${taskData.progress}%` }}
            />
          </div>
        )}

        <div className="text-muted-foreground mt-3 space-y-1 text-xs">
          <div className="flex items-center gap-2">
            <GlobeIcon className="size-3" />
            <span className="line-clamp-1 break-all">{taskData.portal_url}</span>
          </div>
          {taskData.created_at && (
            <div className="flex items-center gap-2">
              <ClockIcon className="size-3" />
              <span>
                创建：{formatDateTime(taskData.created_at)}
                {taskData.finished_at && `  |  完成：${formatDateTime(taskData.finished_at)}`}
              </span>
            </div>
          )}
        </div>

        {taskData.error_message && (
          <div className="mt-3 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
            {taskData.error_message}
          </div>
        )}
      </div>

      {/* Results */}
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="shrink-0 flex items-center gap-2 border-b px-6 py-3">
          <FileTextIcon className="size-4" />
          <span className="text-sm font-medium">
            {t.dataCenter.crawler.crawlResults}
          </span>
          <span className="text-muted-foreground text-xs">
            ({results.length} 条)
          </span>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {resultsLoading || detailLoading ? (
            <div className="text-muted-foreground px-6 py-8 text-center text-sm">
              加载中...
            </div>
          ) : results.length === 0 ? (
            <div className="text-muted-foreground px-6 py-12 text-center text-sm">
              {taskData.status === "RUNNING"
                ? "任务运行中，结果将在完成后显示..."
                : t.dataCenter.crawler.noResults}
            </div>
          ) : (
            <div className="space-y-1 p-3">
              {results.map((item) => (
                <CrawlResultCard key={item.page_id} item={item} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function CrawlResultCard({ item }: { item: CrawlResultItem }) {
  const [expanded, setExpanded] = useState(false);

  const content =
    item.result_markdown ??
    item.result_markdown_ocr ??
    (item.result_json
      ? JSON.stringify(item.result_json, null, 2)
      : null);

  return (
    <div className="rounded-2xl border bg-white/80">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-start gap-3 px-4 py-3 text-left"
      >
        <div className="mt-0.5">
          {expanded ? (
            <ChevronDownIcon className="text-muted-foreground size-4" />
          ) : (
            <ChevronRightIcon className="text-muted-foreground size-4" />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="line-clamp-1 text-sm font-medium break-all" title={item.title ?? item.url}>
            {item.title || item.url}
          </div>
          <div className="text-muted-foreground mt-0.5 line-clamp-1 text-xs break-all">
            {item.url}
          </div>
          <div className="mt-1 flex items-center gap-2">
            <span className="bg-muted rounded-full px-2 py-0.5 text-[10px]">
              {item.result_type ?? "unknown"}
            </span>
            {item.is_duplicate && (
              <span className="bg-yellow-100 text-yellow-700 rounded-full px-2 py-0.5 text-[10px]">
                重复
              </span>
            )}
          </div>
          {!expanded && content && (
            <div className="text-muted-foreground mt-2 line-clamp-3 text-xs break-all">
              {content.slice(0, 300)}
            </div>
          )}
        </div>
      </button>

      {expanded && content && (
        <div className="border-t px-4 py-3">
          <pre className="max-h-96 overflow-y-auto whitespace-pre-wrap break-words text-xs leading-5 text-zinc-800">
            {content}
          </pre>
        </div>
      )}
    </div>
  );
}
