"use client";

import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useI18n } from "@/core/i18n/hooks";
import { useCreateCrawlTask } from "@/core/crawler";
import type { OutputMode } from "@/core/crawler";

interface CrawlerCreateDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CrawlerCreateDialog({
  open,
  onOpenChange,
}: CrawlerCreateDialogProps) {
  const { t } = useI18n();
  const createTask = useCreateCrawlTask();

  const [name, setName] = useState("");
  const [portalUrl, setPortalUrl] = useState("");
  const [query, setQuery] = useState("");
  const [outputMode, setOutputMode] = useState<OutputMode>("html");

  const resetForm = () => {
    setName("");
    setPortalUrl("");
    setQuery("");
    setOutputMode("html");
  };

  const handleSubmit = async () => {
    if (!name.trim() || !portalUrl.trim() || !query.trim()) return;

    try {
      await createTask.mutateAsync({
        name: name.trim(),
        portal_url: portalUrl.trim(),
        query: query.trim(),
        output_mode: outputMode,
      });
      toast.success("爬取任务已创建");
      resetForm();
      onOpenChange(false);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "创建爬取任务失败",
      );
    }
  };

  const isValid = name.trim() && portalUrl.trim() && query.trim();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t.dataCenter.crawler.createTask}</DialogTitle>
          <DialogDescription>
            填写以下信息来创建一个新的网页爬取任务。任务创建后将立即开始执行。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">
              {t.dataCenter.crawler.taskName}
            </label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t.dataCenter.crawler.taskNamePlaceholder}
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">
              {t.dataCenter.crawler.targetUrl}
            </label>
            <Input
              value={portalUrl}
              onChange={(e) => setPortalUrl(e.target.value)}
              placeholder={t.dataCenter.crawler.targetUrlPlaceholder}
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">
              {t.dataCenter.crawler.searchQuery}
            </label>
            <Textarea
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t.dataCenter.crawler.searchQueryPlaceholder}
              rows={3}
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">
              {t.dataCenter.crawler.outputMode}
            </label>
            <Select
              value={outputMode}
              onValueChange={(v) => setOutputMode(v as OutputMode)}
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
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
          >
            取消
          </Button>
          <Button
            onClick={() => void handleSubmit()}
            disabled={!isValid || createTask.isPending}
          >
            {createTask.isPending ? "创建中..." : t.dataCenter.crawler.createTask}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
