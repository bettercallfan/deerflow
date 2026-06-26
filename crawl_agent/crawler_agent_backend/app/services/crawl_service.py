from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import re
import requests
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.legacy_bridge.crawler_agent_bridge import collect_pages_sync, extract_html, extract_json, extract_markdown
from app.models.enums import DuplicateReason, ModelConfigTarget, OutputMode, TaskStatus
from app.models.schedule import ExtractionPositionCache, SiteCheckpoint, TaskEventLog
from app.models.task import CrawlPage, CrawlResult, CrawlRun, CrawlTask
from app.services.model_config_service import ModelConfigService
from app.services.storage_service import StorageService
from app.utils.hash_utils import (
    build_normalized_content_hash,
    build_raw_html_hash,
    build_site_quick_hash,
    sha256_text,
)
from app.utils.url_pattern_utils import are_urls_same_structure, build_url_structure_key


class CrawlService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _build_query_signature(query: str, json_schema: dict | list | None) -> str:
        schema_text = json.dumps(json_schema, ensure_ascii=False, sort_keys=True) if json_schema is not None else ""
        return sha256_text(f"{query}\n{schema_text}")

    @staticmethod
    def _save_result_to_file(task_id: str, page_id: str, idx: int, extracted: dict) -> dict:
        """将抽取结果保存到本地 outputs/{task_id}/ 目录，返回保存路径信息。"""
        output_dir = Path("outputs") / task_id
        output_dir.mkdir(parents=True, exist_ok=True)

        paths: dict[str, str | None] = {
            "html_path": None,
            "markdown_path": None,
            "markdown_ocr_path": None,
            "json_path": None,
        }

        # 根据字段是否存在保存，不依赖 result_type
        if extracted.get("result_html"):
            p = output_dir / f"page_{idx + 1}.html"
            p.write_text(extracted["result_html"], encoding="utf-8")
            paths["html_path"] = str(p)

        if extracted.get("result_markdown"):
            p = output_dir / f"page_{idx + 1}.md"
            p.write_text(extracted["result_markdown"], encoding="utf-8")
            paths["markdown_path"] = str(p)

        if extracted.get("result_markdown_ocr"):
            p = output_dir / f"page_{idx + 1}_ocr.md"
            p.write_text(extracted["result_markdown_ocr"], encoding="utf-8")
            paths["markdown_ocr_path"] = str(p)

        if extracted.get("result_json") is not None:
            p = output_dir / f"page_{idx + 1}.json"
            p.write_text(json.dumps(extracted["result_json"], ensure_ascii=False, indent=2), encoding="utf-8")
            paths["json_path"] = str(p)

        return paths

    @staticmethod
    def _call_embedding(text: str) -> list[float]:
        """调用 text-embedding-v4 API 生成 embedding 向量。API key 从环境变量读取。"""
        import os as _os
        api_key = _os.environ.get("DASHSCOPE_API_KEY", "")
        base_url = _os.environ.get("TEXT_EMBEDDING_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        if not api_key or not base_url:
            return []

        try:
            resp = requests.post(
                f"{base_url.rstrip('/')}/embeddings",
                json={"model": "text-embedding-v4", "input": text[:8000]},
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", [{}])[0].get("embedding", [])
        except Exception:
            return []

    @staticmethod
    def _download_images(task_id: str, page_id: str, idx: int, markdown_text: str, page_url: str, html_text: str = "") -> list[dict]:
        """从 Markdown ![]() 和 HTML <img> 标签中提取图片 URL 并下载，返回图片清单。"""
        import re
        from urllib.parse import urljoin

        images_dir = Path("outputs") / task_id / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        seen: set[str] = set()
        candidates: list[tuple[str, str]] = []  # (alt, url)

        # ── 方式1: Markdown ![](url) ──
        for m in re.finditer(r"!\[([^\]]*)\]\(([^)]+)\)", markdown_text or ""):
            alt, u = m.group(1), m.group(2).strip().split(" ")[0]
            if u not in seen:
                seen.add(u); candidates.append((alt, u))

        # ── 方式2: HTML <img src="..."> ──
        for m in re.finditer(r'<img[^>]+src\s*=\s*["\']([^"\']+)["\']', html_text or "", re.IGNORECASE):
            u = m.group(1).strip()
            if u and u not in seen:
                seen.add(u); candidates.append(("", u))

        if not candidates:
            return []

        records: list[dict] = []
        for i, (alt, img_url) in enumerate(candidates):
            absolute_url = urljoin(page_url, img_url)
            ext = ".jpg"
            url_lower = img_url.lower().split("?")[0]
            for s in [".png", ".gif", ".webp", ".svg", ".jpeg", ".bmp"]:
                if url_lower.endswith(s): ext = s; break

            local_path = images_dir / f"img_{idx + 1}_{i + 1:03d}{ext}"
            downloaded, error = False, None
            try:
                resp = requests.get(absolute_url, timeout=30, stream=True)
                resp.raise_for_status()
                local_path.write_bytes(resp.content)
                downloaded = True
            except Exception as e:
                error = str(e)

            records.append({
                "index": i + 1, "alt": alt,
                "original_url": img_url, "absolute_url": absolute_url,
                "local_path": str(local_path.relative_to(Path("outputs") / task_id)),
                "downloaded": downloaded, "error": error,
            })

        manifest = {"task_id": task_id, "images": records}
        (images_dir / "images.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return records

    @staticmethod
    def _update_manifest(task_id: str, page_id: str, idx: int, url: str, title: str, extracted: dict, paths: dict) -> None:
        """更新 outputs/{task_id}/manifest.json，追加当前页面信息。"""
        import json as _json
        manifest_path = Path("outputs") / task_id / "manifest.json"

        entry = {
            "page_id": page_id,
            "index": idx + 1,
            "url": url,
            "title": title,
            "result_type": extracted.get("result_type"),
            **paths,
        }

        manifest = {"task_id": task_id, "pages": []}
        if manifest_path.exists():
            try:
                existing = _json.loads(manifest_path.read_text(encoding="utf-8"))
                if isinstance(existing, dict) and isinstance(existing.get("pages"), list):
                    manifest = existing
            except Exception:
                pass

        manifest["pages"].append(entry)
        manifest_path.write_text(_json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    def _sync_to_mysql(self, task_id: str) -> None:
        """任务完成后自动将 crawl_result 同步到 MySQL。失败静默跳过。"""
        try:
            storage_service = StorageService(self.db)
            results = self.db.scalars(
                select(CrawlResult).where(CrawlResult.task_id == task_id)
            ).all()
            for r in results:
                page = self.db.get(CrawlPage, r.page_id) if r.page_id else None
                storage_service.write_to_external_storage(
                    storage_db_type_override="mysql",
                    task_id=task_id,
                    page_url=page.url if page else "",
                    title=page.title if page else None,
                    raw_html_hash=page.raw_html_hash if page else "",
                    normalized_content_hash=page.normalized_content_hash if page else "",
                    result_type=r.result_type or "",
                    result_json=r.result_json,
                    result_markdown=r.result_markdown,
                    result_html=page.html_content if page else None,
                )
        except Exception:
            pass

    @staticmethod
    def _enrich_json_result(extracted: dict, idx: int, page_url: str) -> dict:
        """通用后处理：根据数据内容自动判断类型（政策法规/代码片段），补全 LLM 无法生成的字段。"""
        import copy

        items = extracted.get("result_json", {})
        if isinstance(items, dict):
            items = items.get("items", [])
        if not isinstance(items, list) or not items:
            return extracted

        enriched_items = []
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                enriched_items.append(item)
                continue
            item = copy.deepcopy(item)

            # ── 判断数据类型 ──
            is_code = any(k in item for k in ("raw_snippet", "raw_code", "language", "normalized_code"))
            is_policy = any(k in item for k in ("law_name", "article_no", "office", "publish_date"))

            if is_code:
                # 代码片段：补全标准化代码的 language 字段
                raw = item.setdefault("raw_snippet", {})
                norm = item.setdefault("normalized_snippet", {})
                anno = item.setdefault("semantic_annotation", {})
                if isinstance(raw, dict):
                    raw["language"] = "python"
                if isinstance(norm, dict):
                    norm["language"] = "python"
                if isinstance(anno, dict):
                    anno["intent"] = anno.get("intent") or ""
                    anno["input_variables"] = anno.get("input_variables") or []
                    anno["output_variables"] = anno.get("output_variables") or []
                    anno["reusable_interface"] = anno.get("reusable_interface") or ""

            elif is_policy:
                # 政策法规：补全 id / page_content / metadata
                law_name = item.get("law_name", "")
                article_no = item.get("article_no", "")
                if not item.get("id"):
                    item["id"] = f"{idx}::{law_name}::{article_no}"
                title = item.get("title") or law_name
                content = item.get("content", "")
                item["page_content"] = f"{title}\n{article_no} {content}".strip()
                item["source_path"] = page_url
                item["source_article_index"] = i + 1

                meta = item.setdefault("metadata", {})
                if isinstance(meta, dict):
                    meta["publish_date"] = item.get("publish_date") or ""
                    meta["effective_date"] = item.get("effective_date") or ""
                    meta["type"] = item.get("category") or ""
                    meta["status"] = item.get("validity_status") or ""
                    meta["title"] = law_name
                    meta["office"] = item.get("office") or ""
                    meta["office_level"] = item.get("office_level") or ""
                    meta["office_category"] = item.get("office_category") or ""
                    meta["effective_period"] = item.get("effective_period") or ""
                    meta["source_row_id"] = idx
                    meta["article_index"] = i + 1
                    meta["article_label"] = article_no
                    meta["article_number"] = item.get("article_number") or 0
                    meta["source_path"] = page_url
                    meta["source_title"] = law_name
                    meta["source_type"] = item.get("category") or ""
                    meta["source_status"] = item.get("validity_status") or ""
                    meta["source_office"] = item.get("office") or ""
                    meta["source_office_level"] = item.get("office_level") or ""
                    meta["source_office_category"] = item.get("office_category") or ""
                    meta["source_publish_date"] = item.get("publish_date") or ""
                    meta["source_effective_date"] = item.get("effective_date") or ""
                    meta["source_effective_period"] = item.get("effective_period") or ""
                    meta["source_article_index"] = i + 1
                    for k in ("part_label", "part_title", "part_number",
                              "subpart_label", "subpart_title", "subpart_number",
                              "chapter_label", "chapter_title", "chapter_number",
                              "section_label", "section_title", "section_number"):
                        meta[k] = meta.get(k) or ""

            # ── 通用：embedding 后处理字段 ──
            text_to_embed = item.get("page_content") or item.get("content") or ""
            vec = CrawlService._call_embedding(text_to_embed) if text_to_embed else []
            if vec:
                item["vector-text-embedding-v4"] = vec
                item["_embedding_dimensions"] = len(vec)
                item["_embedding_model"] = "text-embedding-v4"
                item["_embedding_text_field"] = "page_content"

            enriched_items.append(item)

        return {**extracted, "result_json": {"items": enriched_items}}

    @staticmethod
    def _save_code_files(task_id: str, page_id: str, idx: int, markdown_text: str, page_url: str, title: str) -> None:
        """代码片段模式：从 Markdown 中提取 ```python ``` 代码块，每个写入独立 .py 文件。"""
        import re as _re
        import json as _json
        code_dir = Path("outputs") / task_id / "code"
        code_dir.mkdir(parents=True, exist_ok=True)

        # 提取所有代码块：```python ``` fence + 纯文本中的 Python 代码行
        blocks: list[str] = []

        # 方式1: ```python ... ``` fence
        fence_pattern = _re.compile(r"```(?:python|py)\s*\n(.*?)```", _re.DOTALL)
        blocks.extend(fence_pattern.findall(markdown_text))

        # 方式2: 从 HTML <pre><code> 或 readerlm 裸输出的 Python 代码行中提取
        # 匹配以 >>> 开头的 REPL 代码，或连续包含 python 关键字的行
        repl_pattern = _re.compile(r"(?:^|\n)(>>>\s+.+(?:\n(?:\.\.\.\s+.+|\s*$))*)", _re.MULTILINE)
        for m in repl_pattern.finditer(markdown_text):
            # 将 REPL 格式转为标准 python
            lines = []
            for line in m.group(1).strip().split("\n"):
                line = line.strip()
                if line.startswith(">>> "):
                    lines.append(line[4:])
                elif line.startswith("... "):
                    lines.append(line[4:])
                elif line and not lines:
                    lines.append(line)
            code = "\n".join(lines).strip()
            if code and len(code) > 10:
                blocks.append(code)

        if not blocks:
            return

        code_manifest: list[dict] = []
        for i, block in enumerate(blocks):
            code = block.strip()
            if not code:
                continue

            func_match = _re.search(r"def\s+(\w+)\s*\(", code)
            fname = f"{func_match.group(1)}.py" if func_match else f"snippet_{idx + 1}_{i + 1}.py"
            fpath = code_dir / fname
            n = 1
            stem, ext = fpath.stem, fpath.suffix
            while fpath.exists():
                fpath = code_dir / f"{stem}_{n}{ext}"
                n += 1

            fpath.write_text(code, encoding="utf-8")
            code_manifest.append({
                "index": i + 1, "filename": fpath.name,
                "path": str(fpath.relative_to(Path("outputs") / task_id)),
                "source_url": page_url, "title": title,
            })

        if code_manifest:
            (code_dir / "manifest.json").write_text(
                _json.dumps({"task_id": task_id, "code_files": code_manifest}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def _load_schedule_position_caches(self, schedule_id: str, query_signature: str) -> list[dict[str, Any]]:
        rows = self.db.scalars(
            select(ExtractionPositionCache)
            .where(
                ExtractionPositionCache.schedule_id == schedule_id,
                ExtractionPositionCache.query_signature == query_signature,
            )
            .order_by(ExtractionPositionCache.updated_at.desc()),
        ).all()
        return [
            {
                "source_url": row.source_url,
                "url_structure_key": row.url_structure_key,
                "position_paths": list(row.position_paths or []),
                "db_row": row,
            }
            for row in rows
        ]

    def _find_reusable_position_paths(
        self,
        current_url: str,
        position_cache_entries: list[dict[str, Any]],
    ) -> list[str] | None:
        current_key = build_url_structure_key(current_url)

        for entry in position_cache_entries:
            if entry["source_url"] == current_url:
                return list(entry["position_paths"])

        for entry in position_cache_entries:
            if entry["url_structure_key"] == current_key and are_urls_same_structure(current_url, entry["source_url"]):
                return list(entry["position_paths"])

        return None

    def _register_runtime_position_cache(
        self,
        position_cache_entries: list[dict[str, Any]],
        current_url: str,
        position_paths: list[str],
    ) -> None:
        if not position_paths:
            return

        current_key = build_url_structure_key(current_url)
        for entry in position_cache_entries:
            if entry["source_url"] == current_url:
                entry["position_paths"] = list(position_paths)
                entry["url_structure_key"] = current_key
                return
            if entry["url_structure_key"] == current_key and are_urls_same_structure(current_url, entry["source_url"]):
                entry["source_url"] = current_url
                entry["position_paths"] = list(position_paths)
                entry["url_structure_key"] = current_key
                return

        position_cache_entries.append(
            {
                "source_url": current_url,
                "url_structure_key": current_key,
                "position_paths": list(position_paths),
            },
        )

    def _upsert_schedule_position_cache(
        self,
        schedule_id: str,
        query_signature: str,
        current_url: str,
        position_paths: list[str],
        position_cache_entries: list[dict[str, Any]],
    ) -> None:
        if not position_paths:
            return

        current_key = build_url_structure_key(current_url)
        matched_entry = None
        for entry in position_cache_entries:
            if entry["source_url"] == current_url:
                matched_entry = entry
                break
            if entry["url_structure_key"] == current_key and are_urls_same_structure(current_url, entry["source_url"]):
                matched_entry = entry
                break

        now = datetime.utcnow()
        if matched_entry and matched_entry.get("db_row") is not None:
            row = matched_entry["db_row"]
            row.source_url = current_url
            row.url_structure_key = current_key
            row.position_paths = list(position_paths)
            row.hit_count = int(row.hit_count or 0) + 1
            row.last_used_at = now
            matched_entry["source_url"] = current_url
            matched_entry["url_structure_key"] = current_key
            matched_entry["position_paths"] = list(position_paths)
            return

        row = ExtractionPositionCache(
            schedule_id=schedule_id,
            query_signature=query_signature,
            source_url=current_url,
            url_structure_key=current_key,
            position_paths=list(position_paths),
            hit_count=1,
            last_used_at=now,
        )
        self.db.add(row)
        self.db.flush()
        position_cache_entries.append(
            {
                "source_url": current_url,
                "url_structure_key": current_key,
                "position_paths": list(position_paths),
                "db_row": row,
            },
        )

    def create_task(self, payload: dict, source: str = "manual", schedule_id: str | None = None) -> CrawlTask:
        # 规则：仅定时任务做任务内判重；一次性智能爬取不判重
        dedup_enabled = source == "schedule"

        task = CrawlTask(
            name=payload["name"],
            portal_url=str(payload["portal_url"]),
            query=payload["query"],
            output_mode=payload.get("output_mode", OutputMode.JSON),
            json_schema=payload.get("json_schema"),
            max_iterations=int(payload.get("max_iterations", 10)),
            dedup_enabled=dedup_enabled,
            dedup_scope=payload.get("dedup_scope", "global"),
            hash_mode=payload.get("hash_mode", "raw+normalized"),
            source=source,
            schedule_id=schedule_id,
        )
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def create_run(self, task_id: str) -> CrawlRun:
        run = CrawlRun(task_id=task_id, status=TaskStatus.PENDING)
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def log_event(self, task_id: str, event_type: str, message: str, level: str = "INFO") -> None:
        log = TaskEventLog(task_id=task_id, event_type=event_type, message=message, level=level)
        self.db.add(log)
        self.db.commit()

    def _fetch_portal_snapshot(self, portal_url: str) -> tuple[str, str | None, str | None]:
        response = requests.get(portal_url, timeout=10)
        response.raise_for_status()
        etag = response.headers.get("ETag")
        last_modified = response.headers.get("Last-Modified")
        soup = BeautifulSoup(response.text, "html.parser")
        text = " ".join(soup.get_text(" ").split())
        return text[:5000], etag, last_modified

    def check_site_change(self, schedule_id: str, portal_url: str, strategy: str) -> tuple[bool, str]:
        text_snapshot, etag, last_modified = self._fetch_portal_snapshot(portal_url)
        current_hash = build_site_quick_hash(
            portal_url=portal_url,
            text_snapshot=text_snapshot,
            etag=etag,
            last_modified=last_modified,
            strategy=strategy,
        )

        last_checkpoint = self.db.scalar(
            select(SiteCheckpoint)
            .where(SiteCheckpoint.schedule_id == schedule_id)
            .order_by(SiteCheckpoint.checked_at.desc())
            .limit(1),
        )
        changed = last_checkpoint is None or last_checkpoint.site_quick_hash != current_hash

        checkpoint = SiteCheckpoint(
            schedule_id=schedule_id,
            portal_url=portal_url,
            site_quick_hash=current_hash,
            check_method=strategy,
        )
        self.db.add(checkpoint)
        self.db.commit()
        return changed, current_hash

    def _find_duplicate_reason(
        self,
        task: CrawlTask,
        raw_hash: str,
        normalized_hash: str,
    ) -> DuplicateReason:
        if not task.dedup_enabled:
            return DuplicateReason.NONE

        # 按用户要求：仅在同一个 task_id 范围内判重，不跨任务比较
        base_query = select(CrawlPage).where(CrawlPage.task_id == task.id)

        raw_exists = self.db.scalar(base_query.where(CrawlPage.raw_html_hash == raw_hash).limit(1))
        if raw_exists:
            return DuplicateReason.RAW_MATCH

        if task.hash_mode != "raw_only":
            norm_exists = self.db.scalar(
                base_query.where(CrawlPage.normalized_content_hash == normalized_hash).limit(1),
            )
            if norm_exists:
                return DuplicateReason.NORMALIZED_MATCH

        return DuplicateReason.NONE

    def execute_task_sync(
        self,
        task_id: str,
        run_id: str,
        site_change_check: dict[str, Any] | None = None,
        storage_db_type_override: str | None = None,
    ) -> CrawlTask:
        task = self.db.get(CrawlTask, task_id)
        run = self.db.get(CrawlRun, run_id)
        if task is None or run is None:
            raise ValueError("task or run not found")

        task.status = TaskStatus.RUNNING
        task.started_at = datetime.utcnow()
        task.progress = 5
        run.status = TaskStatus.RUNNING
        run.started_at = datetime.utcnow()
        self.db.commit()

        try:
            model_config_service = ModelConfigService(self.db)
            crawler_agent_config = model_config_service.get_runtime_config(ModelConfigTarget.CRAWLER_AGENT)
            recursive_config = None
            query_signature = self._build_query_signature(task.query, task.json_schema)
            position_cache_entries: list[dict[str, Any]] = []
            if task.output_mode == OutputMode.JSON:
                recursive_config = model_config_service.get_runtime_config(ModelConfigTarget.RECURSIVE_ACQUISITION)
                if task.schedule_id:
                    position_cache_entries = self._load_schedule_position_caches(task.schedule_id, query_signature)

            if site_change_check and site_change_check.get("enabled") and task.schedule_id:
                changed, _ = self.check_site_change(
                    schedule_id=task.schedule_id,
                    portal_url=task.portal_url,
                    strategy=site_change_check.get("strategy", "content_only"),
                )
                run.site_changed = changed
                if not changed:
                    msg = "site quick hash unchanged, skip current run"
                    task.status = TaskStatus.SKIPPED_NO_CHANGE
                    task.skip_reason = "NO_CHANGE"
                    task.progress = 100
                    run.status = TaskStatus.SKIPPED_NO_CHANGE
                    run.skip_reason = "NO_CHANGE"
                    run.finished_at = datetime.utcnow()
                    task.finished_at = datetime.utcnow()
                    self.log_event(task.id, "SKIP", msg)
                    self.db.commit()
                    return task

            pages = collect_pages_sync(
                query=task.query,
                portal_url=task.portal_url,
                model_config=crawler_agent_config,
                max_iters=task.max_iterations,
            )
            if not pages:
                raise ValueError("未收集到任何候选页面，请检查站点可达性、查询条件或模型配置是否可用")
            self.log_event(task.id, "COLLECT", f"collected candidate pages: {len(pages)}")

            # 代码页面快速通道：检测到 <pre>/<code>/w3-code 标签直接写 .py 并完成
            # 仅 Markdown 模式 + 页面含多个代码块才走代码快速通道
            is_code_mode = task.output_mode == OutputMode.MARKDOWN
            has_code = is_code_mode and any(
                p.get("html") and len(re.findall(
                    r'<(pre|code)\b|<div[^>]+class="[^"]*\bcode\b[^"]*"', p["html"], re.I
                )) >= 2 for p in pages
            )
            if has_code:
                new_count = 0
                for p in pages:
                    url = p.get("url") or task.portal_url
                    title = p.get("title") or ""
                    html = p.get("html") or ""
                    if not html: continue
                    try:
                        from bs4 import BeautifulSoup as _BS
                        from html import unescape as _unescape
                        soup = _BS(html, "html.parser")
                        code_dir = Path("outputs") / task.id / "code"
                        code_dir.mkdir(parents=True, exist_ok=True)
                        seen = set()
                        ci = 0
                        for tag in soup.find_all(["pre", "code", "div"]):
                            is_code = tag.name in ("pre", "code")
                            if tag.name == "div":
                                classes = " ".join(tag.get("class") or [])
                                is_code = "code" in classes.lower()
                            if not is_code: continue
                            text = _unescape(tag.get_text()).strip()
                            if text and len(text) > 10 and any(kw in text for kw in ("def ","print","import ","class ",">>>","=")):
                                hh = hash(text[:200])
                                if hh in seen: continue
                                seen.add(hh)
                                ci += 1
                                fm = re.search(r"def\s+(\w+)\s*\(", text)
                                fn = f"{fm.group(1)}.py" if fm else f"snippet_{task.id[:8]}_{ci}.py"
                                fp = code_dir / fn; n = 1; st, ex = fp.stem, fp.suffix
                                while fp.exists(): fp = code_dir / f"{st}_{n}{ex}"; n += 1
                                fp.write_text(text, encoding="utf-8")
                        new_count += max(1, ci)
                    except Exception:
                        pass
                task.status = TaskStatus.SUCCEEDED
                task.progress = 100
                task.result_summary = f"new_pages={new_count}, code_files_extracted"
                task.finished_at = datetime.utcnow()
                run.status = TaskStatus.SUCCEEDED
                run.new_pages_count = new_count
                run.finished_at = datetime.utcnow()
                self.db.commit()
                return task
            task.progress = 35
            self.db.commit()

            new_count = 0
            duplicate_count = 0
            unchanged_count = 0

            storage_service = StorageService(self.db)

            total_pages = len(pages) or 1
            for idx, page in enumerate(pages):
                url = page.get("url") or task.portal_url
                title = page.get("title")
                html = page.get("html") or ""

                raw_hash = build_raw_html_hash(url, html)
                normalized_hash = build_normalized_content_hash(html)

                duplicate_reason = self._find_duplicate_reason(task, raw_hash, normalized_hash)
                is_duplicate = duplicate_reason != DuplicateReason.NONE

                page_row = CrawlPage(
                    task_id=task.id,
                    run_id=run.id,
                    url=url,
                    title=title,
                    html_content=html,
                    raw_html_hash=raw_hash,
                    normalized_content_hash=normalized_hash,
                    is_duplicate=is_duplicate,
                    duplicate_reason=duplicate_reason.value,
                )
                self.db.add(page_row)
                self.db.flush()

                if is_duplicate:
                    duplicate_count += 1
                    if duplicate_reason == DuplicateReason.NORMALIZED_MATCH:
                        unchanged_count += 1
                    self.log_event(task.id, "DEDUP", f"skip duplicate page: {url} ({duplicate_reason.value})")
                else:
                    if task.output_mode == OutputMode.DOWNLOAD:
                        # download 模式：Agent 已在导航阶段下载文件，跳过页面提取
                        new_count += 1
                        continue
                    elif task.output_mode == OutputMode.HTML:
                        extracted = extract_html(url=url, html=html)
                    elif task.output_mode == OutputMode.MARKDOWN:
                        # 检测是否代码页面（含大量 <pre>/<code>/w3-code），是则跳过 ReaderLM
                        code_page = bool(re.search(
                            r'<(pre|code)\b|<div[^>]+class="[^"]*\bcode\b[^"]*"', html or "", re.I
                        )) if html else False
                        if code_page:
                            extracted = {"result_type": "markdown", "result_markdown": html,
                                         "result_markdown_ocr": None, "result_json": None}
                        else:
                            extracted = extract_markdown(url=url, html=html)
                    else:
                        reusable_position_paths = self._find_reusable_position_paths(url, position_cache_entries)
                        extracted = extract_json(
                            url=url,
                            html=html,
                            query=task.query,
                            model_config=recursive_config,
                            json_schema=task.json_schema,
                            position_paths=reusable_position_paths,
                        )
                        extracted_position_paths = list(extracted.get("position_paths") or [])
                        if extracted_position_paths:
                            self._register_runtime_position_cache(position_cache_entries, url, extracted_position_paths)
                            if task.schedule_id:
                                self._upsert_schedule_position_cache(
                                    schedule_id=task.schedule_id,
                                    query_signature=query_signature,
                                    current_url=url,
                                    position_paths=extracted_position_paths,
                                    position_cache_entries=position_cache_entries,
                                )
                        # JSON 模式后处理：补全 LLM 无法生成的字段
                        extracted = self._enrich_json_result(extracted, idx, url)

                    # 兜底 result_type
                    output_mode_value = task.output_mode.value if hasattr(task.output_mode, "value") else str(task.output_mode)
                    if not extracted.get("result_type"):
                        extracted["result_type"] = output_mode_value

                    # 始终写入数据库
                    result_row = CrawlResult(
                        task_id=task.id,
                        page_id=page_row.id,
                        result_type=extracted.get("result_type"),
                        result_json=extracted.get("result_json"),
                        result_markdown=extracted.get("result_markdown"),
                        result_markdown_ocr=extracted.get("result_markdown_ocr"),
                    )
                    self.db.add(result_row)

                    use_file_output = not storage_db_type_override
                    if use_file_output:
                        # 代码片段模式：直接从原始 HTML 提取 <pre>/<code>/<div class="*-code-*"> 写 .py
                        if html:
                            try:
                                from bs4 import BeautifulSoup
                                from html import unescape
                                soup = BeautifulSoup(html, "html.parser")
                                code_blocks = []
                                for tag in soup.find_all(["pre", "code", "div"]):
                                    is_code = tag.name in ("pre", "code")
                                    if tag.name == "div":
                                        classes = " ".join(tag.get("class") or [])
                                        is_code = "code" in classes.lower()
                                    if not is_code:
                                        continue
                                    text = unescape(tag.get_text()).strip()
                                    if text and len(text) > 10 and any(kw in text for kw in ("def ","print","import ","class ",">>>","=")):
                                        code_blocks.append(text)
                                if code_blocks:
                                    code_dir = Path("outputs") / task.id / "code"
                                    code_dir.mkdir(parents=True, exist_ok=True)
                                    seen = set()
                                    for ci, c in enumerate(code_blocks):
                                        h = hash(c[:200])
                                        if h in seen: continue
                                        seen.add(h)
                                        import re as _ccre
                                        fm = _ccre.search(r"def\s+(\w+)\s*\(", c)
                                        fn = f"{fm.group(1)}.py" if fm else f"snippet_{page_row.id[:8]}_{ci+1}.py"
                                        fp = code_dir / fn
                                        n = 1; st, ex = fp.stem, fp.suffix
                                        while fp.exists():
                                            fp = code_dir / f"{st}_{n}{ex}"; n += 1
                                        fp.write_text(c, encoding="utf-8")
                            except Exception:
                                pass

                        # 本地文件保存 + manifest
                        paths = self._save_result_to_file(task.id, page_row.id, idx, extracted)
                        # 同时从 Markdown 和原始 HTML 提取图片并下载
                        md_text = extracted.get("result_markdown") or ""
                        if html or md_text:
                            self._download_images(task.id, page_row.id, idx, md_text, url, html)
                        self._update_manifest(task.id, page_row.id, idx, url, title or "", extracted, paths)
                    else:
                        storage_service.write_to_external_storage(
                            storage_db_type_override=storage_db_type_override,
                            task_id=task.id,
                            page_url=url,
                            title=title,
                            raw_html_hash=raw_hash,
                            normalized_content_hash=normalized_hash,
                            result_type=result_row.result_type,
                            result_json=result_row.result_json,
                            result_markdown=result_row.result_markdown,
                        )
                    new_count += 1

                task.progress = 35 + int((idx + 1) / total_pages * 60)
                self.db.commit()

            run.new_pages_count = new_count
            run.duplicate_pages_count = duplicate_count
            run.unchanged_pages_count = unchanged_count
            run.status = TaskStatus.SUCCEEDED
            run.finished_at = datetime.utcnow()

            task.status = TaskStatus.SUCCEEDED
            task.progress = 100
            task.result_summary = (
                f"new_pages={new_count}, duplicate_pages={duplicate_count}, unchanged_pages={unchanged_count}"
            )
            task.finished_at = datetime.utcnow()

            self.log_event(task.id, "DONE", task.result_summary)

            # 自动同步已提取的页面结果到 MySQL（已配置时静默写入）
            self._sync_to_mysql(task.id)

            # download 模式：把全局 downloads/ 中本次下载的文件移到任务专属目录
            if task.output_mode == OutputMode.DOWNLOAD:
                import shutil
                dl_src = Path("downloads")
                dl_dst = Path("outputs") / task.id / "downloads"
                if dl_src.exists():
                    dl_dst.mkdir(parents=True, exist_ok=True)
                    record_time = (task.started_at or task.created_at).timestamp()
                    for f in dl_src.rglob("*"):
                        if f.is_file() and f.stat().st_mtime >= record_time:
                            shutil.move(str(f), str(dl_dst / f.name))
            self.db.commit()
            self.db.refresh(task)
            return task
        except Exception as exc:
            task.status = TaskStatus.FAILED
            task.error_message = str(exc)
            task.finished_at = datetime.utcnow()
            task.progress = 100
            run.status = TaskStatus.FAILED
            run.finished_at = datetime.utcnow()
            self.log_event(task.id, "ERROR", str(exc), level="ERROR")
            self.db.commit()
            self.db.refresh(task)
            return task


def run_task_blocking(
    task_id: str,
    run_id: str,
    site_change_check: dict[str, Any] | None = None,
    storage_db_type_override: str | None = None,
) -> None:
    db = SessionLocal()
    try:
        CrawlService(db).execute_task_sync(
            task_id=task_id,
            run_id=run_id,
            site_change_check=site_change_check,
            storage_db_type_override=storage_db_type_override,
        )
    finally:
        db.close()


class TaskExecutor:
    def __init__(self, semaphore_size: int = 2):
        self.semaphore = asyncio.Semaphore(semaphore_size)
        self.background_tasks: dict[str, asyncio.Task] = {}

    def submit(self, key: str, coro):
        async def wrapped():
            async with self.semaphore:
                await coro

        task = asyncio.create_task(wrapped())
        self.background_tasks[key] = task
        return task


executor = TaskExecutor()
