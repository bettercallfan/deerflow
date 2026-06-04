from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MilvusCollectionConfig:
    collection_name: str
    dimension: int
    metric_type: str
    index_type: str


class MilvusWriter:
    def __init__(self, conn: dict):
        try:
            from pymilvus import connections
        except ImportError as exc:
            raise RuntimeError("pymilvus is not installed") from exc

        self._connections = connections
        self.conn = conn
        self.alias = f"milvus_{conn.get('collection_prefix', 'crawler')}"

    def connect(self):
        kwargs = {"uri": self.conn["uri"]}
        if self.conn.get("token"):
            kwargs["token"] = self.conn["token"]
        self._connections.connect(alias=self.alias, **kwargs)

    def test_connection(self) -> tuple[bool, str]:
        self.connect()
        from pymilvus import utility

        utility.list_collections(using=self.alias)
        return True, "milvus connection ok"

    def _ensure_collection(self, cfg: MilvusCollectionConfig):
        from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, utility

        self.connect()
        if utility.has_collection(cfg.collection_name, using=self.alias):
            return Collection(cfg.collection_name, using=self.alias)

        fields = [
            FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=64, is_primary=True, auto_id=False),
            FieldSchema(name="task_id", dtype=DataType.VARCHAR, max_length=36),
            FieldSchema(name="page_url", dtype=DataType.VARCHAR, max_length=2048),
            FieldSchema(name="chunk_hash", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="chunk_text", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=cfg.dimension),
        ]
        schema = CollectionSchema(fields=fields, description="crawler chunks")
        collection = Collection(name=cfg.collection_name, schema=schema, using=self.alias)
        index_params = {"index_type": cfg.index_type, "metric_type": cfg.metric_type, "params": {}}
        collection.create_index(field_name="embedding", index_params=index_params)
        collection.load()
        return collection

    def insert_chunk(
        self,
        task_id: str,
        page_url: str,
        chunk_hash: str,
        chunk_text: str,
        embedding: list[float],
    ) -> None:
        cfg = MilvusCollectionConfig(
            collection_name=f"{self.conn.get('collection_prefix', 'crawler')}_chunks",
            dimension=self.conn.get("dimension", 1024),
            metric_type=self.conn.get("metric_type", "IP"),
            index_type=self.conn.get("index_type", "AUTOINDEX"),
        )
        collection = self._ensure_collection(cfg)
        row_id = f"{task_id}_{chunk_hash[:24]}"
        collection.insert([[row_id], [task_id], [page_url], [chunk_hash], [chunk_text], [embedding]])
