"use client";

import { useMemo, useState } from "react";
import {
  BotIcon,
  ClockIcon,
  FileTextIcon,
  PlayIcon,
  RefreshCwIcon,
  TimerIcon,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  useCreateCrawlTask,
  useCrawlTaskResults,
  type CrawlTaskItem,
  type OutputMode,
} from "@/core/crawler";
import { cn } from "@/lib/utils";

interface CrawlerWorkbenchProps {
  selectedTask: CrawlTaskItem | null;
  onSelectTask: (task: CrawlTaskItem | null) => void;
  onRefresh: () => void;
}

type CrawlMode = "manual" | "schedule";

function formatDateTime(value?: string | null) {
  if (!value) return "-";
  const normalized = value.replace(/(\.\d{3})\d+/, "$1");
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return value;

  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function getStatusText(status?: CrawlTaskItem["status"]) {
  if (!status) return "-";

  const map: Record<CrawlTaskItem["status"], string> = {
    PENDING: "等待中",
    RUNNING: "运行中",
    SUCCEEDED: "已完成",
    FAILED: "失败",
    CANCELED: "已取消",
    SKIPPED_NO_CHANGE: "无变化跳过",
  };

  return map[status] ?? status;
}

function getStatusClassName(status?: CrawlTaskItem["status"]) {
  if (status === "SUCCEEDED") return "border-green-200 bg-green-50 text-green-700";
  if (status === "RUNNING") return "border-blue-200 bg-blue-50 text-blue-700";
  if (status === "FAILED") return "border-red-200 bg-red-50 text-red-700";
  if (status === "CANCELED") return "border-gray-200 bg-gray-50 text-gray-500";
  if (status === "SKIPPED_NO_CHANGE") return "border-yellow-200 bg-yellow-50 text-yellow-700";
  return "border-border bg-muted text-muted-foreground";
}

function ModelCard({
  title,
  description,
  modelName,
}: {
  title: string;
  description: string;
  modelName: string;
}) {
  return (
    <div className="rounded-2xl border bg-background p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="rounded-xl bg-primary/10 p-2 text-primary">
            <BotIcon className="size-4" />
          </div>
          <div>
            <div className="font-medium">{title}</div>
            <div className="mt-1 text-xs text-muted-foreground">
              {description}
            </div>
          </div>
        </div>

        <span className="shrink-0 rounded-full border border-green-200 bg-green-50 px-2 py-0.5 text-xs text-green-700">
          已配置
        </span>
      </div>

      <div className="mt-4 space-y-2 text-xs">
        <div className="flex items-center justify-between gap-3">
          <span className="text-muted-foreground">当前模型</span>
          <span className="truncate font-medium">{modelName}</span>
        </div>
        <div className="flex items-center justify-between gap-3">
          <span className="text-muted-foreground">Base URL</span>
          <span className="truncate">dashscope.aliyuncs.com</span>
        </div>
      </div>

      <Button
        type="button"
        variant="outline"
        size="sm"
        className="mt-4 w-full"
        onClick={() => toast.info("模型配置接口接入 Gateway 后可在这里编辑保存")}
      >
        编辑配置
      </Button>
    </div>
  );
}

function ResultPreview({ selectedTask }: { selectedTask: CrawlTaskItem | null }) {
  const resultsQuery = useCrawlTaskResults(selectedTask?.id);
  const results = resultsQuery.data?.items ?? [];

  return (
    <div className="rounded-2xl border bg-background p-5 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 font-medium">
          <FileTextIcon className="size-4" />
          结果预览
        </div>
        <span className="text-xs text-muted-foreground">
          {selectedTask ? `${results.length} 条结果` : "暂无任务"}
        </span>
      </div>

      {!selectedTask ? (
        <div className="mt-4 rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
          创建或选择任务后，将在这里展示最近的爬取结果摘要。
        </div>
      ) : (
        <>
          <div className="mt-4 grid grid-cols-3 gap-3">
            <div className="rounded-xl border p-3">
              <div className="text-xs text-muted-foreground">任务状态</div>
              <div className="mt-1 text-sm font-medium">
                {getStatusText(selectedTask.status)}
              </div>
            </div>
            <div className="rounded-xl border p-3">
              <div className="text-xs text-muted-foreground">任务进度</div>
              <div className="mt-1 text-sm font-medium">
                {selectedTask.progress ?? 0}%
              </div>
            </div>
            <div className="rounded-xl border p-3">
              <div className="text-xs text-muted-foreground">结果数量</div>
              <div className="mt-1 text-sm font-medium">{results.length}</div>
            </div>
          </div>

          <div className="mt-4 space-y-3">
            {results.length === 0 ? (
              <div className="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">
                暂无结果。任务完成后会在这里展示页面摘要。
              </div>
            ) : (
              results.slice(0, 3).map((result, index) => {
                const summary =
                  result.result_markdown ||
                  result.result_markdown_ocr ||
                  JSON.stringify(result.result_json ?? {}, null, 2);

                return (
                  <div key={result.page_id || index} className="rounded-xl border p-4">
                    <div className="truncate text-sm font-medium">
                      {result.title || `结果 ${index + 1}`}
                    </div>
                    <div className="mt-1 truncate text-xs text-muted-foreground">
                      {result.url}
                    </div>
                    <div className="mt-3 line-clamp-3 text-xs leading-5 text-muted-foreground">
                      {summary || "暂无摘要"}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </>
      )}
    </div>
  );
}

function CurrentTaskSidePanel({
  selectedTask,
  onRefresh,
}: {
  selectedTask: CrawlTaskItem | null;
  onRefresh: () => void;
}) {
  return (
    <aside className="flex h-full min-h-0 w-[320px] shrink-0 flex-col overflow-hidden border-l bg-background/60">
      <div className="shrink-0 border-b px-5 py-5">
        <div className="font-medium">当前任务详情</div>
        <div className="mt-1 text-xs text-muted-foreground">
          查看选中任务的运行状态、参数和快捷操作。
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-5">
        {!selectedTask ? (
          <div className="rounded-2xl border border-dashed p-6 text-center text-sm text-muted-foreground">
            左侧选择任务后，这里会展示任务详情。
          </div>
        ) : (
          <div className="space-y-5">
            <div>
              <div className="break-all text-base font-semibold">
                {selectedTask.name}
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                <span
                  className={cn(
                    "rounded-full border px-2 py-0.5 text-xs",
                    getStatusClassName(selectedTask.status),
                  )}
                >
                  {getStatusText(selectedTask.status)}
                </span>
                <span className="rounded-full border bg-muted px-2 py-0.5 text-xs">
                  {selectedTask.output_mode.toUpperCase()}
                </span>
              </div>
            </div>

            <div className="space-y-4 text-sm">
              <div>
                <div className="text-xs text-muted-foreground">目标 URL</div>
                <div className="mt-1 break-all">{selectedTask.portal_url}</div>
              </div>

              <div>
                <div className="text-xs text-muted-foreground">自然语言需求</div>
                <div className="mt-1 rounded-xl bg-muted p-3 text-xs leading-5">
                  {selectedTask.query}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-xl border p-3">
                  <div className="text-xs text-muted-foreground">进度</div>
                  <div className="mt-1 font-medium">{selectedTask.progress ?? 0}%</div>
                </div>
                <div className="rounded-xl border p-3">
                  <div className="text-xs text-muted-foreground">来源</div>
                  <div className="mt-1 truncate font-medium">
                    {selectedTask.source || "手动"}
                  </div>
                </div>
              </div>

              <div>
                <div className="text-xs text-muted-foreground">创建时间</div>
                <div className="mt-1">{formatDateTime(selectedTask.created_at)}</div>
              </div>

              <div>
                <div className="text-xs text-muted-foreground">完成时间</div>
                <div className="mt-1">{formatDateTime(selectedTask.finished_at)}</div>
              </div>
            </div>

            {selectedTask.error_message && (
              <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
                <div className="font-medium">错误信息</div>
                <div className="mt-2 text-xs leading-5">
                  {selectedTask.error_message}
                </div>
              </div>
            )}

            <div className="space-y-2">
              <Button className="w-full" variant="outline" onClick={onRefresh}>
                <RefreshCwIcon className="mr-2 size-4" />
                刷新任务
              </Button>
              <Button className="w-full" variant="outline" disabled>
                取消任务
              </Button>
              <Button className="w-full" variant="outline" disabled>
                重新运行
              </Button>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}

export function CrawlerWorkbench({
  selectedTask,
  onSelectTask,
  onRefresh,
}: CrawlerWorkbenchProps) {
  const createTask = useCreateCrawlTask();

  const [mode, setMode] = useState<CrawlMode>("manual");
  const [name, setName] = useState("");
  const [portalUrl, setPortalUrl] = useState("");
  const [query, setQuery] = useState("");
  const [outputMode, setOutputMode] = useState<OutputMode>("html");

  const [scheduleFrequency, setScheduleFrequency] = useState("daily");
  const [scheduleTime, setScheduleTime] = useState("09:00");
  const [scheduleEnabled, setScheduleEnabled] = useState(true);

  const canSubmit = useMemo(() => {
    return Boolean(name.trim() && portalUrl.trim() && query.trim());
  }, [name, portalUrl, query]);

  const handleCreateTask = async () => {
    if (!canSubmit) return;

    if (mode === "schedule") {
      toast.info("定时爬取接口接入 Gateway 后，可在这里创建调度任务");
      return;
    }

    try {
      const task = await createTask.mutateAsync({
        name: name.trim(),
        portal_url: portalUrl.trim(),
        query: query.trim(),
        output_mode: outputMode,
      });

      toast.success("爬取任务已创建");
      setName("");
      setPortalUrl("");
      setQuery("");
      setOutputMode("html");

      onSelectTask(task);
      onRefresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "创建爬取任务失败");
    }
  };

  return (
    <div className="flex h-full min-h-0">
      <div className="min-w-0 flex-1 overflow-y-auto bg-muted/20 p-6">
        <div className="mx-auto max-w-5xl space-y-5">
          <div className="grid grid-cols-1 gap-4 2xl:grid-cols-2">
            <ModelCard
              title="Agent 导航模型"
              description="负责根据自然语言需求进行网页导航和页面探索。"
              modelName="qwen3.5-35b-a3b"
            />
            <ModelCard
              title="单页面信息抽取模型"
              description="负责对单个页面进行结构化内容提取。"
              modelName="qwen-plus"
            />
          </div>

          <div className="rounded-2xl border bg-background p-5 shadow-sm">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-lg font-semibold">网页智能化爬取</div>
                <div className="mt-1 text-sm text-muted-foreground">
                  输入目标 URL 和自然语言需求，由 Crawler Agent 自动完成网页探索、内容提取和结果保存。
                </div>
              </div>

              <div className="inline-flex rounded-xl bg-muted p-1">
                <button
                  type="button"
                  onClick={() => setMode("manual")}
                  className={cn(
                    "rounded-lg px-3 py-1.5 text-sm transition",
                    mode === "manual"
                      ? "bg-background shadow-sm"
                      : "text-muted-foreground",
                  )}
                >
                  <PlayIcon className="mr-1 inline size-3.5" />
                  手动爬取
                </button>
                <button
                  type="button"
                  onClick={() => setMode("schedule")}
                  className={cn(
                    "rounded-lg px-3 py-1.5 text-sm transition",
                    mode === "schedule"
                      ? "bg-background shadow-sm"
                      : "text-muted-foreground",
                  )}
                >
                  <TimerIcon className="mr-1 inline size-3.5" />
                  定时爬取
                </button>
              </div>
            </div>

            <div className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-2">
              <div className="space-y-2">
                <label className="text-sm font-medium">
                  {mode === "manual" ? "任务名称" : "调度名称"}
                </label>
                <Input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder={mode === "manual" ? "例如：政策网页采集" : "例如：政策网站每日更新采集"}
                />
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">目标 URL</label>
                <Input
                  value={portalUrl}
                  onChange={(event) => setPortalUrl(event.target.value)}
                  placeholder="https://example.com"
                />
              </div>

              <div className="space-y-2 lg:col-span-2">
                <label className="text-sm font-medium">自然语言需求</label>
                <Textarea
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="例如：提取页面中的政策标题、发布时间和正文"
                  rows={4}
                />
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">输出模式</label>
                <Select
                  value={outputMode}
                  onValueChange={(value) => setOutputMode(value as OutputMode)}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="html">HTML</SelectItem>
                    <SelectItem value="markdown">Markdown</SelectItem>
                    <SelectItem value="json">JSON</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {mode === "schedule" && (
                <>
                  <div className="space-y-2">
                    <label className="text-sm font-medium">执行频率</label>
                    <Select
                      value={scheduleFrequency}
                      onValueChange={setScheduleFrequency}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="daily">每天</SelectItem>
                        <SelectItem value="weekly">每周</SelectItem>
                        <SelectItem value="cron">Cron 表达式</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <label className="text-sm font-medium">执行时间</label>
                    <Input
                      value={scheduleTime}
                      onChange={(event) => setScheduleTime(event.target.value)}
                      placeholder="09:00"
                    />
                  </div>

                  <div className="flex items-end">
                    <button
                      type="button"
                      onClick={() => setScheduleEnabled((value) => !value)}
                      className={cn(
                        "rounded-md border px-3 py-2 text-sm",
                        scheduleEnabled
                          ? "border-green-200 bg-green-50 text-green-700"
                          : "bg-muted text-muted-foreground",
                      )}
                    >
                      {scheduleEnabled ? "已启用" : "已停用"}
                    </button>
                  </div>
                </>
              )}
            </div>

            <div className="mt-5 flex items-center justify-end gap-3">
              {mode === "schedule" && (
                <div className="mr-auto flex items-center gap-2 text-xs text-muted-foreground">
                  <ClockIcon className="size-3.5" />
                  定时爬取接口接入后将创建调度任务。
                </div>
              )}

              <Button
                type="button"
                onClick={() => void handleCreateTask()}
                disabled={!canSubmit || createTask.isPending}
              >
                {createTask.isPending
                  ? "创建中..."
                  : mode === "manual"
                    ? "创建并执行任务"
                    : "创建定时任务"}
              </Button>
            </div>
          </div>

          <ResultPreview selectedTask={selectedTask} />
        </div>
      </div>

      <CurrentTaskSidePanel selectedTask={selectedTask} onRefresh={onRefresh} />
    </div>
  );
}