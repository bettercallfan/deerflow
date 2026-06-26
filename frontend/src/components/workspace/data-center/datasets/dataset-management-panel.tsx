"use client";

import { useState } from "react";

import { useDatasetRecords, useDatasetStats } from "@/core/datasets";
import { DatasetRecordDetailDrawer } from "./dataset-record-detail-drawer";
import { DatasetSidebar } from "./dataset-sidebar";
import { DatasetViewer } from "./dataset-viewer";

export function DatasetManagementPanel() {
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState("");
  const [resultType, setResultType] = useState("all");
  const [selectedRecordId, setSelectedRecordId] = useState<number | null>(null);

  const pageSize = 20;

  const recordsQuery = useDatasetRecords({
    page,
    page_size: pageSize,
    keyword,
    result_type: resultType,
  });

  const statsQuery = useDatasetStats();

  const records = recordsQuery.data?.items ?? [];
  const total = recordsQuery.data?.total ?? 0;

  return (
    <div className="flex h-full min-h-0">
      <main className="min-w-0 flex-1 overflow-y-auto bg-muted/20 p-6">
        <div className="mx-auto max-w-[1200px] space-y-5">
          <section className="rounded-2xl border bg-background p-5">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="text-sm text-muted-foreground">
                  数据中心 / 数据集管理
                </div>
                <h1 className="mt-1 text-2xl font-semibold">
                  网页爬取结果数据集
                </h1>
                <p className="mt-2 text-sm text-muted-foreground">
                  从 MySQL external_crawl_content
                  表读取网页爬取产生的 Markdown、JSON 和 HTML 结果。
                </p>
              </div>

              <button
                type="button"
                className="rounded-md border px-3 py-2 text-sm"
                onClick={() => {
                  void recordsQuery.refetch();
                  void statsQuery.refetch();
                }}
              >
                刷新
              </button>
            </div>

            <div className="mt-4 flex flex-wrap gap-2 text-xs">
              <span className="rounded-full border px-2 py-1">Markdown</span>
              <span className="rounded-full border px-2 py-1">JSON</span>
              <span className="rounded-full border px-2 py-1">HTML</span>
              <span className="rounded-full border px-2 py-1">MySQL</span>
            </div>
          </section>

          <section className="rounded-2xl border bg-background p-4">
            <div className="flex flex-wrap gap-3">
              <input
                className="min-w-[280px] flex-1 rounded-md border bg-background px-3 py-2 text-sm"
                placeholder="搜索标题、URL、正文内容..."
                value={keyword}
                onChange={(event) => {
                  setKeyword(event.target.value);
                  setPage(1);
                }}
              />

              <select
                className="rounded-md border bg-background px-3 py-2 text-sm"
                value={resultType}
                onChange={(event) => {
                  setResultType(event.target.value);
                  setPage(1);
                }}
              >
                <option value="all">全部类型</option>
                <option value="markdown">Markdown</option>
                <option value="json">JSON</option>
                <option value="html">HTML</option>
              </select>
            </div>
          </section>

          <DatasetViewer
            records={records}
            total={total}
            page={page}
            pageSize={pageSize}
            loading={recordsQuery.isLoading}
            onPageChange={setPage}
            onOpenRecord={setSelectedRecordId}
          />
        </div>
      </main>

      <DatasetSidebar
        stats={statsQuery.data}
        loading={statsQuery.isLoading}
      />

      <DatasetRecordDetailDrawer
        open={selectedRecordId !== null}
        recordId={selectedRecordId}
        onClose={() => setSelectedRecordId(null)}
      />
    </div>
  );
}
