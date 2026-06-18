export type DocumentParseStatus = "completed" | "failed";

export type DocumentParseResponse = {
  jobId: string;
  filename: string;
  isImage: boolean;
  preprocessed: boolean;
  processedImageUrl: string | null;
  markdown: string;
  markdownDownloadUrl: string;
  preprocessReport: unknown | null;
  warnings: string[];
};

export type DocumentParseTask = {
  id: string;
  jobId?: string;
  filename: string;
  fileType?: string;
  fileSize?: number;
  status: DocumentParseStatus;
  isImage?: boolean;
  preprocessed: boolean;
  markdown?: string;
  markdownBeforePreprocess?: string;
  originalImageUrl?: string;
  processedImageUrl?: string | null;
  preprocessReport?: unknown | null;
  warnings?: string[];
  error?: string;
  createdAt: string;
  completedAt?: string;
};
