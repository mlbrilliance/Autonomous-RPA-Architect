"""Application configuration using pydantic-settings."""

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    UIPATH_GATEWAY = "uipath_gateway"


class GenerationMode(str, Enum):
    """UiPath project generation mode."""

    REFRAMEWORK = "reframework"
    MAESTRO = "maestro"
    HYBRID = "hybrid"
    AUTO = "auto"


class LLMSettings(BaseSettings):
    """LLM provider configuration."""

    model_config = SettingsConfigDict(env_prefix="LLM_")

    provider: LLMProvider = Field(
        default=LLMProvider.ANTHROPIC,
        description="LLM provider to use for extraction and generation.",
    )
    model_name: str = Field(
        default="claude-sonnet-4-20250514",
        description="Model identifier to use.",
    )
    temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="Sampling temperature for generation.",
    )
    max_tokens: int = Field(
        default=4096,
        gt=0,
        description="Maximum tokens in LLM response.",
    )
    api_key: Optional[SecretStr] = Field(
        default=None,
        description="API key for the LLM provider.",
    )
    base_url: Optional[str] = Field(
        default=None,
        description="Custom base URL for the LLM API endpoint.",
    )


class UiPathSettings(BaseSettings):
    """UiPath Orchestrator connection settings."""

    model_config = SettingsConfigDict(env_prefix="UIPATH_")

    url: str = Field(
        default="https://cloud.uipath.com",
        description="UiPath Orchestrator URL.",
    )
    tenant_id: Optional[str] = Field(
        default=None,
        description="UiPath tenant identifier.",
    )
    client_id: Optional[SecretStr] = Field(
        default=None,
        description="OAuth client ID for UiPath.",
    )
    client_secret: Optional[SecretStr] = Field(
        default=None,
        description="OAuth client secret for UiPath.",
    )
    folder: str = Field(
        default="Default",
        description="UiPath Orchestrator folder name.",
    )


class RAGSettings(BaseSettings):
    """Retrieval-Augmented Generation settings."""

    model_config = SettingsConfigDict(env_prefix="RAG_")

    persist_dir: Path = Field(
        default=Path(".rag_store"),
        description="Directory for persisting vector store data.",
    )
    collection_name: str = Field(
        default="rpa_knowledge",
        description="Name of the vector collection.",
    )
    embedding_model: str = Field(
        default="text-embedding-3-small",
        description="Embedding model identifier.",
    )


class OutputSettings(BaseSettings):
    """Output and generation settings."""

    model_config = SettingsConfigDict(env_prefix="OUTPUT_")

    default_output_dir: Path = Field(
        default=Path("output"),
        description="Default directory for generated UiPath projects.",
    )
    validate_on_generate: bool = Field(
        default=True,
        description="Run IR validation before generating project.",
    )
    package_on_generate: bool = Field(
        default=False,
        description="Package project as .nupkg after generation.",
    )


class HarvestSettings(BaseSettings):
    """Browser-based selector harvesting settings."""

    model_config = SettingsConfigDict(env_prefix="HARVEST_")

    enabled: bool = Field(
        default=False,
        description="Enable live browser selector harvesting.",
    )
    headless: bool = Field(
        default=True,
        description="Run browser in headless mode.",
    )
    timeout_ms: int = Field(
        default=30000,
        gt=0,
        description="Browser navigation timeout in milliseconds.",
    )
    screenshot_dir: Optional[Path] = Field(
        default=None,
        description="Directory to save per-step screenshots.",
    )
    max_elements_per_page: int = Field(
        default=200,
        gt=0,
        description="Maximum interactive elements to harvest per page.",
    )
    credential_env_prefix: str = Field(
        default="HARVEST_CRED_",
        description="Env var prefix for per-system credentials (e.g., HARVEST_CRED_APP_USER).",
    )


class LifecycleSettings(BaseSettings):
    """Autonomous lifecycle agent settings."""

    model_config = SettingsConfigDict(env_prefix="LIFECYCLE_")

    monitor_interval_seconds: int = Field(
        default=300,
        gt=0,
        description="Seconds between monitoring polls.",
    )
    max_auto_fix_iterations: int = Field(
        default=3,
        gt=0,
        description="Maximum automatic fix-redeploy iterations.",
    )
    require_approval: bool = Field(
        default=True,
        description="Require human approval before applying fixes.",
    )
    deployment_folder: str = Field(
        default="Default",
        description="Default Orchestrator folder for deployment.",
    )
    monitor_lookback_hours: int = Field(
        default=24,
        gt=0,
        description="Hours to look back when collecting monitoring data.",
    )
    auto_deploy: bool = Field(
        default=False,
        description="Automatically deploy after successful generation.",
    )
    auto_monitor: bool = Field(
        default=True,
        description="Automatically start monitoring after deployment.",
    )
    metrics_db_path: Optional[Path] = Field(
        default=None,
        description="Path to SQLite metrics database (auto-created).",
    )


class AppConfig(BaseSettings):
    """Root application configuration.

    Loads settings from environment variables and .env files.
    Nested settings use prefixed env vars (e.g., LLM_PROVIDER, UIPATH_URL).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    llm: LLMSettings = Field(default_factory=LLMSettings)
    uipath: UiPathSettings = Field(default_factory=UiPathSettings)
    rag: RAGSettings = Field(default_factory=RAGSettings)
    output: OutputSettings = Field(default_factory=OutputSettings)
    harvest: HarvestSettings = Field(default_factory=HarvestSettings)
    lifecycle: LifecycleSettings = Field(default_factory=LifecycleSettings)
    generation_mode: GenerationMode = Field(
        default=GenerationMode.AUTO,
        description="UiPath project generation mode.",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).",
    )


def load_config(**overrides) -> AppConfig:
    """Load application configuration from environment and .env file.

    Args:
        **overrides: Key-value overrides applied on top of env/file settings.

    Returns:
        Fully resolved AppConfig instance.
    """
    return AppConfig(**overrides)
