"use client";

import { useState } from "react";

import { useDatasetRecordDetail } from "@/core/datasets";

interface DatasetRecordDetailDrawerProps {
  recordId: number | null;
  open: boolean;
  onClose: () => void;
}

type DetailTab = "markdown" | "json" | "html" | "meta";

export function DatasetRecordDetailDrawer({
  recordId,
  open,
  onClose,
}: DatasetRecordDetailDrawerProps) {
  const [activeTab, setActiveTab] = useState<DetailTab>("markdown");
  const detailQuery = useDatasetRecordDetail(recordId);

  if (!open) return null;

  const record = detailQuery.data;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/20">
      <div className="h-full w-[720px] overflow-y-auto border-l bg-background shadow-xl">
        <div className="sticky top-0 z-10 border-b bg-background p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold">
                {record?.title || "记录详情"}
              </h2>
              <p className="mt-1 max-w-[560px] truncate text-sm text-muted-foreground">
                {record?.page_url || ""}
              </p>
            </div>

            <button
              type="button"
              className="rounded-md border px-3 py-1 text-sm"
              onClick={onClose}
            >
              关闭
            </button>
          </div>
        </div>

        {detailQuery.isLoading ? (
          <div className="p-6 text-sm text-muted-foreground">
            正在加载详情...
          </div>
        ) : !record ? (
          <div className="p-6 text-sm text-muted-foreground">
            未找到记录
          </div>
        ) : (
          <div className="p-5">
            <div className="grid grid-cols-2 gap-3 text-sm">
              <Info label="ID" value={record.id} />
              <Info label="结果类型" value={record.result_type || "-"} />
              <Info label="任务 ID" value={record.task_id || "-"} />
              <Info label="入库时间" value={record.created_at || "-"} />
              <Info
                label="原始 HTML 哈希"
                value={record.raw_html_hash || "-"}
              />
              <Info
                label="标准化哈希"
                value={record.normalized_content_hash || "-"}
              />
            </div>

            <div className="mt-5 flex gap-2 border-b">
              <TabButton
                active={activeTab === "markdown"}
                onClick={() => setActiveTab("markdown")}
              >
                Markdown
              </TabButton>
              <TabButton
                active={activeTab === "json"}
                onClick={() => setActiveTab("json")}
              >
                JSON
              </TabButton>
              <TabButton
                active={activeTab === "html"}
                onClick={() => setActiveTab("html")}
              >
                HTML
              </TabButton>
              <TabButton
                active={activeTab === "meta"}
                onClick={() => setActiveTab("meta")}
              >
                元信息
              </TabButton>
            </div>

            <div className="mt-4">
              {activeTab === "markdown" && (
                <CodeBlock
                  content={record.result_markdown || "暂无 Markdown 内容"}
                />
              )}

              {activeTab === "json" && (
                <CodeBlock
                  content={
                    record.result_json
                      ? JSON.stringify(record.result_json, null, 2)
                      : "暂无 JSON 内容"
                  }
                />
              )}

              {activeTab === "html" && (
                <CodeBlock
                  content={record.result_html || "暂无 HTML 内容"}
                />
              )}

              {activeTab === "meta" && (
                <CodeBlock
                  content={JSON.stringify(
                    {
                      id: record.id,
                      task_id: record.task_id,
                      page_url: record.page_url,
                      title: record.title,
                      raw_html_hash: record.raw_html_hash,
                      normalized_content_hash:
                        record.normalized_content_hash,
                      result_type: record.result_type,
                      created_at: record.created_at,
                    },
                    null,
                    2,
                  )}
                />
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Info({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 break-all text-sm">{value}</div>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      className={`border-b-2 px-3 py-2 text-sm ${
        active
          ? "border-foreground font-medium"
          : "border-transparent text-muted-foreground"
      }`}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

function CodeBlock({ content }: { content: string }) {
  return (
    <pre className="max-h-[620px] overflow-auto rounded-xl border bg-muted/30 p-4 text-xs leading-relaxed whitespace-pre-wrap">
      {content}
    </pre>
  );
}
