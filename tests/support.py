from __future__ import annotations

import json
from typing import Any

from app.core.config import Settings
from app.rag.embeddings import HashEmbeddings
from app.rag.index import NumPyIndex
from app.rag.llm import LLMResult
from app.services.chat import ChatService


def make_chunk(
    chunk_id: str,
    doc_id: str,
    text: str,
    *,
    title: str | None = None,
    category: str = "policy",
    audience: str = "public",
    section_path: str = "Umum",
    chunk_type: str = "prose",
    status: str = "active",
) -> dict[str, Any]:
    return {
        "chunk_id": chunk_id,
        "doc_id": doc_id,
        "title": title or doc_id,
        "category": category,
        "subcategory": "refund",
        "version": "1.0",
        "effective_date": "2025-01-01",
        "last_updated": "2025-01-01",
        "status": status,
        "audience": audience,
        "section_path": section_path,
        "chunk_type": chunk_type,
        "text": text,
        "embedding_text": f"{title or doc_id}\n{text}",
        "token_estimate": 20,
        "source_path": f"{doc_id}.md",
        "doc_hash": f"hash-{doc_id}",
        "chunk_hash": f"chunk-{chunk_id}",
    }


def make_index() -> NumPyIndex:
    chunks = [
        make_chunk(
            "c1",
            "KB-POL-001",
            "Refund ke GoPay diproses 1 sampai 3 hari kerja dengan biaya admin Rp 10.000.",
            title="Kebijakan Refund",
        ),
        make_chunk(
            "c2",
            "KB-POL-002",
            "Refund kartu kredit maksimal 7 hari kerja dengan biaya admin Rp 25.000.",
            title="Kebijakan Refund Dana",
        ),
        make_chunk(
            "c3",
            "KB-SOP-001",
            "SOP internal: eskalasi refund yang melewati SLA ke supervisor.",
            title="SOP Refund Tertunda",
            category="sop",
            audience="internal",
        ),
    ]
    vectors = HashEmbeddings().embed([chunk["text"] for chunk in chunks])
    documents = [
        {
            "doc_id": "KB-POL-001",
            "title": "Kebijakan Refund",
            "category": "policy",
            "subcategory": "refund",
            "version": "1.0",
            "effective_date": "2025-01-01",
            "last_updated": "2025-01-01",
            "owner": "Refund",
            "status": "active",
            "audience": "public",
            "source_path": "KB-POL-001.md",
            "chunk_count": 1,
        },
        {
            "doc_id": "KB-POL-002",
            "title": "Kebijakan Refund Dana",
            "category": "policy",
            "subcategory": "refund",
            "version": "1.0",
            "effective_date": "2025-01-01",
            "last_updated": "2025-01-01",
            "owner": "Refund",
            "status": "active",
            "audience": "public",
            "source_path": "KB-POL-002.md",
            "chunk_count": 1,
        },
        {
            "doc_id": "KB-SOP-001",
            "title": "SOP Refund Tertunda",
            "category": "sop",
            "subcategory": "refund",
            "version": "1.0",
            "effective_date": "2025-01-01",
            "last_updated": "2025-01-01",
            "owner": "Refund",
            "status": "active",
            "audience": "internal",
            "source_path": "KB-SOP-001.md",
            "chunk_count": 1,
        },
    ]
    return NumPyIndex(
        chunks=chunks,
        embeddings=vectors,
        manifest={
            "index_version": "test-index",
            "dimension": vectors.shape[1],
            "chunk_count": len(chunks),
            "document_count": len(documents),
            "documents": documents,
            "status_counts": {"active": 3},
            "embedding_model": "hash-test",
            "created_at": "2026-01-01T00:00:00Z",
        },
    )


class FakeLLM:
    def __init__(self, *payloads: dict[str, Any] | str) -> None:
        self.payloads = list(payloads)
        self.calls: list[list[dict[str, str]]] = []

    def complete(
        self, messages: list[dict[str, str]], *, response_format: bool = True
    ) -> LLMResult:
        del response_format
        self.calls.append(messages)
        if not self.payloads:
            raise AssertionError("FakeLLM tidak punya payload tersisa")
        payload = self.payloads.pop(0)
        content = payload if isinstance(payload, str) else json.dumps(payload)
        return LLMResult(content=content, model="fake-model", usage={"total_tokens": 10})


def make_settings(**overrides: Any) -> Settings:
    values = {
        "openrouter_api_key": "test-key",
        "min_dense_score": 0.0,
        "context_top_k": 3,
        "daily_request_budget": 100,
        "rate_limit_per_minute": 100,
        "max_input_chars": 1000,
    }
    values.update(overrides)
    return Settings(**values)


def make_service(
    payload: dict[str, Any] | str,
    *,
    settings: Settings | None = None,
    index: NumPyIndex | None = None,
) -> ChatService:
    settings = settings or make_settings()
    index = index or make_index()
    return ChatService(
        settings=settings,
        index=index,
        embedder=HashEmbeddings(),
        llm=FakeLLM(payload),
    )
