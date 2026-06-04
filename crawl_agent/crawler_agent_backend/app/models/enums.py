from enum import Enum


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"
    SKIPPED_NO_CHANGE = "SKIPPED_NO_CHANGE"


class ScheduleStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"


class ScheduleType(str, Enum):
    CRON = "cron"
    INTERVAL = "interval"


class OutputMode(str, Enum):
    JSON = "json"
    MARKDOWN = "markdown"
    HTML = "html"


class StorageConfigType(str, Enum):
    MYSQL = "mysql"
    MILVUS = "milvus"


class ModelConfigTarget(str, Enum):
    CRAWLER_AGENT = "crawler_agent"
    RECURSIVE_ACQUISITION = "recursive_acquisition"


class DuplicateReason(str, Enum):
    NONE = "NONE"
    RAW_MATCH = "RAW_MATCH"
    NORMALIZED_MATCH = "NORMALIZED_MATCH"
