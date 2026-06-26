from __future__ import annotations

import json
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from urllib.parse import quote_plus

from app.models.enums import StorageConfigType
from app.services.storage_service import StorageService


class DatasetService:
    """Read-only query service for external_crawl_content in MySQL."""

    def __init__(self, db: Session):
        self.db = db

    def _get_mysql_engine(self):
        """Resolve MySQL config from metadata DB and create a SQLAlchemy engine.

        Reuses the same connection pattern as MySQLWriter / StorageService.
        """
        storage_svc = StorageService(self.db)
        mysql_cfg = storage_svc.resolve_config_by_type(StorageConfigType.MYSQL)
        if not mysql_cfg:
            raise RuntimeError("No enabled MySQL storage config found")
        conn = mysql_cfg.conn_json
        url = (
            f"mysql+pymysql://{conn['username']}:{quote_plus(conn['password'])}"
            f"@{conn['host']}:{conn['port']}/{conn['database']}"
            f"?charset={conn.get('charset', 'utf8mb4')}"
        )
        return create_engine(url, pool_pre_ping=True)

    def list_records(
        self,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
        result_type: str | None = None,
    ) -> dict[str, Any]:
        offset = (page - 1) * page_size

        where_parts: list[str] = ["1=1"]
        params: dict[str, Any] = {}

        if result_type and result_type != "all":
            where_parts.append("result_type = :result_type")
            params["result_type"] = result_type

        if keyword:
            like = f"%{keyword}%"
            where_parts.append(
                "("
                "title LIKE :kw_title OR "
                "page_url LIKE :kw_url OR "
                "result_markdown LIKE :kw_md OR "
                "result_html LIKE :kw_html OR "
                "CAST(result_json AS CHAR) LIKE :kw_json"
                ")",
            )
            params["kw_title"] = like
            params["kw_url"] = like
            params["kw_md"] = like
            params["kw_html"] = like
            params["kw_json"] = like

        where_clause = " AND ".join(where_parts)

        count_sql = text(
            f"SELECT COUNT(*) AS total FROM external_crawl_content WHERE {where_clause}"
        )

        list_sql = text(
            f"""
            SELECT
                id, task_id, page_url, title,
                raw_html_hash, normalized_content_hash, result_type,
                result_json, result_markdown, result_html, created_at
            FROM external_crawl_content
            WHERE {where_clause}
            ORDER BY created_at DESC, id DESC
            LIMIT :page_size OFFSET :offset
            """
        )

        engine = self._get_mysql_engine()
        with engine.connect() as conn:
            total_row = conn.execute(count_sql, params).fetchone()
            total = total_row[0] if total_row else 0

            list_params = dict(params)
            list_params["page_size"] = page_size
            list_params["offset"] = offset
            rows = conn.execute(list_sql, list_params).fetchall()

        items = []
        for row in rows:
            items.append({
                "id": row[0],
                "task_id": row[1],
                "page_url": row[2],
                "title": row[3],
                "raw_html_hash": row[4],
                "normalized_content_hash": row[5],
                "result_type": row[6],
                "content_preview": self._build_preview(row[6], row[7], row[8], row[9]),
                "created_at": row[10],
            })

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_record(self, record_id: int) -> dict[str, Any] | None:
        sql = text(
            """
            SELECT
                id, task_id, page_url, title,
                raw_html_hash, normalized_content_hash, result_type,
                result_json, result_markdown, result_html, created_at
            FROM external_crawl_content
            WHERE id = :record_id
            LIMIT 1
            """
        )

        engine = self._get_mysql_engine()
        with engine.connect() as conn:
            row = conn.execute(sql, {"record_id": record_id}).fetchone()

        if not row:
            return None

        return {
            "id": row[0],
            "task_id": row[1],
            "page_url": row[2],
            "title": row[3],
            "raw_html_hash": row[4],
            "normalized_content_hash": row[5],
            "result_type": row[6],
            "result_json": row[7],
            "result_markdown": row[8],
            "result_html": row[9],
            "created_at": row[10],
        }

    def get_stats(self) -> dict[str, Any]:
        sql = text(
            """
            SELECT
                COUNT(*) AS total_records,
                COUNT(DISTINCT task_id) AS task_count,
                SUM(CASE WHEN result_type = 'markdown' THEN 1 ELSE 0 END) AS markdown_count,
                SUM(CASE WHEN result_type = 'json' THEN 1 ELSE 0 END) AS json_count,
                SUM(CASE WHEN result_type = 'html' THEN 1 ELSE 0 END) AS html_count,
                MAX(created_at) AS latest_created_at
            FROM external_crawl_content
            """
        )

        engine = self._get_mysql_engine()
        with engine.connect() as conn:
            row = conn.execute(sql).fetchone()

        return {
            "total_records": row[0] or 0,
            "task_count": row[1] or 0,
            "markdown_count": row[2] or 0,
            "json_count": row[3] or 0,
            "html_count": row[4] or 0,
            "latest_created_at": row[5],
        }

    @staticmethod
    def _build_preview(
        result_type: str | None,
        result_json: Any,
        result_markdown: str | None,
        result_html: str | None,
    ) -> str | None:
        if result_type == "markdown" and result_markdown:
            return result_markdown[:300]
        if result_type == "html" and result_html:
            return result_html[:300]
        if result_type == "json" and result_json is not None:
            value = result_json if isinstance(result_json, str) else json.dumps(result_json, ensure_ascii=False)
            return value[:300]
        # fallback
        for value in [result_markdown, result_html, result_json]:
            if value:
                text_val = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
                return text_val[:300]
        return None
