import type { DocumentParseResponse } from "./types";

const API_PREFIX = "/api/data-center/document-parser";

export async function parseDocument(params: {
  file: File;
  preprocess: boolean;
}): Promise<DocumentParseResponse> {
  const formData = new FormData();
  formData.append("file", params.file);
  formData.append("preprocess", String(params.preprocess));

  const response = await fetch(`${API_PREFIX}/parse`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const text = await response.text();
    let message = text || `文档解析失败，状态码：${response.status}`;

    try {
      const json = JSON.parse(text);
      message = json.detail || message;
    } catch {
      // keep raw message
    }

    throw new Error(message);
  }

  return response.json();
}
