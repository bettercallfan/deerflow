from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

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
    def _save_result_to_file(task_id: str, page_id: str, idx: int, extracted: dict) -> None:
        output_dir = Path("outputs") / task_id
        output_dir.mkdir(parents=True, exist_ok=True)

        result_type = extracted.get("result_type", "unknown")

        if result_type == "html" and extracted.get("result_html"):
            file_path = output_dir / f"page_{idx + 1}.html"
            file_path.write_text(extracted["result_html"], encoding="utf-8")

        elif result_type == "markdown":
            if extracted.get("result_markdown"):
                file_path = output_dir / f"page_{idx + 1}.md"
                file_path.write_text(extracted["result_markdown"], encoding="utf-8")
            if extracted.get("result_markdown_ocr"):
                file_path = output_dir / f"page_{idx + 1}_ocr.md"
                file_path.write_text(extracted["result_markdown_ocr"], encoding="utf-8")

        elif result_type == "json" and extracted.get("result_json"):
            file_path = output_dir / f"page_{idx + 1}.json"
            file_path.write_text(json.dumps(extracted["result_json"], ensure_ascii=False, indent=2), encoding="utf-8")

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
            )
            if not pages:
                raise ValueError("未收集到任何候选页面，请检查站点可达性、查询条件或模型配置是否可用")
            self.log_event(task.id, "COLLECT", f"collected candidate pages: {len(pages)}")
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
                    if task.output_mode == OutputMode.HTML:
                        extracted = extract_html(url=url, html=html)
                    elif task.output_mode == OutputMode.MARKDOWN:
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

                    use_file_output = not storage_db_type_override
                    if use_file_output:
                        self._save_result_to_file(task.id, page_row.id, idx, extracted)
                    else:
                        result_row = CrawlResult(
                            task_id=task.id,
                            page_id=page_row.id,
                            result_type=extracted["result_type"],
                            result_json=extracted.get("result_json"),
                            result_markdown=extracted.get("result_markdown"),
                            result_markdown_ocr=extracted.get("result_markdown_ocr"),
                        )
                        self.db.add(result_row)

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
