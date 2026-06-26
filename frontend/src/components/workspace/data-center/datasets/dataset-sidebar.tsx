"use client";

import type { DatasetStats } from "@/core/datasets";

interface DatasetSidebarProps {
  stats?: DatasetStats;
  loading?: boolean;
}

export function DatasetSidebar({ stats, loading }: DatasetSidebarProps) {
  if (loading) {
    return (
      <aside className="w-80 shrink-0 border-l bg-background p-5 text-sm text-muted-foreground">
        正在加载统计信息...
      </aside>
    );
  }

  return (
    <aside className="w-80 shrink-0 border-l bg-background p-5">
      <h3 className="text-sm font-semibold">数据集统计</h3>

      <div className="mt-4 space-y-3 text-sm">
        <StatItem label="总记录数" value={stats?.total_records ?? 0} />
        <StatItem label="来源任务数" value={stats?.task_count ?? 0} />
        <StatItem label="Markdown" value={stats?.markdown_count ?? 0} />
        <StatItem label="JSON" value={stats?.json_count ?? 0} />
        <StatItem label="HTML" value={stats?.html_count ?? 0} />
        <StatItem
          label="最近入库"
          value={stats?.latest_created_at ?? "-"}
        />
      </div>
    </aside>
  );
}

function StatItem({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div className="rounded-xl border p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 font-medium">{value}</div>
    </div>
  );
}
