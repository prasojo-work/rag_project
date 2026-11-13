from __future__ import annotations

from unittest.mock import patch

from app.core.config import Settings
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
