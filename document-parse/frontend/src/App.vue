<template>
  <main class="app-shell">
    <section class="workspace">
      <header class="topbar">
        <div>
          <p class="eyebrow">PaddleOCR3</p>
          <h1>文档解析工作台</h1>
        </div>

        <label class="switch">
          <input v-model="preprocessEnabled" type="checkbox" />
          <span class="slider"></span>
          <span>开启图片预处理</span>
        </label>
      </header>

      <section
        class="dropzone"
        :class="{ 'is-dragging': isDragging }"
        tabindex="0"
        @click="openFilePicker"
        @keydown.enter.prevent="openFilePicker"
        @keydown.space.prevent="openFilePicker"
        @dragenter.prevent="isDragging = true"
        @dragover.prevent="isDragging = true"
        @dragleave.prevent="isDragging = false"
        @drop.prevent="handleDrop"
      >
        <input
          ref="fileInput"
          type="file"
          accept=".png,.jpg,.jpeg,.bmp,.tif,.tiff,.pdf"
          @change="handleFileChange"
        />
        <div class="upload-icon">+</div>
        <h2>拖拽图片或 PDF 到这里</h2>
        <p>也可以点击选择文件。预处理目前只支持图片，PDF 会跳过预处理直接解析。</p>
        <button type="button" @click.stop="openFilePicker">选择文件</button>
        <p v-if="selectedFile" class="file-meta">
          {{ selectedFile.name }} · {{ fileSizeText }}
        </p>
      </section>

      <section class="status-row">
        <button type="button" :disabled="!selectedFile || isParsing" @click="parseFile">
          {{ isParsing ? "解析中..." : "开始解析" }}
        </button>
        <span>{{ statusText }}</span>
      </section>

      <section v-if="warningText" class="warning">
        {{ warningText }}
      </section>

      <section v-if="processedImageUrl" class="preview-panel">
        <div class="section-title">
          <h2>预处理效果</h2>
          <span>图片上传且开启预处理时展示</span>
        </div>
        <img :src="processedImageUrl" alt="预处理后的图片" />
      </section>

      <section class="markdown-panel">
        <div class="section-title">
          <h2>Markdown 解析结果</h2>
          <a v-if="downloadUrl" class="download-link" :href="downloadUrl">下载 .md</a>
        </div>
        <pre class="markdown-output">{{ markdownText || "解析后的 Markdown 内容会显示在这里。" }}</pre>
      </section>
    </section>
  </main>
</template>

<script setup>
import { computed, ref, watch } from "vue";

const fileInput = ref(null);
const selectedFile = ref(null);
const preprocessEnabled = ref(true);
const isDragging = ref(false);
const isParsing = ref(false);
const statusText = ref("等待上传文件");
const warningText = ref("");
const markdownText = ref("");
const downloadUrl = ref("");
const processedImageUrl = ref("");

const fileSizeText = computed(() => {
  if (!selectedFile.value) return "";
  return `${(selectedFile.value.size / 1024 / 1024).toFixed(2)} MB`;
});

const selectedFileIsImage = computed(() => {
  return Boolean(selectedFile.value?.type?.startsWith("image/"));
});

watch(preprocessEnabled, () => {
  if (!selectedFile.value) return;
  statusText.value = preprocessEnabled.value && selectedFileIsImage.value
    ? "图片已就绪，解析时会先预处理"
    : "文件已就绪";
});

function openFilePicker() {
  fileInput.value?.click();
}

function resetResult() {
  warningText.value = "";
  markdownText.value = "";
  downloadUrl.value = "";
  processedImageUrl.value = "";
}

function selectFile(file) {
  if (!file) return;
  selectedFile.value = file;
  resetResult();
  statusText.value = selectedFileIsImage.value ? "图片已就绪" : "文档已就绪";
}

function handleFileChange(event) {
  selectFile(event.target.files?.[0]);
}

function handleDrop(event) {
  isDragging.value = false;
  selectFile(event.dataTransfer.files?.[0]);
}

async function readJsonResponse(response) {
  const text = await response.text();
  if (!text) {
    return {};
  }

  try {
    return JSON.parse(text);
  } catch {
    throw new Error(text || ("请求失败，HTTP " + response.status));
  }
}

async function parseFile() {
  if (!selectedFile.value) return;

  const formData = new FormData();
  formData.append("file", selectedFile.value);
  formData.append("preprocess", String(preprocessEnabled.value));

  resetResult();
  isParsing.value = true;
  statusText.value = "正在上传并解析，请稍等";

  try {
    const response = await fetch("/api/parse", {
      method: "POST",
      body: formData,
    });
    const payload = await readJsonResponse(response);

    if (!response.ok) {
      throw new Error(payload.detail || ("解析失败，HTTP " + response.status));
    }

    warningText.value = (payload.warnings || []).join(" ");
    markdownText.value = payload.markdown || "没有解析到 Markdown 内容。";
    downloadUrl.value = payload.markdownDownloadUrl || "";
    processedImageUrl.value = payload.processedImageUrl
      ? `${payload.processedImageUrl}?t=${Date.now()}`
      : "";
    statusText.value = "解析完成";
  } catch (error) {
    warningText.value = error.message;
    markdownText.value = "";
    statusText.value = "解析失败";
  } finally {
    isParsing.value = false;
  }
}
</script>
