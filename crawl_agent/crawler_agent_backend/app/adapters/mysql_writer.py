from __future__ import annotations

import json
from datetime import datetime
from sqlalchemy import create_engine, text


class MySQLWriter:
    def __init__(self, conn: dict):
        self.conn = conn
        self.url = (
            f"mysql+pymysql://{conn['username']}:{conn['password']}"
            f"@{conn['host']}:{conn['port']}/{conn['database']}?charset={conn.get('charset', 'utf8mb4')}"
        )
        self.engine = create_engine(self.url, pool_pre_ping=True)

    def test_connection(self) -> tuple[bool, str]:
        with self.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "mysql connection ok"

    def ensure_table(self) -> None:
        ddl = """
        CREATE TABLE IF NOT EXISTS external_crawl_content (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            task_id VARCHAR(36) NOT NULL,
            page_url TEXT NOT NULL,
            title TEXT NULL,
            raw_html_hash VARCHAR(64) NOT NULL,
            normalized_content_hash VARCHAR(64) NOT NULL,
            result_type VARCHAR(32) NOT NULL,
            result_json JSON NULL,
            result_markdown LONGTEXT NULL,
            created_at DATETIME NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        with self.engine.begin() as conn:
            conn.execute(text(ddl))

    def write_content(
        self,
        task_id: str,
        page_url: str,
        title: str | None,
        raw_html_hash: str,
        normalized_content_hash: str,
        result_type: str,
        result_json: dict | list | None,
        result_markdown: str | None,
    ) -> None:
        self.ensure_table()
        # PyMySQL + text() 下直接传 list/dict 可能触发 SQL 操作数错误，统一序列化为 JSON 字符串。
        result_json_payload = None if result_json is None else json.dumps(result_json, ensure_ascii=False)
        sql = text(
            """
            INSERT INTO external_crawl_content (
                task_id, page_url, title, raw_html_hash, normalized_content_hash,
                result_type, result_json, result_markdown, created_at
            ) VALUES (
                :task_id, :page_url, :title, :raw_html_hash, :normalized_content_hash,
                :result_type, :result_json, :result_markdown, :created_at
            )
            """
        )
        with self.engine.begin() as conn:
            conn.execute(
                sql,
                {
                    "task_id": task_id,
                    "page_url": page_url,
                    "title": title,
                    "raw_html_hash": raw_html_hash,
                    "normalized_content_hash": normalized_content_hash,
                    "result_type": result_type,
                    "result_json": result_json_payload,
                    "result_markdown": result_markdown,
                    "created_at": datetime.utcnow(),
                },
            )
