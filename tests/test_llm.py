from __future__ import annotations

from unittest.mock import patch

from app.core.config import Settings, is_secret_set
from app.rag.llm import ChatClient


class FakeResponse:
    status_code = 200
    headers: dict[str, str] = {}

    def json(self):
        return {
            "id": "gen-test",
            "model": "fake",
            "choices": [
                {
                    "message": {"content": '{"answerable": true}'},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"total_tokens": 10},
        }

    def raise_for_status(self) -> None:
        return None


class FakeHttpClient:
    def __init__(self, *args, **kwargs) -> None:
        self.posts = []

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None

    def post(self, url, headers, json):
        self.posts.append((url, json))
        return FakeResponse()


def test_settings_selects_deepseek_provider() -> None:
    settings = Settings(
        llm_provider="deepseek",
        deepseek_api_key="deepseek-key",
        deepseek_model="deepseek-flash",
    )
    assert settings.chat_provider == "deepseek"
    assert settings.chat_api_key == "deepseek-key"
    assert settings.chat_base_url == "https://api.deepseek.com"
    assert settings.chat_models == ["deepseek-flash"]


def test_settings_selects_openrouter_provider() -> None:
    settings = Settings(
        llm_provider="openrouter",
        openrouter_api_key="openrouter-key",
        llm_model="model-a",
        llm_fallback_models="model-b, model-c",
    )
    assert settings.chat_provider == "openrouter"
    assert settings.chat_models == ["model-a", "model-b", "model-c"]


def test_deepseek_payload_disables_thinking() -> None:
    fake = FakeHttpClient()
    with patch("app.rag.llm.httpx.Client", return_value=fake):
        client = ChatClient(
            "key",
            ["deepseek-flash"],
            provider="deepseek",
            base_url="https://api.deepseek.com",
            thinking_disabled=True,
        )
        client.complete([{"role": "user", "content": "tes"}])

    url, payload = fake.posts[0]
    assert url == "https://api.deepseek.com/chat/completions"
    assert payload["thinking"] == {"type": "disabled"}
    assert "reasoning_effort" not in payload
    assert payload["response_format"] == {"type": "json_object"}


def test_openrouter_payload_uses_reasoning_effort() -> None:
    fake = FakeHttpClient()
    with patch("app.rag.llm.httpx.Client", return_value=fake):
        client = ChatClient(
            "key",
            ["model-a"],
            provider="openrouter",
            reasoning_effort="low",
        )
        client.complete([{"role": "user", "content": "tes"}])

    _, payload = fake.posts[0]
    assert payload["reasoning_effort"] == "low"
    assert "thinking" not in payload


def test_generic_openai_compatible_provider() -> None:
    settings = Settings(
        llm_provider="nvidia",
        llm_base_url="https://integrate.api.nvidia.com/v1",
        llm_api_key="nvapi-test",
        llm_model="minimaxai/minimax-m3.1-flash",
        llm_fallback_models="backup-model",
    )
    assert settings.chat_provider_is_generic is True
    assert settings.chat_api_key == "nvapi-test"
    assert settings.chat_base_url == "https://integrate.api.nvidia.com/v1"
    assert settings.chat_models == ["minimaxai/minimax-m3.1-flash", "backup-model"]


def test_placeholder_secret_is_treated_as_unset() -> None:
    """DEEPSEEK_API_KEY=- used to look configured and produced a 401 on every
    request instead of triggering the OpenRouter fallback."""
    settings = Settings(
        llm_provider="deepseek",
        deepseek_api_key="-",
        openrouter_api_key="openrouter-key",
    )
    assert is_secret_set("-") is False
    assert is_secret_set("sk-real-key") is True
    assert settings.chat_api_key == ""
    assert settings.openrouter_api_key == "openrouter-key"
