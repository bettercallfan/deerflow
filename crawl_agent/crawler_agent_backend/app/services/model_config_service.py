from __future__ import annotations

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session
from openai import OpenAI

from app.models.enums import ModelConfigTarget, OutputMode
from app.models.model_config import ModelConfig


MODEL_CONFIG_LABELS = {
    ModelConfigTarget.CRAWLER_AGENT: "Agent导航模型",
    ModelConfigTarget.RECURSIVE_ACQUISITION: "单页面信息抽取模型",
}


class ModelConfigService:
    def __init__(self, db: Session):
        self.db = db

    def _build_effective_runtime_config(self, target: ModelConfigTarget, payload: dict) -> dict[str, str]:
        row = self.get_config(target)
        effective_api_key = (payload.get("api_key") or "").strip() or (row.api_key.strip() if row else "")
        effective_base_url = (payload.get("base_url") or "").strip() or (row.base_url.strip() if row else "")
        effective_model_name = (payload.get("model_name") or "").strip() or (row.model_name.strip() if row else "")
        return {
            "api_key": effective_api_key,
            "base_url": effective_base_url,
            "model_name": effective_model_name,
        }

    def _validate_runtime_config(self, target: ModelConfigTarget, runtime_config: dict[str, str]) -> None:
        missing_fields = [key for key, value in runtime_config.items() if not value]
        if missing_fields:
            missing_text = "、".join(missing_fields)
            raise ValueError(f"{MODEL_CONFIG_LABELS[target]}缺少 {missing_text}，请补全后再验证保存")

        try:
            http_client = httpx.Client(
                timeout=httpx.Timeout(30.0, connect=15.0),
                limits=httpx.Limits(max_keepalive_connections=2, max_connections=5),
                transport=httpx.HTTPTransport(retries=1),
            )
            client = OpenAI(
                api_key=runtime_config["api_key"],
                base_url=runtime_config["base_url"],
                http_client=http_client,
            )
            response = client.chat.completions.create(
                model=runtime_config["model_name"],
                messages=[{"role": "user", "content": "请回复 ok"}],
                max_tokens=8,
                timeout=30,
            )
            if not response.choices:
                raise ValueError("模型没有返回可用结果")
        except Exception as exc:
            raise ValueError(f"{MODEL_CONFIG_LABELS[target]}验证失败：{exc}") from exc

    def get_config(self, target: ModelConfigTarget) -> ModelConfig | None:
        return self.db.scalar(select(ModelConfig).where(ModelConfig.target == target).limit(1))

    def list_configs(self) -> list[ModelConfig]:
        return self.db.scalars(select(ModelConfig).order_by(ModelConfig.created_at.asc())).all()

    def upsert_config(self, target: ModelConfigTarget, payload: dict) -> ModelConfig:
        row = self.get_config(target)
        api_key = (payload.get("api_key") or "").strip()
        base_url = (payload.get("base_url") or "").strip()
        model_name = (payload.get("model_name") or "").strip()

        if not base_url or not model_name:
            raise ValueError("base_url 与 model_name 不能为空")

        if row is None and not api_key:
            raise ValueError("首次保存配置时必须填写 api_key")

        runtime_config = self._build_effective_runtime_config(target, payload)
        self._validate_runtime_config(target, runtime_config)

        if row is None:
            row = ModelConfig(
                target=target,
                api_key=runtime_config["api_key"],
                base_url=runtime_config["base_url"],
                model_name=runtime_config["model_name"],
            )
            self.db.add(row)
        else:
            if api_key:
                row.api_key = api_key
            row.base_url = runtime_config["base_url"]
            row.model_name = runtime_config["model_name"]

        self.db.commit()
        self.db.refresh(row)
        return row

    def to_read_model(self, target: ModelConfigTarget) -> dict:
        row = self.get_config(target)
        if row is None:
            return {
                "target": target,
                "label": MODEL_CONFIG_LABELS[target],
                "has_api_key": False,
                "base_url": None,
                "model_name": None,
                "is_configured": False,
                "missing_fields": ["api_key", "base_url", "model_name"],
                "created_at": None,
                "updated_at": None,
            }

        missing_fields = []
        if not row.api_key.strip():
            missing_fields.append("api_key")
        if not row.base_url.strip():
            missing_fields.append("base_url")
        if not row.model_name.strip():
            missing_fields.append("model_name")

        return {
            "target": target,
            "label": MODEL_CONFIG_LABELS[target],
            "has_api_key": bool(row.api_key.strip()),
            "base_url": row.base_url,
            "model_name": row.model_name,
            "is_configured": not missing_fields,
            "missing_fields": missing_fields,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    def get_runtime_config(self, target: ModelConfigTarget) -> dict[str, str]:
        row = self.get_config(target)
        if row is None:
            raise ValueError(
                f"{MODEL_CONFIG_LABELS[target]}未配置，请先前往模型配置页面完成 API Key / Base URL / Model Name 配置",
            )

        missing_fields = []
        if not row.api_key.strip():
            missing_fields.append("api_key")
        if not row.base_url.strip():
            missing_fields.append("base_url")
        if not row.model_name.strip():
            missing_fields.append("model_name")
        if missing_fields:
            missing_text = "、".join(missing_fields)
            raise ValueError(
                f"{MODEL_CONFIG_LABELS[target]}缺少 {missing_text}，请先前往模型配置页面补全后再使用",
            )

        return {
            "api_key": row.api_key,
            "base_url": row.base_url,
            "model_name": row.model_name,
        }

    def required_targets_for_output_mode(self, output_mode: OutputMode | str) -> list[ModelConfigTarget]:
        if getattr(output_mode, "value", output_mode) == OutputMode.JSON.value:
            return [
                ModelConfigTarget.CRAWLER_AGENT,
                ModelConfigTarget.RECURSIVE_ACQUISITION,
            ]
        return [ModelConfigTarget.CRAWLER_AGENT]

    def ensure_output_mode_ready(self, output_mode: OutputMode | str) -> None:
        for target in self.required_targets_for_output_mode(output_mode):
            self.get_runtime_config(target)
