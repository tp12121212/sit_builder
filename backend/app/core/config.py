from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("backend/.env", ".env"), env_file_encoding="utf-8", case_sensitive=False)

    app_name: str = "SIT Builder"
    environment: str = "development"
    debug: bool = True
    api_prefix: str = "/v1"

    database_url: str = "postgresql+psycopg://sitbuilder:sitbuilder@localhost:5432/sitbuilder"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    storage_root: Path = Field(default=Path("data"))
    upload_dir: str = "uploads"
    artifacts_dir: str = "artifacts"

    default_tenant_name: str = "Default Tenant"
    default_user_email: str = "admin@example.com"
    default_user_name: str = "Local Admin"
    default_user_role: str = "ADMIN"

    # For local development. Replace with real Entra/OIDC validation for production.
    allow_insecure_dev_auth: bool = True

    sentence_transformer_powershell_script: Path = Field(default=Path("scripts/textExctraction.ps1"))
    sentence_transformer_python_script: Path = Field(default=Path("scripts/keyword_extraction.py"))
    sentence_transformer_python_executable: str = "python3"


@lru_cache
def get_settings() -> Settings:
    return Settings()
