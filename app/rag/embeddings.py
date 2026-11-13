"""Embedding providers: OpenRouter (production) and a deterministic hash fake."""

from __future__ import annotations

import hashlib
import os
import time
from typing import Protocol

import httpx
import numpy as np

from app.rag.text import tokenize

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


class EmbeddingProvider(Protocol):
    name: str
    model: str
    synthetic: bool
    dimension: int | None

    def embed(self, texts: list[str], input_type: str | None = None) -> np.ndarray: ...


def _normalize(vectors: np.ndarray) -> np.ndarray:
    vectors = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.maximum(norms, 1e-12)


class OpenRouterEmbeddings:
    """Batch embedding client for OpenRouter's OpenAI-compatible endpoint."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = DEFAULT_BASE_URL,
        batch_size: int = 16,
        timeout: float = 60.0,
        input_type: str | None = None,
        http_referer: str | None = None,
        x_title: str | None = None,
        max_retries: int = 3,
    ) -> None:
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY kosong")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.batch_size = max(1, batch_size)
        self.timeout = timeout
        self.input_type = input_type or None
        self.http_referer = http_referer or None
        self.x_title = x_title or None
        self.max_retries = max_retries
        self.name = "openrouter"
        self.synthetic = False
        self.dimension: int | None = None
        self._input_type_disabled = False

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

    def _request(self, client: httpx.Client, batch: list[str]) -> list[list[float]]:
        payload: dict[str, object] = {
            "model": self.model,
            "input": batch,
            "encoding_format": "float",
        }
        if self.input_type and not self._input_type_disabled:
            payload["input_type"] = self.input_type

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = client.post(
                    f"{self.base_url}/embeddings",
                    headers=self._headers(),
                    json=payload,
                )
                if response.status_code == 400 and "input_type" in payload:
                    # Some models reject input_type; retry once without it and
                    # remember the limitation to avoid wasting quota.
                    payload.pop("input_type", None)
                    self._input_type_disabled = True
                    response = client.post(
                        f"{self.base_url}/embeddings",
                        headers=self._headers(),
                        json=payload,
                    )
                response.raise_for_status()
                data = response.json().get("data", [])
                if len(data) != len(batch):
                    raise RuntimeError(
                        f"Jumlah embedding tidak sesuai: {len(data)} != {len(batch)}"
                    )
                ordered = sorted(data, key=lambda item: item.get("index", 0))
                return [item["embedding"] for item in ordered]
            except httpx.HTTPStatusError as exc:
                last_error = exc
                status = exc.response.status_code
                body = exc.response.text[:500]
                if status in {401, 402, 403}:
                    raise RuntimeError(
                        f"OpenRouter menolak request (HTTP {status}): {body}"
                    ) from exc
                if status == 429:
                    # Daily/per-minute quota will not recover in a few seconds.
                    # Let ChatService fall back to BM25 immediately.
                    raise RuntimeError(
                        "Rate limit embedding OpenRouter tercapai. "
                        "Cek kuota free model atau gunakan BM25 fallback."
                    ) from exc
                if status >= 500 and attempt < self.max_retries:
                    time.sleep(2**attempt)
                    continue
                hint = ""
                if len(batch) > 1:
                    hint = (
                        " Model/provider ini mungkin tidak mendukung batch >1. "
                        "Coba --batch-size 1 atau ganti EMBEDDING_MODEL ke "
                        "nvidia/nemotron-3.5-embed-8b:free."
                    )
                raise RuntimeError(f"Embedding gagal (HTTP {status}): {body}.{hint}") from exc
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(2**attempt)
                    continue
                raise RuntimeError(f"Koneksi ke OpenRouter gagal: {exc}") from exc

        raise RuntimeError(f"Embedding gagal setelah retry: {last_error}")

    def embed(self, texts: list[str], input_type: str | None = None) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dimension or 0), dtype=np.float32)

        previous_input_type = self.input_type
        if input_type is not None:
            self.input_type = input_type

        vectors: list[list[float]] = []
        try:
            with httpx.Client(timeout=self.timeout) as client:
                for start in range(0, len(texts), self.batch_size):
                    batch = texts[start : start + self.batch_size]
                    vectors.extend(self._request(client, batch))
        finally:
            self.input_type = previous_input_type

        matrix = _normalize(np.asarray(vectors, dtype=np.float32))
        if matrix.size:
            self.dimension = int(matrix.shape[1])
        return matrix


class HashEmbeddings:
    """Deterministic feature-hashing embeddings.

    Only for tests and pipeline smoke tests. It is lexical, not semantic, and
    must never be presented as a real retrieval baseline.
    """

    name = "hash"
    synthetic = True

    def __init__(self, dimension: int = 256) -> None:
        self.dimension = dimension
        self.model = f"hash-{dimension}"

    def embed(self, texts: list[str], input_type: str | None = None) -> np.ndarray:
        del input_type
        matrix = np.zeros((len(texts), self.dimension), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in tokenize(text):
                digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
                index = int.from_bytes(digest[:4], "big") % self.dimension
                sign = 1.0 if digest[4] & 1 else -1.0
                matrix[row, index] += sign
        return _normalize(matrix)


def get_embedding_provider(
    provider: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
    batch_size: int = 16,
    input_type: str | None = None,
    base_url: str = DEFAULT_BASE_URL,
    http_referer: str | None = None,
    x_title: str | None = None,
) -> EmbeddingProvider:
    provider = provider.lower().strip()
    if provider == "openrouter":
        key = api_key or os.getenv("OPENROUTER_API_KEY", "")
        if not key:
            raise RuntimeError(
                "OPENROUTER_API_KEY belum di-set. Salin .env.example menjadi .env "
                "dan isi API key, atau gunakan --provider hash untuk smoke test."
            )
        return OpenRouterEmbeddings(
            api_key=key,
            model=model or os.getenv("EMBEDDING_MODEL", "nvidia/nemotron-3.5-embed-8b:free"),
            base_url=base_url,
            batch_size=batch_size,
            input_type=input_type,
            http_referer=http_referer,
            x_title=x_title,
        )
    if provider == "hash":
        return HashEmbeddings()
    raise ValueError(f"Provider embedding tidak dikenal: {provider}")
