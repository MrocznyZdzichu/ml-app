from functools import cached_property
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class RuntimeSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    model_artifact_uri: str = "/models/model.joblib"


class NullModel:
    def predict(self, records: list[dict]) -> list[float]:
        return [0.0 for _ in records]


class ModelLoader:
    def __init__(self, settings: RuntimeSettings | None = None) -> None:
        self.settings = settings or RuntimeSettings()

    @property
    def is_loaded(self) -> bool:
        return Path(self.settings.model_artifact_uri).exists()

    @cached_property
    def _model(self):
        artifact = Path(self.settings.model_artifact_uri)
        if not artifact.exists():
            return NullModel()

        import joblib

        return joblib.load(artifact)

    def load(self):
        return self._model
