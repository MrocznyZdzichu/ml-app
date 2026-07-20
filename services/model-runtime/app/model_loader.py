from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
from pydantic_settings import BaseSettings, SettingsConfigDict


class RuntimeSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    model_repository_root: str = "/app/data/repository"


class ModelLoader:
    def __init__(self, settings: RuntimeSettings | None = None) -> None:
        self.settings = settings or RuntimeSettings()
        self.root = Path(self.settings.model_repository_root).resolve()

    def load(self, artifact_uri: str, expected_hash: str) -> dict[str, Any]:
        path = Path(artifact_uri.removeprefix("file://")).resolve()
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("Model artifact is outside the allowed repository") from exc
        if not path.is_file():
            raise FileNotFoundError("Model artifact does not exist")
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if expected_hash and actual_hash != expected_hash:
            raise ValueError("Model artifact hash does not match registry metadata")
        return self._load_cached(str(path), actual_hash)

    @staticmethod
    @lru_cache(maxsize=32)
    def _load_cached(path: str, artifact_hash: str) -> dict[str, Any]:
        bundle = joblib.load(path)
        if not isinstance(bundle, dict) or "estimator" not in bundle or "feature_columns" not in bundle:
            raise ValueError("Unsupported model bundle contract")
        return bundle
