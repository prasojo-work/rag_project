"""OpenRouter chat client with model fallback and JSON mode."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        model: str | None = None,
        body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.model = model
        self.body = body


@dataclass
class LLMResult:
    content: str
    model: str
    usage: dict[str, Any] | None = None
    response_id: str | None = None
    finish_reason: str | None = None


class ChatClient:
    """OpenAI-compatible chat client for OpenRouter and DeepSeek."""

    def __init__(
        self,
        api_key: str,
        models: list[str],
        *,
        provider: str = "openrouter",
        base_url: str = "https://openrouter.ai/api/v1",
        temperature: float = 0.1,
        max_tokens: int = 1400,
        reasoning_effort: str | None = "low",
        thinking_disabled: bool = True,
        timeout: float = 120.0,
        http_referer: str | None = None,
        x_title: str | None = None,
        max_retries: int = 2,
    ) -> None:
        if not api_key:
            raise ValueError("API key chat kosong")
        if not models:
            raise ValueError("Minimal satu model chat harus di-set")
        self.api_key = api_key
        self.models = list(dict.fromkeys(models))
        self.provider = provider.strip().lower()
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.reasoning_effort = reasoning_effort or None
        self.thinking_disabled = thinking_disabled
        self.timeout = timeout
        self.http_referer = http_referer or None
        self.x_title = x_title or None
        self.max_retries = max_retries

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.http_referer:
            headers["HTTP-Referer"] = self.http_referer
        if self.x_title:
            headers["X-Title"] = self.x_title
        return headers

    def _call(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        response_format: bool,
    ) -> LLMResult:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if response_format:
            payload["response_format"] = {"type": "json_object"}
        if self.provider == "deepseek":
            # DeepSeek thinking mode is enabled by default. Disable it for a
            # customer-service copilot: lower latency and cheaper output.
            payload["thinking"] = {"type": "disabled" if self.thinking_disabled else "enabled"}
        elif self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort

        with httpx.Client(timeout=self.timeout) as client:
            for attempt in range(self.max_retries + 1):
                try:
                    response = client.post(
                        f"{self.base_url}/chat/completions",
                        headers=self._headers(),
                        json=payload,
                    )
                    if response.status_code == 400 and (
                        "response_format" in payload
                        or "reasoning_effort" in payload
                        or "thinking" in payload
                    ):
                        logger.warning(
                            "Model %s menolak parameter opsional; retry tanpa "
                            "response_format/reasoning_effort/thinking",
                            model,
                        )
                        payload.pop("response_format", None)
                        payload.pop("reasoning_effort", None)
                        payload.pop("thinking", None)
                        response = client.post(
                            f"{self.base_url}/chat/completions",
                            headers=self._headers(),
                            json=payload,
                        )
                    if response.status_code == 429:
                        # Fail fast to the fallback model instead of burning the
                        # limited free-tier quota on retries.
                        raise LLMError(
                            "Model chat kena rate limit.",
                            status=429,
                            model=model,
                            body=response.text[:300],
                        )
                    if response.status_code >= 500:
                        if attempt < self.max_retries:
                            time.sleep(2**attempt)
                            continue
                        raise LLMError(
                            "Provider chat mengembalikan error server.",
                            status=response.status_code,
                            model=model,
                            body=response.text[:300],
                        )
                    if response.status_code in {401, 402}:
                        raise LLMError(
                            "OpenRouter menolak kredensial/kredit.",
                            status=response.status_code,
                            model=model,
                            body=response.text[:300],
                        )
                    response.raise_for_status()
                    data = response.json()
                    choices = data.get("choices") or []
                    if not choices:
                        raise LLMError("Response chat tidak punya choices.", model=model)
                    message = choices[0].get("message") or {}
                    content = message.get("content")
                    if not content or not str(content).strip():
                        raise LLMError(
                            "Model mengembalikan content kosong (mungkin hanya reasoning).",
                            model=model,
                            body=str(choices[0])[:300],
                        )
                    return LLMResult(
                        content=str(content),
                        model=str(data.get("model") or model),
                        usage=data.get("usage"),
                        response_id=data.get("id"),
                        finish_reason=choices[0].get("finish_reason"),
                    )
                except httpx.HTTPStatusError as exc:
                    status = exc.response.status_code
                    if status in {401, 402, 403}:
                        raise LLMError(
                            "Model chat tidak dapat diakses.",
                            status=status,
                            model=model,
                            body=exc.response.text[:300],
                        ) from exc
                    if attempt < self.max_retries:
                        time.sleep(2**attempt)
                        continue
                    raise LLMError(
                        "Request chat gagal.",
                        status=status,
                        model=model,
                        body=exc.response.text[:300],
                    ) from exc
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    if attempt < self.max_retries:
                        time.sleep(2**attempt)
                        continue
                    raise LLMError(f"Koneksi ke OpenRouter gagal: {exc}", model=model) from exc
        raise LLMError("Request chat gagal setelah retry.", model=model)

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        response_format: bool = True,
    ) -> LLMResult:
        errors: list[str] = []
        last_status: int | None = None
        for model in self.models:
            try:
                result = self._call(model, messages, response_format=response_format)
                if model != self.models[0]:
                    logger.info("Chat memakai fallback model %s", model)
                return result
            except LLMError as exc:
                errors.append(f"{model}: {exc}")
                last_status = exc.status
                logger.warning("Chat model %s gagal: %s", model, exc)
                if exc.status in {401, 402}:
                    break
                continue
        raise LLMError(
            "Semua model chat gagal: " + " | ".join(errors),
            status=last_status,
        )


# Backwards-compatible alias for earlier imports.
OpenRouterChat = ChatClient
