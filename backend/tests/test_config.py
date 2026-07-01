import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_non_local_environment_rejects_development_secret() -> None:
    with pytest.raises(ValidationError, match="APP_SECRET_KEY must be changed"):
        Settings(APP_ENV="production", APP_SECRET_KEY="change-me-in-development")


def test_non_local_environment_accepts_strong_secret() -> None:
    configured = Settings(APP_ENV="production", APP_SECRET_KEY="x" * 32)

    assert configured.app_env == "production"
