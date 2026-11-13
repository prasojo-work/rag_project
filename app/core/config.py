"""Application configuration loaded from environment variables / .env."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "development"
    log_level: str = "INFO"

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_http_referer: str = ""
    openrouter_x_title: str = "TravelKita RAG"

    # Chat provider: "deepseek" for development, "openrouter" for deploy/demo.
    llm_provider: str = "openrouter"
    llm_model: str = "baidu/ernie-5.5-flash-preview:free"
    llm_fallback_models: str = "google/gemma-4-26b-a4b-it:free"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 1400
    llm_reasoning_effort: str = "low"

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"
    deepseek_fallback_models: str = ""
    deepseek_thinking_disabled: bool = True

    judge_model: str = "deepseek-v4-pro"
    judge_fallback_models: str = "deepseek-flash"

    embedding_model: str = "nvidia/nemotron-3.5-embed-8b:free"
    embedding_batch_size: int = 16
    embedding_input_type: str = ""
    embedding_failure_cooldown_seconds: int = 120

    index_dir: Path = ROOT / "data/index"
    prompt_version: str = "1.0"

    top_k: int = 10
    context_top_k: int = 6
    max_input_chars: int = 1000
    max_context_chars: int = 16000
    min_dense_score: float = 0.20

    request_timeout: float = 120.0
    rate_limit_per_minute: int = 10
    daily_request_budget: int = 100
    admin_token: str = ""

    @property
    def fallback_models(self) -> list[str]:
        return [model.strip() for model in self.llm_fallback_models.split(",") if model.strip()]

    @property
    def model_candidates(self) -> list[str]:
        candidates = [self.llm_model, *self.fallback_models]
        # Keep order, remove duplicates.
        return list(dict.fromkeys(candidates))

    @property
    def deepseek_fallback_model_list(self) -> list[str]:
        return [
            model.strip() for model in self.deepseek_fallback_models.split(",") if model.strip()
        ]

    @property
    def chat_provider(self) -> str:
        return self.llm_provider.strip().lower()

    @property
    def chat_api_key(self) -> str:
        if self.chat_provider == "deepseek":
            return self.deepseek_api_key
        return self.openrouter_api_key

    @property
    def chat_base_url(self) -> str:
        if self.chat_provider == "deepseek":
            return self.deepseek_base_url
        return self.openrouter_base_url

    @property
    def chat_models(self) -> list[str]:
        if self.chat_provider == "deepseek":
            candidates = [self.deepseek_model, *self.deepseek_fallback_model_list]
        else:
            candidates = [self.llm_model, *self.fallback_models]
        return list(dict.fromkeys(model for model in candidates if model))

    @property
    def judge_models(self) -> list[str]:
        candidates = [
            self.judge_model,
            *[model.strip() for model in self.judge_fallback_models.split(",") if model.strip()],
        ]
        return list(dict.fromkeys(model for model in candidates if model))

    @property
    def resolved_index_dir(self) -> Path:
        if self.index_dir.is_absolute():
            return self.index_dir
        return ROOT / self.index_dir
