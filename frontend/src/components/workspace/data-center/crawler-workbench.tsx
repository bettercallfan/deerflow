"use client";

import { useMemo, useState } from "react";
import {
  BotIcon,
  ClockIcon,
  DownloadIcon,
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
  createSchedule,
  cancelCrawlTask,
  listModelConfigs,
  listSchedules,
  pauseSchedule,
  resumeSchedule,
  deleteSchedule,
  type CrawlTaskItem,
  type ModelConfigItem,
  type OutputMode,
  type ScheduleItem,
} from "@/core/crawler";
import { ModelConfigDialog } from "./model-config-dialog";
import { cn } from "@/lib/utils";

interface CrawlerWorkbenchProps {
  selectedTask: CrawlTaskItem | null;
  onSelectTask: (task: CrawlTaskItem | null) => void;
  onRefresh: () => void;
}

type WorkMode = "manual" | "schedule";
type CrawlMode = "general" | "policy_regulation" | "code_snippet" | "video_surveillance";

const POLICY_REGULATION_SCHEMA = {
  type: "object",
  required: ["items"],
  properties: {
    items: {
      type: "array",
      description:
        "从网页中抽取的法条列表。每一条对应一个独立法条。如果页面是法律全文页，必须逐条拆分。注意：章节标题（第X章、第X节）出现在该章节第一条之前，必须把每个法条所属的编/章/节信息填入 metadata 的对应字段。不要因为章节标题不是法条就忽略它。",
      items: {
        type: "object",
        required: ["law_name", "content"],
        properties: {
          // ── 基本信息（必须填写）──
          law_name: {
            type: "string",
            description:
              "法律文件全称，例如 中华人民共和国宪法修正案（2018年）、中华人民共和国个人信息保护法。同一条法律的多个法条必须使用相同的 law_name。",
          },
          title: {
            type: "string",
            description:
              "法条标题，格式: {law_name} {article_no}，例如 中华人民共和国宪法修正案（2018年） 第三十二条。",
          },
          article_no: {
            type: "string",
            description:
              "法条编号，例如 第一条、第三十二条、第1条。必须从页面原文提取，不要编造。如果该条无序号，填写整个法律的名称作为兜底。",
          },
          article_number: {
            type: "integer",
            description:
              "法条数字编号，例如 32。用于排序。如果 article_no 无法转换为数字，填 0。",
          },

          // ── 发布机关（同一条法律所有法条共用）──
          office: {
            type: "string",
            description:
              "发布机关全称，例如 全国人民代表大会、国务院、武汉市人民代表大会常务委员会。",
          },
          office_level: {
            type: "string",
            description:
              "机关层级，例如 全国人民代表大会、国务院、部委、省级、市级。",
          },
          office_category: {
            type: "string",
            description:
              "机关类别，例如 人民代表大会、行政机关、司法机关。",
          },

          // ── 时效性（同一条法律所有法条共用）──
          publish_date: {
            type: "string",
            description:
              "发布日期，格式 YYYY-MM-DD。如果页面只显示年份，填 YYYY-01-01。",
          },
          effective_date: {
            type: "string",
            description:
              "生效日期，格式 YYYY-MM-DD。如果页面未明确给出，填 null。",
          },
          effective_period: {
            type: ["string", "null"],
            description:
              "生效时间段，格式 起始年份_结束年份，例如 2000_2020。仅在页面明确标注时填写，否则 null。",
          },
          validity_status: {
            type: "string",
            description:
              "效力状态：有效、已废止、已修改、尚未生效、部分失效。如果 effective_date 早于今天且页面未标注废止/修改，填 有效。",
          },

          // ── 内容（核心字段）──
          content: {
            type: "string",
            description:
              "当前法条的完整正文。只包含本条内容，不要包含其他条的文本。如果有标题、标点，保留。",
          },
          page_content: {
            type: "string",
            description:
              "检索用文本，由 law_name + article_no + content 拼接而成。格式: {law_name}\\n{article_no} {content}。",
          },
          category: {
            type: "string",
            description:
              "法律类型：宪法、法律、行政法规、地方性法规、部门规章、司法解释、政策文件。根据页面内容或法律名称判断。",
          },

          // ── 标识（由系统组合生成，LLM 尽量填）──
          id: {
            type: "string",
            description:
              "唯一标识，格式 0::{law_name}::{article_no}，例如 0::中华人民共和国宪法修正案（2018年）::第三十二条。",
          },

          // ── 后处理字段（当前阶段填 null 或空值即可）──
          source_path: { type: ["string", "null"], description: "后处理字段，填 null。" },
          source_article_index: { type: ["integer", "null"], description: "后处理字段，填 null。" },
          _embedding_dimensions: { type: ["integer", "null"], description: "后处理字段，填 null。" },
          _embedding_model: { type: ["string", "null"], description: "后处理字段，填 null。" },
          _embedding_text_field: { type: ["string", "null"], description: "后处理字段，填 null。" },
          "vector-text-embedding-v4": {
            type: "array",
            description: "后处理字段，填 []。",
            items: { type: "number" },
          },
          metadata: {
            type: "object",
            description: "完整元数据字典，严格按此结构填写。",
            properties: {
              publish_date: { type: "string", description: "发布日期，与顶层一致。" },
              effective_date: { type: "string", description: "生效日期，与顶层一致。" },
              type: { type: "string", description: "类型，同顶层 category。" },
              status: { type: "string", description: "状态，同顶层 validity_status。" },
              title: { type: "string", description: "标题，同顶层 law_name。" },
              office: { type: "string", description: "发布机关，同顶层。" },
              office_level: { type: "string", description: "机关层级，同顶层。" },
              office_category: { type: "string", description: "机关类别，同顶层。" },
              effective_period: { type: "string", description: "生效时间段，同顶层。" },
              source_row_id: { type: "integer", description: "源行号，填 0。" },
              article_index: { type: "integer", description: "法条序号，从 1 开始。" },
              part_label: { type: "string", description: "编编号，从页面原文提取如 第一编。整个页面都找不到编级结构时填 ''。" },
              part_title: { type: "string", description: "编标题，从页面原文提取如 总则。无则 ''。" },
              part_number: { type: "string", description: "编数字编号，从 part_label 提取数字如 1。无则 ''。" },
              subpart_label: { type: "string", description: "分编编号，从页面原文提取。无则 ''。" },
              subpart_title: { type: "string", description: "分编标题，从页面原文提取。无则 ''。" },
              subpart_number: { type: "string", description: "分编数字编号。无则 ''。" },
              chapter_label: { type: "string", description: "章编号，从页面原文提取如 第一章。必须查找页面中出现的\\\"第X章\\\"标记，不要填 ''，除非确认页面完全没有章结构。" },
              chapter_title: { type: "string", description: "章标题，从页面原文提取如 总则。必须查找页面中章标题。" },
              chapter_number: { type: "string", description: "章数字编号，从 chapter_label 提取数字如 1。" },
              section_label: { type: "string", description: "节编号，从页面原文提取如 第一节。有则填，无则 ''。" },
              section_title: { type: "string", description: "节标题，从页面原文提取。有则填，无则 ''。" },
              section_number: { type: "string", description: "节数字编号。有则填，无则 ''。" },
              article_label: { type: "string", description: "法条编号，同顶层 article_no。" },
              article_number: { type: "integer", description: "法条数字编号，同顶层。" },
              source_path: { type: "string", description: "源路径，填当前页面 URL。" },
              source_title: { type: "string", description: "源标题，同顶层 law_name。" },
              source_type: { type: "string", description: "源类型，同顶层 category。" },
              source_status: { type: "string", description: "源状态，同顶层 validity_status。" },
              source_office: { type: "string", description: "源发布机关，同顶层 office。" },
              source_office_level: { type: "string", description: "源机关层级，同顶层。" },
              source_office_category: { type: "string", description: "源机关类别，同顶层。" },
              source_publish_date: { type: "string", description: "源发布日期，同顶层。" },
              source_effective_date: { type: "string", description: "源生效日期，同顶层。" },
              source_effective_period: { type: "string", description: "源生效时间段，同顶层。" },
              source_article_index: { type: "integer", description: "源法条序号，同 article_index。" },
            },
          },
          source_url: {
            type: ["string", "null"],
            description: "当前法规来源网页 URL，填用户输入的 portal_url。",
          },
        },
      },
    },
  },
};

const CODE_SNIPPET_SCHEMA = {
  type: "object",
  required: ["name", "version", "items"],
  properties: {
    name: {
      type: "string",
      description: "固定填 \\\"code_snippet\\\"。",
    },
    version: {
      type: "string",
      description: "固定填 \\\"1.0\\\"。",
    },
    items: {
      type: "array",
      description:
        "从网页中抽取的代码片段列表。每一条对应一个独立的函数、方法、类定义或可包装为函数的语句块。不要抽取 YAML/JSON/TOML 配置文件、HTML 模板或纯文本。",
      items: {
        type: "object",
        required: ["raw_snippet", "normalized_snippet", "semantic_annotation"],
        properties: {
          // ── 原始代码 ──
          raw_snippet: {
            type: "object",
            required: ["language", "raw_code"],
            properties: {
              language: {
                type: "string",
                description:
                  "代码语言，当前仅抽取 Python 代码。看到非 Python 代码（JS/Java/C++/SQL 等）不要纳入 items。",
              },
              raw_code: {
                type: "string",
                description:
                  "网页中的原始代码文本，必须是非空字符串。保留原始缩进和变量名。注意排除页面导航、注释模板和Shell命令。",
              },
            },
          },

          // ── 标准化代码 ──
          normalized_snippet: {
            type: "object",
            required: ["language", "normalized_code"],
            properties: {
              language: {
                type: "string",
                description: "填 \\\"python\\\"。",
              },
              normalized_code: {
                type: "string",
                description:
                  "标准化后的代码。如果 raw_code 是完整函数或类定义，原样复制；如果 raw_code 是零散语句，包装为 def generated_function(...): 并补上参数和 return 语句。不要返回 null。",
              },
            },
          },

          // ── 语义标注 ──
          semantic_annotation: {
            type: "object",
            required: ["intent", "input_variables", "output_variables", "reusable_interface"],
            properties: {
              intent: {
                type: "string",
                description:
                  "代码意图，用简短中文短语概括，例如 计算总价、读取文件、调用API、解析JSON。",
              },
              input_variables: {
                type: "array",
                description: "输入变量列表。无法识别时返回空数组 []。",
                items: {
                  type: "object",
                  required: ["name", "type", "description"],
                  properties: {
                    name: { type: "string", description: "变量名。" },
                    type: { type: ["string", "null"], description: "变量类型，如 int, str, list。无法判断填 null。" },
                    description: { type: ["string", "null"], description: "变量含义，无法判断填 null。" },
                  },
                },
              },
              output_variables: {
                type: "array",
                description: "输出变量或返回值列表。无法识别时返回空数组 []。",
                items: {
                  type: "object",
                  required: ["name", "type", "description"],
                  properties: {
                    name: { type: "string", description: "变量名或 return。" },
                    type: { type: ["string", "null"], description: "返回类型，无法判断填 null。" },
                    description: { type: ["string", "null"], description: "返回值含义，无法判断填 null。" },
                  },
                },
              },
              reusable_interface: {
                type: "string",
                description:
                  "可复用的函数签名建议，例如 generated_function(price, quantity)。无法确定填 normalized_code 中的函数签名。",
              },
            },
          },

          // ── 元信息 ──
          source_url: {
            type: "string",
            description: "代码来源页面 URL，填用户输入的 portal_url。不要填 null。",
          },
        },
      },
    },
  },
};


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
function getStorageText(storageDbType?: string | null) {
  if (storageDbType === "mysql") return "MySQL";
  if (storageDbType === "milvus") return "Milvus";
  return "本地文件";
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
  isConfigured,
  onEdit,
}: {
  title: string;
  description: string;
  modelName: string;
  isConfigured: boolean;
  onEdit: () => void;
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

        <span
          className={`shrink-0 rounded-full border px-2 py-0.5 text-xs ${
            isConfigured
              ? "border-green-200 bg-green-50 text-green-700"
              : "border-yellow-200 bg-yellow-50 text-yellow-700"
          }`}
        >
          {isConfigured ? "已配置" : "未配置"}
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
        onClick={onEdit}
      >
        编辑配置
      </Button>
    </div>
  );
}

function ResultPreview({ selectedTask }: { selectedTask: CrawlTaskItem | null }) {
  const resultsQuery = useCrawlTaskResults(selectedTask?.id);
  const results = resultsQuery.data?.items ?? [];
  const [isDownloading, setIsDownloading] = useState(false);

  const canDownload = Boolean(
    selectedTask && (selectedTask.status === "SUCCEEDED" || results.length > 0),
  );

  const handleDownload = async () => {
    if (!selectedTask) {
      toast.info("请先选择一个爬取任务");
      return;
    }

    try {
      setIsDownloading(true);

      const response = await fetch(
        `/api/data-center/crawler/tasks/${selectedTask.id}/download`,
      );

      if (!response.ok) {
        throw new Error(await response.text());
      }

      const blob = await response.blob();
      const blobUrl = window.URL.createObjectURL(blob);
      const safeTaskName = (selectedTask.name || selectedTask.id).replace(
        /[\/:*?"<>|]+/g,
        "_",
      );

      const link = document.createElement("a");
      link.href = blobUrl;
      link.download = `${safeTaskName}_outputs.zip`;
      document.body.appendChild(link);
      link.click();
      link.remove();

      window.URL.revokeObjectURL(blobUrl);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "下载本次爬取文件失败",
      );
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <div className="rounded-2xl border bg-background p-5 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 font-medium">
          <FileTextIcon className="size-4" />
          结果预览
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">
            {selectedTask ? `${results.length} 条结果` : "暂无任务"}
          </span>

          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void handleDownload()}
            disabled={!canDownload || isDownloading}
            title={
              canDownload
                ? "下载该任务本次爬取生成的文件"
                : "任务完成或生成结果后可下载文件"
            }
            className="h-8 whitespace-nowrap"
          >
            <DownloadIcon className="mr-1.5 size-3.5" />
            {isDownloading ? "下载中..." : "下载本次爬取文件"}
          </Button>
        </div>
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
  const [isCancelling, setIsCancelling] = useState(false);

  const handleCancel = async () => {
    if (!selectedTask) return;
    try {
      setIsCancelling(true);
      await cancelCrawlTask(selectedTask.id);
      toast.success("任务已取消");
      onRefresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "取消任务失败");
    } finally {
      setIsCancelling(false);
    }
  };

  const canCancel = selectedTask && (selectedTask.status === "PENDING" || selectedTask.status === "RUNNING");
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
                <div className="rounded-xl border p-3">
                  <div className="text-xs text-muted-foreground">输出格式</div>
                  <div className="mt-1 truncate font-medium">
                    {selectedTask.output_mode.toUpperCase()}
                  </div>
                </div>
                <div className="rounded-xl border p-3">
                  <div className="text-xs text-muted-foreground">保存位置</div>
                  <div className="mt-1 truncate font-medium">
                    {getStorageText(selectedTask.storage_db_type)}
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

            <div className="space-y-2.5">
              <Button className="w-full" variant="outline" onClick={onRefresh}>
                <RefreshCwIcon className="mr-2 size-4" />
                刷新任务
              </Button>
              <Button
                className="w-full"
                variant="outline"
                onClick={() => void handleCancel()}
                disabled={!canCancel || isCancelling}
              >
                {isCancelling ? "取消中..." : "取消任务"}
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

  const [mode, setMode] = useState<WorkMode>("manual");
  const [crawlMode, setCrawlMode] = useState<CrawlMode>("general");
  const [name, setName] = useState("");
  const [portalUrl, setPortalUrl] = useState("");
  const [query, setQuery] = useState("");
  const [outputMode, setOutputMode] = useState<OutputMode>("html");
  const [jsonSchemaText, setJsonSchemaText] = useState("");
  const [showJsonSchemaEditor, setShowJsonSchemaEditor] = useState(false);

  const [scheduleHours, setScheduleHours] = useState(0);
  const [scheduleMinutes, setScheduleMinutes] = useState(60);
  const [scheduleEnabled, setScheduleEnabled] = useState(true);
  const [maxIterations, setMaxIterations] = useState(10);

  const [modelConfigs, setModelConfigs] = useState<ModelConfigItem[]>([]);
  const [configDialogOpen, setConfigDialogOpen] = useState(false);
  const [editingConfig, setEditingConfig] = useState<ModelConfigItem | null>(null);
  const [schedules, setSchedules] = useState<ScheduleItem[]>([]);

  const loadModelConfigs = async () => {
    try { const data = await listModelConfigs(); setModelConfigs(data.items); } catch { /* 静默 */ }
  };
  const loadSchedules = async () => {
    try { const data = await listSchedules(); setSchedules(data.items); } catch { /* 静默 */ }
  };
  useState(() => { void loadModelConfigs(); void loadSchedules(); });

  const handlePauseSchedule = async (id: string) => {
    try { await pauseSchedule(id); toast.success("已暂停"); void loadSchedules(); onRefresh(); } catch { toast.error("暂停失败"); }
  };
  const handleResumeSchedule = async (id: string) => {
    try { await resumeSchedule(id); toast.success("已恢复"); void loadSchedules(); } catch { toast.error("恢复失败"); }
  };
  const handleDeleteSchedule = async (id: string) => {
    try { await deleteSchedule(id); toast.success("已删除"); setSchedules((s) => s.filter((x) => x.id !== id)); onRefresh(); } catch { toast.error("删除失败"); }
  };

  const handleCrawlModeChange = (value: CrawlMode) => {
    setCrawlMode(value);
    setShowJsonSchemaEditor(false);

    if (value === "general") {
      return;
    }

    setOutputMode("json");

    if (value === "policy_regulation") {
      setJsonSchemaText(JSON.stringify(POLICY_REGULATION_SCHEMA, null, 2));
      return;
    }

    if (value === "code_snippet") {
      setJsonSchemaText(JSON.stringify(CODE_SNIPPET_SCHEMA, null, 2));
      return;
    }

    // 视频监控类：download 模式，Agent 只导航+下载，不提取页面内容
    if (value === "video_surveillance") {
      setOutputMode("download" as OutputMode);
      setQuery("使用 download_file 工具");
    }
  };

  const canSubmit = useMemo(() => {
    return Boolean(name.trim() && portalUrl.trim() && query.trim());
  }, [name, portalUrl, query]);

  const handleCreateTask = async () => {
    if (!canSubmit) return;

    let parsedJsonSchema: Record<string, unknown> | unknown[] | null = null;

    if (outputMode === "json" && jsonSchemaText.trim()) {
      try {
        parsedJsonSchema = JSON.parse(jsonSchemaText) as
          | Record<string, unknown>
          | unknown[];
      } catch {
        toast.error("JSON 结构定义格式不正确，请检查是否为合法 JSON");
        return;
      }
    }

    if (mode === "schedule") {
      try {
        await createSchedule({
          name: name.trim(),
          schedule_type: "interval",
          interval_hours: scheduleHours,
          interval_minutes: scheduleMinutes,
          timezone: "Asia/Shanghai",
          enabled: scheduleEnabled,
          payload: {
            name: name.trim(),
            portal_url: portalUrl.trim(),
            query: query.trim(),
            output_mode: outputMode,
            storage_db_type: null,
            json_schema: parsedJsonSchema,
            max_iterations: maxIterations,
          },
        });

        toast.success("定时任务已创建");
        setName("");
        setPortalUrl("");
        setQuery("");
        setOutputMode("html");
        setJsonSchemaText("");
        setCrawlMode("general");
        setShowJsonSchemaEditor(false);
        void loadSchedules();
        onRefresh();
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "创建定时任务失败");
      }
      return;
    }

    try {
      const task = await createTask.mutateAsync({
        name: name.trim(),
        portal_url: portalUrl.trim(),
        query: query.trim(),
        output_mode: outputMode,
        storage_db_type: null,
        json_schema: parsedJsonSchema,
        max_iterations: maxIterations,
      });

      toast.success("爬取任务已创建");
      setName("");
      setPortalUrl("");
      setQuery("");
      setOutputMode("html");
      setJsonSchemaText("");
      setCrawlMode("general");
      setShowJsonSchemaEditor(false);

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
          {schedules.length > 0 && (
            <div className="rounded-2xl border bg-background p-5 shadow-sm">
              <div className="flex items-center gap-2 text-sm font-medium">
                <ClockIcon className="size-4" />
                定时任务管理
                <span className="text-xs text-muted-foreground">({schedules.length} 个)</span>
              </div>
              <div className="mt-3 space-y-2">
                {schedules.map((s) => (
                  <div key={s.id} className="flex items-center justify-between rounded-xl border px-4 py-3">
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium truncate">{s.name}</div>
                      <div className="text-xs text-muted-foreground">
                        {s.status === "ACTIVE" ? "运行中" : "已暂停"}
                        {" · "}
                        {s.interval_minutes
                          ? `每 ${s.interval_minutes} 分钟`
                          : s.interval_seconds
                            ? `每 ${Math.round(s.interval_seconds / 60)} 分钟`
                            : ""}
                        {s.next_run_at ? ` · 下次: ${new Date(s.next_run_at).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}` : ""}
                      </div>
                    </div>
                    <div className="ml-3 flex shrink-0 gap-1.5">
                      {s.status === "ACTIVE" ? (
                        <Button size="sm" variant="outline" onClick={() => handlePauseSchedule(s.id)}>
                          暂停
                        </Button>
                      ) : (
                        <Button size="sm" variant="outline" onClick={() => handleResumeSchedule(s.id)}>
                          恢复
                        </Button>
                      )}
                      <Button size="sm" variant="outline" onClick={() => handleDeleteSchedule(s.id)}>
                        删除
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 gap-4 2xl:grid-cols-2">
            {modelConfigs.map((cfg) => (
              <ModelCard
                key={cfg.target}
                title={cfg.label}
                description={
                  cfg.target === "crawler_agent"
                    ? "负责根据自然语言需求进行网页导航。"
                    : "负责对单个页面进行结构化内容提取。"
                }
                modelName={cfg.model_name ?? "未配置"}
                isConfigured={cfg.is_configured}
                onEdit={() => {
                  setEditingConfig(cfg);
                  setConfigDialogOpen(true);
                }}
              />
            ))}
          </div>

          <div className="rounded-2xl border bg-background p-5 shadow-sm">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-3">
                  <div className="text-lg font-semibold">网页智能化爬取</div>
                  <Select
                    value={crawlMode}
                    onValueChange={(value) => handleCrawlModeChange(value as CrawlMode)}
                  >
                    <SelectTrigger className="h-8 w-[190px] rounded-full text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="general">通用网页爬取</SelectItem>
                      <SelectItem value="policy_regulation">政策法规类数据爬取</SelectItem>
                      <SelectItem value="code_snippet">代码片段类数据爬取</SelectItem>
                      <SelectItem value="video_surveillance">数据集下载</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="text-sm text-muted-foreground">
                  输入目标 URL 和自然语言需求，由 Crawler Agent 自动完成网页探索、内容提取和结果保存。
                </div>
              </div>

              <div className="inline-flex shrink-0 rounded-xl bg-muted p-1">
                <button
                  type="button"
                  onClick={() => setMode("manual")}
                  className={cn(
                    "flex min-w-[104px] items-center justify-center gap-1.5 whitespace-nowrap rounded-lg px-4 py-2 text-sm transition",
                    mode === "manual"
                      ? "bg-background shadow-sm"
                      : "text-muted-foreground",
                  )}
                >
                  <PlayIcon className="size-3.5" />
                  手动爬取
                </button>
                <button
                  type="button"
                  onClick={() => setMode("schedule")}
                  className={cn(
                    "flex min-w-[104px] items-center justify-center gap-1.5 whitespace-nowrap rounded-lg px-4 py-2 text-sm transition",
                    mode === "schedule"
                      ? "bg-background shadow-sm"
                      : "text-muted-foreground",
                  )}
                >
                  <TimerIcon className="size-3.5" />
                  定时爬取
                </button>
              </div>
            </div>

            <div className="mt-6 grid grid-cols-1 gap-x-6 gap-y-5 lg:grid-cols-2">
              <div className="space-y-2.5">
                <label className="text-sm font-medium">
                  {mode === "manual" ? "任务名称" : "调度名称"}
                </label>
                <Input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder={mode === "manual" ? "例如：政策网页采集" : "例如：政策网站每日更新采集"}
                />
              </div>

              <div className="space-y-2.5">
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
                  placeholder={
                    crawlMode === "policy_regulation"
                      ? "例如：提取页面中的政策标题、发布时间和正文"
                      : crawlMode === "code_snippet"
                        ? "例如：提取页面中的代码块、编程语言和注释"
                        : crawlMode === "video_surveillance"
                              ? "例如：提取页面中所有监控视频，使用 download_file 下载视频文件到本地"
                              : "例如：提取页面的主要内容"
                  }
                  rows={4}
                />
              </div>

              <div className="space-y-2.5">
                <label className="text-sm font-medium">
                  最大探索步数: {maxIterations}
                </label>
                <input
                  type="range"
                  min={1}
                  max={50}
                  value={maxIterations}
                  onChange={(e) => setMaxIterations(parseInt(e.target.value, 10))}
                  className="w-full h-1.5 appearance-none rounded-full bg-muted accent-primary cursor-pointer"
                />
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>1 (快)</span>
                  <span>50 (深)</span>
                </div>
              </div>

              <div className="space-y-2.5">
                <label className="text-sm font-medium">输出模式</label>
                <Select
                  value={outputMode}
                  onValueChange={(value) => {
                    const nextOutputMode = value as OutputMode;
                    setOutputMode(nextOutputMode);
                    if (nextOutputMode !== "json") {
                      setShowJsonSchemaEditor(false);
                    }
                  }}
                  disabled={crawlMode !== "general"}
                >
                  <SelectTrigger className="w-[150px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="html">HTML</SelectItem>
                    <SelectItem value="markdown">Markdown</SelectItem>
                    <SelectItem value="json">JSON</SelectItem>
                    <SelectItem value="download">数据集下载</SelectItem>
                  </SelectContent>
                </Select>
              </div>


              {outputMode === "json" && (
                <div className="space-y-2.5 lg:col-span-2">
                  <div className="flex items-center justify-between gap-3">
                    <div className="space-y-1">
                      <label className="text-sm font-medium">JSON 结构定义</label>
                      <div className="text-xs leading-5 text-muted-foreground">
                        {crawlMode === "policy_regulation"
                          ? "当前已使用政策法规类数据模板，可展开查看或微调字段。"
                          : crawlMode === "code_snippet"
                            ? "当前已使用代码片段类数据模板，可展开查看或微调字段。"
                            : "如果希望固定 JSON 输出结构，可展开填写 JSON Schema；留空则由系统自动生成结构。"}
                      </div>
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => setShowJsonSchemaEditor((value) => !value)}
                      className="h-8 whitespace-nowrap"
                    >
                      {showJsonSchemaEditor ? "收起模板" : "展开查看/编辑"}
                    </Button>
                  </div>

                  {!showJsonSchemaEditor && (
                    <div className="rounded-xl bg-muted/50 px-3 py-2 text-xs leading-5 text-muted-foreground">
                      {crawlMode === "general"
                        ? "当前未展开 JSON 结构定义。选择 JSON 输出时，可按需展开填写模板。"
                        : "已自动填入当前爬取模式对应的内置 JSON 模板，提交任务时会随任务一起发送。"}
                    </div>
                  )}

                  {showJsonSchemaEditor && (
                    <>
                      <Textarea
                        value={jsonSchemaText}
                        onChange={(event) => setJsonSchemaText(event.target.value)}
                        placeholder='例如：{"type":"object","properties":{"items":{"type":"array"}}}'
                        rows={10}
                        className="max-h-[360px] min-h-[220px] font-mono text-xs leading-5"
                      />
                      <div className="rounded-xl bg-muted/60 px-3 py-2 text-xs leading-5 text-muted-foreground">
                        {crawlMode === "policy_regulation"
                          ? "当前已使用政策法规类数据模板，可根据需要微调字段。"
                          : crawlMode === "code_snippet"
                            ? "当前已使用代码片段类数据模板，可根据需要微调字段。"
                            : "如果希望固定 JSON 输出结构，请填写 JSON Schema 或结构模板；留空则由系统自动生成结构。"}
                      </div>
                    </>
                  )}
                </div>
              )}

              {mode === "schedule" && (
                <>
                  <div className="space-y-2.5">
                    <label className="text-sm font-medium">执行间隔</label>
                    <div className="flex items-center gap-1.5">
                      <Input
                        type="number"
                        min={0}
                        value={scheduleHours}
                        onChange={(e) => {
                          const v = parseInt(e.target.value, 10) || 0;
                          if (v >= 0) setScheduleHours(v);
                        }}
                        className="w-20"
                      />
                      <span className="text-sm text-muted-foreground">小时</span>
                      <Input
                        type="number"
                        min={0}
                        value={scheduleMinutes}
                        onChange={(e) => {
                          const v = parseInt(e.target.value, 10) || 0;
                          if (v >= 0) setScheduleMinutes(v);
                        }}
                        className="w-20"
                      />
                      <span className="text-sm text-muted-foreground">分钟</span>
                    </div>
                    {scheduleHours === 0 && scheduleMinutes === 0 && (
                      <p className="text-xs text-red-500">小时和分钟不能同时为 0</p>
                    )}
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

            <div className="mt-6 flex items-center justify-end gap-3 border-t pt-5">
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

      <ModelConfigDialog
        open={configDialogOpen}
        onOpenChange={setConfigDialogOpen}
        config={editingConfig}
        onSaved={() => void loadModelConfigs()}
      />
    </div>
  );
}