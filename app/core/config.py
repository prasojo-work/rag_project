"""Application configuration loaded from environment variables / .env."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]

# Placeholders people commonly leave in .env. Treating them as unset keeps the
# provider fallback working: DEEPSEEK_API_KEY=- used to look "configured", so a
# bearer token of "-" was sent to the API and every chat request became a 401
# that the UI reported as "layanan sedang sibuk".
PLACEHOLDER_SECRETS = {
    "-",
    "--",
    "changeme",
    "change-me",
    "your-key-here",
    "todo",
    "xxx",
}


def is_secret_set(value: str | None) -> bool:
    """True only when a secret is present and is not an obvious placeholder."""
    if not value:
        return False
    return value.strip().lower() not in PLACEHOLDER_SECRETS


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

    # Generic OpenAI-compatible chat provider. Used when LLM_PROVIDER is any
    # label other than the deepseek/openrouter shorthands, so adding a provider
    # (NVIDIA NIM, Groq, Together, ...) becomes an .env-only change.
    llm_base_url: str = ""
    llm_api_key: str = ""

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

    # Generic OpenAI-compatible embedding provider.
    embedding_provider: str = "openrouter"
    embedding_base_url: str = ""
    embedding_api_key: str = ""

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
            value = self.deepseek_api_key
        elif self.chat_provider == "openrouter":
            value = self.openrouter_api_key
        else:
            value = self.llm_api_key
        return value if is_secret_set(value) else ""

    @property
    def chat_base_url(self) -> str:
        if self.chat_provider == "deepseek":
            return self.deepseek_base_url
        if self.chat_provider == "openrouter":
            return self.openrouter_base_url
        return self.llm_base_url

    @property
    def chat_provider_is_generic(self) -> bool:
        return self.chat_provider not in {"deepseek", "openrouter"}

    @property
    def embedding_provider_name(self) -> str:
        return (self.embedding_provider or "openrouter").strip().lower()

    @property
    def resolved_embedding_api_key(self) -> str:
        if self.embedding_provider_name == "openrouter":
            value = self.openrouter_api_key
        else:
            value = self.embedding_api_key
            if not is_secret_set(value) and self.embedding_provider_name == self.chat_provider:
                # Same vendor for chat and embeddings: reuse the chat key so the
                # secret is not duplicated in .env.
                value = self.llm_api_key
        return value if is_secret_set(value) else ""

    @property
    def resolved_embedding_base_url(self) -> str:
        if self.embedding_provider_name == "openrouter":
            return self.openrouter_base_url
        if not self.embedding_base_url and self.embedding_provider_name == self.chat_provider:
            return self.llm_base_url
        return self.embedding_base_url

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
