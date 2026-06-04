from __future__ import annotations

import time
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.milvus_writer import MilvusWriter
from app.adapters.mysql_writer import MySQLWriter
from app.models.enums import StorageConfigType
from app.models.storage import StorageConfig
from app.utils.embedding_utils import chunk_text, fake_embedding
from app.utils.hash_utils import sha256_text


def mask_conn_json(db_type: StorageConfigType, conn: dict) -> dict:
    masked = dict(conn)
    if db_type == StorageConfigType.MYSQL and "password" in masked:
        masked["password"] = "******"
    if db_type == StorageConfigType.MILVUS and "token" in masked and masked["token"]:
        masked["token"] = "******"
    return masked


class StorageService:
    def __init__(self, db: Session):
        self.db = db

    def create_mysql_config(self, payload: dict) -> StorageConfig:
        cfg = StorageConfig(name=payload["name"], db_type=StorageConfigType.MYSQL, conn_json=payload)
        self.db.add(cfg)
        self.db.commit()
        self.db.refresh(cfg)
        return cfg

    def create_milvus_config(self, payload: dict) -> StorageConfig:
        cfg = StorageConfig(name=payload["name"], db_type=StorageConfigType.MILVUS, conn_json=payload)
        self.db.add(cfg)
        self.db.commit()
        self.db.refresh(cfg)
        return cfg

    def list_configs(self) -> list[StorageConfig]:
        return self.db.scalars(select(StorageConfig).order_by(StorageConfig.created_at.desc())).all()

    def get_config(self, config_id: str) -> StorageConfig | None:
        return self.db.get(StorageConfig, config_id)

    def get_raw_config(self, config_id: str) -> StorageConfig | None:
        return self.db.get(StorageConfig, config_id)

    def update_config(self, config_id: str, payload: dict) -> StorageConfig | None:
        row = self.db.get(StorageConfig, config_id)
        if row is None:
            return None
        row.conn_json = payload
        row.name = payload.get("name", row.name)
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete_config(self, config_id: str) -> bool:
        row = self.db.get(StorageConfig, config_id)
        if row is None:
            return False
        self.db.delete(row)
        self.db.commit()
        return True

    def test_connection(self, config_id: str) -> tuple[bool, str, int | None]:
        row = self.db.get(StorageConfig, config_id)
        if row is None:
            return False, "config not found", None

        started = time.perf_counter()
        try:
            if row.db_type == StorageConfigType.MYSQL:
                writer = MySQLWriter(row.conn_json)
                ok, msg = writer.test_connection()
            else:
                writer = MilvusWriter(row.conn_json)
                ok, msg = writer.test_connection()
            latency = int((time.perf_counter() - started) * 1000)
            row.last_test_status = "success" if ok else "failed"
            row.last_test_at = datetime.utcnow()
            self.db.commit()
            return ok, msg, latency
        except Exception as exc:
            latency = int((time.perf_counter() - started) * 1000)
            row.last_test_status = "failed"
            row.last_test_at = datetime.utcnow()
            self.db.commit()
            return False, str(exc), latency

    def resolve_config_by_type(self, db_type: StorageConfigType) -> StorageConfig | None:
        default_cfg = self.db.scalar(
            select(StorageConfig)
            .where(StorageConfig.db_type == db_type, StorageConfig.is_enabled.is_(True), StorageConfig.is_default.is_(True))
            .order_by(StorageConfig.created_at.desc())
            .limit(1),
        )
        if default_cfg:
            return default_cfg
        return self.db.scalar(
            select(StorageConfig)
            .where(StorageConfig.db_type == db_type, StorageConfig.is_enabled.is_(True))
            .order_by(StorageConfig.created_at.desc())
            .limit(1),
        )

    def write_to_external_storage(
        self,
        storage_db_type_override: str | None,
        task_id: str,
        page_url: str,
        title: str | None,
        raw_html_hash: str,
        normalized_content_hash: str,
        result_type: str,
        result_json: dict | list | None,
        result_markdown: str | None,
    ) -> dict:
        if storage_db_type_override not in ("mysql", "milvus"):
            return {"written": False, "reason": "storage_db_type must be mysql or milvus"}

        if storage_db_type_override == "mysql":
            mysql_cfg = self.resolve_config_by_type(StorageConfigType.MYSQL)
            if not mysql_cfg:
                return {"written": False, "reason": "no mysql config"}
            writer = MySQLWriter(mysql_cfg.conn_json)
            writer.write_content(
                task_id=task_id,
                page_url=page_url,
                title=title,
                raw_html_hash=raw_html_hash,
                normalized_content_hash=normalized_content_hash,
                result_type=result_type,
                result_json=result_json,
                result_markdown=result_markdown,
            )
            return {"written": True, "mysql": True, "milvus": False}

        milvus_cfg = self.resolve_config_by_type(StorageConfigType.MILVUS)
        if not milvus_cfg:
            return {"written": False, "reason": "no milvus config"}
        if result_markdown:
            writer = MilvusWriter(milvus_cfg.conn_json)
            chunks = chunk_text(result_markdown)
            for chunk in chunks:
                chunk_hash = sha256_text(chunk)
                emb = fake_embedding(chunk, dim=milvus_cfg.conn_json.get("dimension", 1024))
                writer.insert_chunk(
                    task_id=task_id,
                    page_url=page_url,
                    chunk_hash=chunk_hash,
                    chunk_text=chunk,
                    embedding=emb,
                )
            return {"written": True, "mysql": False, "milvus": True}
        return {"written": False, "reason": "milvus needs markdown text"}
