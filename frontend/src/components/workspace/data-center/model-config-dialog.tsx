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
import { upsertModelConfig, type ModelConfigItem } from "@/core/crawler";

interface ModelConfigDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  config: ModelConfigItem | null;
  onSaved: () => void;
}

export function ModelConfigDialog({
  open,
  onOpenChange,
  config,
  onSaved,
}: ModelConfigDialogProps) {
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [modelName, setModelName] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [initialized, setInitialized] = useState(false);

  if (config && !initialized) {
    setApiKey("");
    setBaseUrl(config.base_url ?? "");
    setModelName(config.model_name ?? "");
    setInitialized(true);
  }

  const resetForm = () => {
    setApiKey("");
    setBaseUrl("");
    setModelName("");
    setInitialized(false);
  };

  const handleSave = async () => {
    if (!config || !baseUrl.trim() || !modelName.trim()) return;

    try {
      setIsSaving(true);
      const payload: { api_key?: string; base_url: string; model_name: string } = {
        base_url: baseUrl.trim(),
        model_name: modelName.trim(),
      };
      if (apiKey.trim()) {
        payload.api_key = apiKey.trim();
      }

      await upsertModelConfig(config.target, payload);
      toast.success(`${config.label} 配置已更新`);
      resetForm();
      onOpenChange(false);
      onSaved();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "保存模型配置失败");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(open) => {
      if (!open) resetForm();
      onOpenChange(open);
    }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>编辑 {config?.label ?? "模型"}</DialogTitle>
          <DialogDescription>
            配置爬虫使用的 LLM 模型连接信息。修改后立即生效。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">API Key</label>
            <Input
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={config?.has_api_key ? "已设置，留空不修改" : "sk-xxx"}
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">Base URL</label>
            <Input
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1"
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">模型名称</label>
            <Input
              value={modelName}
              onChange={(e) => setModelName(e.target.value)}
              placeholder="qwen-plus"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            onClick={() => void handleSave()}
            disabled={!baseUrl.trim() || !modelName.trim() || isSaving}
          >
            {isSaving ? "保存中..." : "保存"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
