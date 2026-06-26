"use client";

import type { DatasetRecordListItem } from "@/core/datasets";

interface DatasetViewerProps {
  records: DatasetRecordListItem[];
  total: number;
  page: number;
  pageSize: number;
  loading?: boolean;
  onPageChange: (page: number) => void;
  onOpenRecord: (recordId: number) => void;
}

export function DatasetViewer({
  records,
  total,
  page,
  pageSize,
  loading,
  onPageChange,
  onOpenRecord,
}: DatasetViewerProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="rounded-2xl border bg-background">
      <div className="border-b p-4">
        <div className="font-semibold">Dataset Viewer</div>
        <div className="mt-1 text-xs text-muted-foreground">
          共 {total} 条记录，当前第 {page} / {totalPages} 页
        </div>
      </div>

      <div className="overflow-auto">
        <table className="w-full min-w-[1000px] border-collapse text-sm">
          <thead className="bg-muted/40">
            <tr className="border-b text-left">
              <Th>ID</Th>
              <Th>标题</Th>
              <Th>来源 URL</Th>
              <Th>类型</Th>
              <Th>内容预览</Th>
              <Th>任务 ID</Th>
              <Th>入库时间</Th>
              <Th>操作</Th>
            </tr>
          </thead>

          <tbody>
            {loading ? (
              <tr>
                <td
                  colSpan={8}
                  className="p-6 text-center text-muted-foreground"
                >
                  正在加载数据...
                </td>
              </tr>
            ) : records.length === 0 ? (
              <tr>
                <td
                  colSpan={8}
                  className="p-6 text-center text-muted-foreground"
                >
                  暂无数据
                </td>
              </tr>
            ) : (
              records.map((record) => (
                <tr
                  key={record.id}
                  className="cursor-pointer border-b hover:bg-muted/30"
                  onClick={() => onOpenRecord(record.id)}
                >
                  <Td>{record.id}</Td>
                  <Td className="max-w-[220px] truncate">
                    {record.title || "-"}
                  </Td>
                  <Td className="max-w-[280px] truncate">
                    {record.page_url || "-"}
                  </Td>
                  <Td>
                    <span className="rounded-full border px-2 py-1 text-xs">
                      {record.result_type || "-"}
                    </span>
                  </Td>
                  <Td className="max-w-[320px] truncate">
                    {record.content_preview || "-"}
                  </Td>
                  <Td className="max-w-[160px] truncate">
                    {record.task_id || "-"}
                  </Td>
                  <Td>{record.created_at || "-"}</Td>
                  <Td>
                    <button
                      type="button"
                      className="rounded-md border px-2 py-1 text-xs"
                      onClick={(event) => {
                        event.stopPropagation();
                        onOpenRecord(record.id);
                      }}
                    >
                      查看
                    </button>
                  </Td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between border-t p-4 text-sm">
        <button
          type="button"
          className="rounded-md border px-3 py-1 disabled:opacity-50"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          上一页
        </button>

        <span className="text-muted-foreground">
          第 {page} 页 / 共 {totalPages} 页
        </span>

        <button
          type="button"
          className="rounded-md border px-3 py-1 disabled:opacity-50"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
        >
          下一页
        </button>
      </div>
    </div>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th className="whitespace-nowrap px-4 py-3 font-medium">{children}</th>
  );
}

function Td({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <td className={`px-4 py-3 align-top ${className}`}>{children}</td>
  );
}
