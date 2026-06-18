"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { parseDocument } from "@/core/document-parser/api";
import type { DocumentParseTask } from "@/core/document-parser/types";
import { MarkdownContent } from "@/components/workspace/messages/markdown-content";
import { streamdownPlugins } from "@/core/streamdown";

type ViewMode = "create" | "detail";
type ResultTab = "preview" | "source" | "info";

const STORAGE_KEY = "deerflow.document-parser.tasks";

function createLocalId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function formatDate(value?: string) {
  if (!value) return "-";
  return new Date(value).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatFileSize(size?: number) {
  if (!size) return "-";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function getStatusText(status: DocumentParseTask["status"]) {
  if (status === "completed") return "已完成";
  return "失败";
}

function getStatusClass(status: DocumentParseTask["status"]) {
  if (status === "completed") {
    return "bg-green-100 text-green-700";
  }
  return "bg-red-100 text-red-700";
}

export function DocumentParserPanel() {
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [mounted, setMounted] = useState(false);
  const [tasks, setTasks] = useState<DocumentParseTask[]>([]);
  const [viewMode, setViewMode] = useState<ViewMode>("create");
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [preprocess, setPreprocess] = useState(false);
  const [isParsing, setIsParsing] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [resultTab, setResultTab] = useState<ResultTab>("preview");

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        setTasks(JSON.parse(raw));
      }
    } catch {
      // ignore localStorage error
    }
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted) return;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(tasks));
  }, [tasks, mounted]);

  const selectedTask = useMemo(() => {
    if (!selectedTaskId) return null;
    return tasks.find((task) => task.id === selectedTaskId) ?? null;
  }, [tasks, selectedTaskId]);

  function goCreate() {
    setViewMode("create");
    setSelectedTaskId(null);
    setResultTab("preview");
    setFormError(null);
  }

  function openTask(task: DocumentParseTask) {
    setSelectedTaskId(task.id);
    setViewMode("detail");
    setResultTab("preview");
  }

  async function handleParse() {
    if (!selectedFile) {
      setFormError("请先选择一个 PDF 或图片文件。");
      return;
    }

    setFormError(null);
    setIsParsing(true);

    const createdAt = new Date().toISOString();

    try {
      const result = await parseDocument({
        file: selectedFile,
        preprocess,
      });

      const task: DocumentParseTask = {
        id: result.jobId,
        jobId: result.jobId,
        filename: result.filename,
        fileType: selectedFile.type || "unknown",
        fileSize: selectedFile.size,
        status: "completed",
        isImage: result.isImage,
        preprocessed: result.preprocessed,
        markdown: result.markdown,
        originalImageUrl: preprocess ? URL.createObjectURL(selectedFile) : undefined,
        processedImageUrl: result.processedImageUrl,
        preprocessReport: result.preprocessReport,
        warnings: result.warnings,
        createdAt,
        completedAt: new Date().toISOString(),
      };

      setTasks((prev) => [task, ...prev]);
      setSelectedTaskId(task.id);
      setViewMode("detail");
      setResultTab("preview");
      setSelectedFile(null);

      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    } catch (error) {
      const task: DocumentParseTask = {
        id: createLocalId(),
        filename: selectedFile.name,
        fileType: selectedFile.type || "unknown",
        fileSize: selectedFile.size,
        status: "failed",
        preprocessed: preprocess,
        error: error instanceof Error ? error.message : String(error),
        createdAt,
        completedAt: new Date().toISOString(),
      };

      setTasks((prev) => [task, ...prev]);
      setSelectedTaskId(task.id);
      setViewMode("detail");
    } finally {
      setIsParsing(false);
    }
  }

  function deleteTask(taskId: string) {
    setTasks((prev) => prev.filter((task) => task.id !== taskId));
    if (selectedTaskId === taskId) {
      goCreate();
    }
  }

  return (
    <div className="grid h-full min-h-[720px] grid-cols-[320px_minmax(0,1fr)] gap-6">
      <aside className="rounded-2xl border bg-background p-4">
        <div className="mb-4">
          <h2 className="text-lg font-semibold">文档解析任务</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            上传 PDF 或图片，查看历史解析结果。
          </p>
        </div>

        <button
          type="button"
          onClick={goCreate}
          className={[
            "mb-4 flex w-full items-center justify-center rounded-xl border px-4 py-3 text-sm font-medium transition",
            viewMode === "create"
              ? "border-primary bg-primary text-primary-foreground"
              : "bg-background hover:bg-muted",
          ].join(" ")}
        >
          + 新建解析
        </button>

        <div className="space-y-3">
          {tasks.length === 0 ? (
            <div className="rounded-xl border border-dashed p-4 text-center text-sm text-muted-foreground">
              暂无历史任务
            </div>
          ) : (
            tasks.map((task) => (
              <button
                key={task.id}
                type="button"
                onClick={() => openTask(task)}
                className={[
                  "w-full rounded-xl border p-4 text-left transition hover:bg-muted",
                  selectedTaskId === task.id && viewMode === "detail"
                    ? "border-primary bg-muted"
                    : "bg-background",
                ].join(" ")}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">
                      {task.filename}
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {formatDate(task.createdAt)} · {formatFileSize(task.fileSize)}
                    </div>
                  </div>

                  <span
                    className={[
                      "shrink-0 rounded-full px-2 py-1 text-xs",
                      getStatusClass(task.status),
                    ].join(" ")}
                  >
                    {getStatusText(task.status)}
                  </span>
                </div>
              </button>
            ))
          )}
        </div>
      </aside>

      <main className="min-w-0 rounded-2xl border bg-background p-6">
        {viewMode === "create" ? (
          <section>
            <div className="mb-6">
              <h2 className="text-xl font-semibold">文档智能解析</h2>
              <p className="mt-2 text-sm text-muted-foreground">
                上传 PDF、PNG、JPG 等文档文件，自动解析为 Markdown 结构化内容。
              </p>
            </div>

            <div
              onClick={() => fileInputRef.current?.click()}
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                event.preventDefault();
                const file = event.dataTransfer.files?.[0];
                if (file) {
                  setSelectedFile(file);
                  setFormError(null);
                }
              }}
              className="flex min-h-[220px] cursor-pointer flex-col items-center justify-center rounded-2xl border border-dashed bg-muted/30 p-8 text-center hover:bg-muted/50"
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.png,.jpg,.jpeg"
                className="hidden"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) {
                    setSelectedFile(file);
                    setFormError(null);
                  }
                }}
              />

              <div className="text-base font-medium">
                点击上传或拖拽文件到这里
              </div>
              <div className="mt-2 text-sm text-muted-foreground">
                支持 PDF / PNG / JPG / JPEG
              </div>

              {selectedFile && (
                <div className="mt-5 rounded-xl border bg-background px-4 py-3 text-sm">
                  已选择：{selectedFile.name} · {formatFileSize(selectedFile.size)}
                </div>
              )}
            </div>

            <div className="mt-6 flex items-center justify-between rounded-xl border p-4">
              <div>
                <div className="text-sm font-medium">启用预处理增强</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  对倾斜、模糊或拍照文档进行增强处理。
                </div>
              </div>

              <label className="flex cursor-pointer items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={preprocess}
                  onChange={(event) => setPreprocess(event.target.checked)}
                />
                开启
              </label>
            </div>

            {formError && (
              <div className="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                {formError}
              </div>
            )}

            <div className="mt-6 flex justify-end">
              <button
                type="button"
                onClick={handleParse}
                disabled={isParsing}
                className="rounded-xl bg-primary px-6 py-3 text-sm font-medium text-primary-foreground disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isParsing ? "解析中..." : "开始解析"}
              </button>
            </div>
          </section>
        ) : selectedTask ? (
          <section>
            <div className="mb-6 flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex items-center gap-3">
                  <h2 className="truncate text-xl font-semibold">
                    {selectedTask.filename}
                  </h2>
                  <span
                    className={[
                      "rounded-full px-2 py-1 text-xs",
                      getStatusClass(selectedTask.status),
                    ].join(" ")}
                  >
                    {getStatusText(selectedTask.status)}
                  </span>
                </div>

                <p className="mt-2 text-sm text-muted-foreground">
                  {selectedTask.fileType || "未知类型"} ·
                  {selectedTask.preprocessed ? " 已启用预处理" : " 未启用预处理"} ·
                  Markdown 输出
                </p>
              </div>

              <div className="flex shrink-0 gap-2">
                {selectedTask.markdownDownloadUrl && (
                  <a
                    href={selectedTask.markdownDownloadUrl}
                    download
                    className="rounded-xl border px-4 py-2 text-sm hover:bg-muted"
                  >
                    下载 Markdown
                  </a>
                )}

                <button
                  type="button"
                  onClick={() => deleteTask(selectedTask.id)}
                  className="rounded-xl border px-4 py-2 text-sm text-red-600 hover:bg-red-50"
                >
                  删除记录
                </button>
              </div>
            </div>

            <div className="mb-6 grid grid-cols-4 gap-4">
              <div className="rounded-xl border p-4">
                <div className="text-xs text-muted-foreground">文件大小</div>
                <div className="mt-2 text-sm font-medium">
                  {formatFileSize(selectedTask.fileSize)}
                </div>
              </div>

              <div className="rounded-xl border p-4">
                <div className="text-xs text-muted-foreground">预处理</div>
                <div className="mt-2 text-sm font-medium">
                  {selectedTask.preprocessed ? "是" : "否"}
                </div>
              </div>

              <div className="rounded-xl border p-4">
                <div className="text-xs text-muted-foreground">输出格式</div>
                <div className="mt-2 text-sm font-medium">Markdown</div>
              </div>

              <div className="rounded-xl border p-4">
                <div className="text-xs text-muted-foreground">完成时间</div>
                <div className="mt-2 text-sm font-medium">
                  {formatDate(selectedTask.completedAt)}
                </div>
              </div>
            </div>

            {selectedTask.status === "failed" ? (
              <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
                {selectedTask.error || "解析失败"}
              </div>
            ) : (
              <>
                <div className="mb-4 flex gap-2 border-b">
                  {[
                    ...(selectedTask.preprocessed
                      ? [["compare", "预处理对比"] as [string, string]]
                      : []),
                    ["source", "结果预览"],
                    ["info", "文件信息"],
                  ].map(([value, label]) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setResultTab(value as ResultTab)}
                      className={[
                        "border-b-2 px-4 py-2 text-sm",
                        resultTab === value
                          ? "border-primary font-medium text-primary"
                          : "border-transparent text-muted-foreground",
                      ].join(" ")}
                    >
                      {label}
                    </button>
                  ))}
                </div>

                {resultTab === "compare" && selectedTask.preprocessed && (
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <div className="mb-2 text-sm font-medium">原始图像</div>
                      <div className="flex items-center justify-center rounded-xl border bg-muted/20 p-4">
                        {selectedTask.originalImageUrl ? (
                          <img
                            src={selectedTask.originalImageUrl}
                            alt="原始图像"
                            className="max-h-[460px] max-w-full object-contain"
                          />
                        ) : (
                          <span className="text-sm text-muted-foreground">此任务为旧版任务，缺少原始图像，请新建解析</span>
                        )}
                      </div>
                    </div>
                    <div>
                      <div className="mb-2 text-sm font-medium">预处理增强后</div>
                      <div className="flex items-center justify-center rounded-xl border bg-muted/20 p-4">
                        {selectedTask.processedImageUrl ? (
                          <img
                            src={encodeURI(selectedTask.processedImageUrl)}
                            alt="预处理后"
                            className="max-h-[460px] max-w-full object-contain"
                          />
                        ) : (
                          <span className="text-sm text-muted-foreground">无处理后图像</span>
                        )}
                      </div>
                    </div>
                  </div>
                )}

                {resultTab === "source" && (
                  <div className="max-h-[520px] overflow-auto rounded-xl border bg-muted/20 p-5 text-sm leading-7">
                    {selectedTask.markdown ? (
                      <MarkdownContent
                        content={selectedTask.markdown}
                        isLoading={false}
                        rehypePlugins={streamdownPlugins.rehypePlugins}
                      />
                    ) : (
                      "暂无解析结果"
                    )}
                  </div>
                )}

                {resultTab === "info" && (
                  <div className="space-y-3 rounded-xl border p-5 text-sm">
                    <div>任务 ID：{selectedTask.jobId || selectedTask.id}</div>
                    <div>文件名：{selectedTask.filename}</div>
                    <div>文件类型：{selectedTask.fileType || "-"}</div>
                    <div>是否图片：{selectedTask.isImage ? "是" : "否"}</div>
                    <div>下载地址：{selectedTask.markdownDownloadUrl || "-"}</div>
                    <div>
                      警告信息：
                      {selectedTask.warnings?.length
                        ? selectedTask.warnings.join("；")
                        : "无"}
                    </div>
                  </div>
                )}
              </>
            )}
          </section>
        ) : (
          <section className="flex h-full items-center justify-center text-sm text-muted-foreground">
            请选择左侧任务，或点击“新建解析”。
          </section>
        )}
      </main>
    </div>
  );
}
