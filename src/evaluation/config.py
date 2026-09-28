"""Configuration for evaluation runs and optional Langfuse tracing."""

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class EvaluationSettings(BaseSettings):
    """Environment-backed settings with tracing disabled by default."""

    langfuse_public_key: str | None = Field(default=None, validation_alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str | None = Field(default=None, validation_alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(
        default="https://cloud.langfuse.com",
        validation_alias=AliasChoices("LANGFUSE_HOST", "LANGFUSE_BASE_URL"),
    )
    langfuse_environment: str = Field(
        default="production",
        validation_alias=AliasChoices("LANGFUSE_TRACING_ENVIRONMENT", "LANGFUSE_ENV", "ENVIRONMENT"),
    )
    evaluation_dataset_path: str = "data/eval/golden_dataset.json"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    @property
    def tracing_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)