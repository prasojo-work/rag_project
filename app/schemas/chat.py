"""Pydantic schemas for the chat API and document endpoints."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    mode: Literal["agent", "public"] = "agent"
    top_k: int | None = Field(default=None, ge=1, le=20)
    debug: bool = False


class Citation(BaseModel):
    doc_id: str
    title: str
    version: str | None = None
    effective_date: str | None = None
    section_path: str
    snippet: str
    cited: bool = True


class Source(BaseModel):
    chunk_id: str
    doc_id: str
    title: str
    section_path: str
    version: str | None = None
    effective_date: str | None = None
    audience: str = "public"
    chunk_type: str
    snippet: str
    dense_score: float | None = None
    bm25_score: float | None = None
    rrf_score: float | None = None
    rank: int
    cited: bool = False


class ChatResponse(BaseModel):
    request_id: str
    answerable: bool
    internal_notes: str
    customer_reply: str
    citations: list[Citation] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    confidence: float = 0.0
    needs_escalation: bool = False
    escalation_reason: str | None = None
    refusal_reason: str | None = None
    citation_valid: bool = False
    model: str = ""
    index_version: str = ""
    prompt_version: str = ""
    latency_ms: int = 0
    usage: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    debug: dict[str, Any] | None = None


class DocumentInfo(BaseModel):
    doc_id: str
    title: str
    category: str
    subcategory: str | None = None
    version: str | None = None
    effective_date: str | None = None
    last_updated: str | None = None
    owner: str | None = None
    status: str
    audience: str
    source_path: str
    chunk_count: int


class DocumentChunk(BaseModel):
    chunk_id: str
    section_path: str
    chunk_type: str
    text: str
    token_estimate: int


class DocumentDetail(DocumentInfo):
    chunks: list[DocumentChunk] = Field(default_factory=list)


class MetaResponse(BaseModel):
    index_version: str | None = None
    created_at: str | None = None
    embedding_model: str | None = None
    embedding_dimension: int | None = None
    chunk_count: int
    document_count: int
    llm_provider: str
    llm_model: str
    prompt_version: str
    status_counts: dict[str, int] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str
    index_loaded: bool
    index_version: str | None = None


class ReadyResponse(BaseModel):
    ready: bool
    index_loaded: bool
    llm_configured: bool
    index_version: str | None = None


class FeedbackRequest(BaseModel):
    message_id: str | None = Field(default=None, max_length=120)
    rating: Literal["up", "down"]
    comment: str | None = Field(default=None, max_length=1000)


class FeedbackResponse(BaseModel):
    accepted: bool
    message: str
