"""Chat orchestration: validate, retrieve, generate, and validate citations."""

from __future__ import annotations

import logging
import re
import time
import uuid
from collections import OrderedDict
from datetime import date
from typing import Any, Protocol

import numpy as np

from app.core.config import Settings
from app.rag.embeddings import EmbeddingProvider
from app.rag.generation import GenerationError, generate_answer
from app.rag.guardrails import (
    redact_for_log,
    scrub_customer_reply,
    validate_message,
)
from app.rag.index import NumPyIndex, SearchHit
from app.rag.prompt import PROMPT_VERSION, build_messages
from app.rag.text import truncate
from app.schemas.chat import ChatRequest, ChatResponse, Citation, Source

logger = logging.getLogger(__name__)

_CITATION_RE = re.compile(r"\bKB-(?:POL|FAQ|SOP)-\d{3}\b")


class InputRejected(Exception):
    def __init__(self, reason: str, *, warnings: list[str] | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.warnings = warnings or []


class ServiceUnavailable(Exception):
    pass


class UpstreamError(Exception):
    pass


class LLMClient(Protocol):
    def complete(self, messages: list[dict[str, str]], *, response_format: bool = True) -> Any: ...


REFUSAL_CUSTOMER_REPLY = (
    "Mohon maaf, informasi tersebut belum tersedia di knowledge base kami. "
    "Saya akan bantu eskalasikan ke tim terkait agar dapat dicek lebih lanjut. "
    "Mohon sertakan nomor pesanan atau Ticket ID agar prosesnya lebih cepat."
)

REFUSAL_INTERNAL_NOTES = (
    "Tidak ada sumber yang cukup untuk menjawab pertanyaan ini. "
    "Jangan menebak kebijakan atau angka. Eskalasi ke tim terkait dan minta "
    "detail pesanan/Ticket ID bila diperlukan."
)

SERVICE_BUSY_CUSTOMER_REPLY = (
    "Mohon maaf, layanan sedang sibuk atau tidak tersedia saat ini. "
    "Silakan coba lagi beberapa saat lagi. Jika mendesak, teruskan ke agen "
    "manusia melalui kanal resmi TravelKita."
)

SERVICE_BUSY_INTERNAL_NOTES = (
    "Permintaan gagal karena layanan embedding/generation tidak tersedia, "
    "rate limit, atau konfigurasi API bermasalah. Jangan mengarang jawaban; "
    "coba lagi atau eskalasi ke agen manusia."
)

QUOTA_CUSTOMER_REPLY = (
    "Mohon maaf, layanan chat sedang mencapai batas kapasitas harian. "
    "Silakan coba lagi besok atau hubungi Customer Care TravelKita melalui "
    "kanal resmi agar bisa dibantu oleh agen manusia."
)

QUOTA_INTERNAL_NOTES = (
    "Kuota provider LLM habis (HTTP 402/403/429). Jangan mengarang jawaban. "
    "Eskalasi ke agen manusia atau coba lagi setelah kuota direset."
)


class ChatService:
    def __init__(
        self,
        settings: Settings,
        index: NumPyIndex,
        embedder: EmbeddingProvider,
        llm: LLMClient,
        *,
        embedding_cache_size: int = 128,
    ) -> None:
        self.settings = settings
        self.index = index
        self.embedder = embedder
        self.llm = llm
        self._embedding_cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._embedding_cache_size = embedding_cache_size
        self._embedding_unavailable_until = 0.0
        self._budget_date = date.today()
        self._request_count = 0

    @property
    def index_version(self) -> str:
        return str(self.index.manifest.get("index_version") or "")

    def _embed_query(self, question: str) -> np.ndarray:
        if time.monotonic() < self._embedding_unavailable_until:
            raise ServiceUnavailable("Embedding sedang cooldown setelah gagal.")

        key = f"{self.settings.embedding_model}:{question}"
        cached = self._embedding_cache.get(key)
        if cached is not None:
            self._embedding_cache.move_to_end(key)
            return cached

        try:
            vectors = self.embedder.embed(
                [question], input_type=self.settings.embedding_input_type or None
            )
        except Exception as exc:
            self._embedding_unavailable_until = time.monotonic() + max(
                0, self.settings.embedding_failure_cooldown_seconds
            )
            raise ServiceUnavailable(f"Embedding query gagal: {exc}") from exc

        self._embedding_unavailable_until = 0.0
        vector = np.asarray(vectors[0], dtype=np.float32)
        self._embedding_cache[key] = vector
        if len(self._embedding_cache) > self._embedding_cache_size:
            self._embedding_cache.popitem(last=False)
        return vector

    def _check_budget(self) -> None:
        today = date.today()
        if today != self._budget_date:
            self._budget_date = today
            self._request_count = 0
        if (
            self.settings.daily_request_budget > 0
            and self._request_count >= self.settings.daily_request_budget
        ):
            raise ServiceUnavailable("Batas request harian aplikasi tercapai. Coba lagi besok.")

    def _sources(self, hits: list[SearchHit], cited: set[str]) -> list[Source]:
        sources: list[Source] = []
        for rank, hit in enumerate(hits, start=1):
            chunk = hit.chunk
            sources.append(
                Source(
                    chunk_id=chunk["chunk_id"],
                    doc_id=chunk["doc_id"],
                    title=chunk["title"],
                    section_path=chunk["section_path"],
                    version=chunk.get("version"),
                    effective_date=chunk.get("effective_date"),
                    audience=chunk.get("audience", "public"),
                    chunk_type=chunk.get("chunk_type", "prose"),
                    snippet=truncate(chunk.get("text", ""), 500),
                    dense_score=hit.dense_score,
                    bm25_score=hit.bm25_score,
                    rrf_score=hit.rrf_score,
                    rank=rank,
                    cited=chunk["doc_id"] in cited,
                )
            )
        return sources

    def _citations(self, hits: list[SearchHit], cited: list[str]) -> list[Citation]:
        seen: set[str] = set()
        citations: list[Citation] = []
        for doc_id in cited:
            if doc_id in seen:
                continue
            seen.add(doc_id)
            for hit in hits:
                chunk = hit.chunk
                if chunk["doc_id"] != doc_id:
                    continue
                citations.append(
                    Citation(
                        doc_id=doc_id,
                        title=chunk["title"],
                        version=chunk.get("version"),
                        effective_date=chunk.get("effective_date"),
                        section_path=chunk["section_path"],
                        snippet=truncate(chunk.get("text", ""), 500),
                    )
                )
                break
        return citations

    def _base_response(
        self,
        *,
        request_id: str,
        answerable: bool,
        internal_notes: str,
        customer_reply: str,
        citations: list[Citation],
        sources: list[Source],
        confidence: float,
        needs_escalation: bool,
        escalation_reason: str | None,
        refusal_reason: str | None,
        citation_valid: bool,
        model: str,
        latency_ms: int,
        usage: dict[str, Any] | None,
        warnings: list[str],
        debug: dict[str, Any] | None,
    ) -> ChatResponse:
        return ChatResponse(
            request_id=request_id,
            answerable=answerable,
            internal_notes=internal_notes,
            customer_reply=customer_reply,
            citations=citations,
            sources=sources,
            confidence=confidence,
            needs_escalation=needs_escalation,
            escalation_reason=escalation_reason,
            refusal_reason=refusal_reason,
            citation_valid=citation_valid,
            model=model,
            index_version=self.index_version,
            prompt_version=PROMPT_VERSION,
            latency_ms=latency_ms,
            usage=usage,
            warnings=warnings,
            debug=debug,
        )

    def _refuse(
        self,
        *,
        request_id: str,
        reason: str,
        hits: list[SearchHit],
        warnings: list[str],
        debug: dict[str, Any] | None,
        started: float,
        model: str = "",
        usage: dict[str, Any] | None = None,
        internal_notes: str | None = None,
        customer_reply: str | None = None,
    ) -> ChatResponse:
        return self._base_response(
            request_id=request_id,
            answerable=False,
            internal_notes=internal_notes or REFUSAL_INTERNAL_NOTES,
            customer_reply=customer_reply or REFUSAL_CUSTOMER_REPLY,
            citations=[],
            sources=self._sources(hits, set()),
            confidence=0.0,
            needs_escalation=True,
            escalation_reason=reason,
            refusal_reason=reason,
            citation_valid=True,
            model=model,
            latency_ms=int((time.perf_counter() - started) * 1000),
            usage=usage,
            warnings=warnings,
            debug=debug,
        )

    def answer(self, request: ChatRequest) -> ChatResponse:
        started = time.perf_counter()
        request_id = uuid.uuid4().hex
        guard = validate_message(request.message, self.settings.max_input_chars)
        if not guard.ok:
            raise InputRejected(guard.reason or "Pesan tidak valid.", warnings=guard.warnings)

        question = guard.sanitized_text
        warnings = list(guard.warnings)
        debug: dict[str, Any] | None = None
        if request.debug:
            debug = {
                "mode": request.mode,
                "question_for_retrieval": question,
                "min_dense_score": self.settings.min_dense_score,
                "context_top_k": self.settings.context_top_k,
            }

        audience = "public" if request.mode == "public" else None
        top_k = request.top_k or self.settings.top_k

        retrieval_mode = "hybrid"
        query_vector: np.ndarray | None
        try:
            query_vector = self._embed_query(question)
        except ServiceUnavailable as exc:
            # The OpenRouter free daily quota can be exhausted. BM25 is a strong
            # fallback on this corpus and keeps the copilot usable without
            # calling the embedding API.
            query_vector = None
            retrieval_mode = "bm25"
            warnings.append("Embedding query tidak tersedia; memakai BM25 fallback.")
            logger.warning(
                "request_id=%s embedding_failed_fallback_bm25=%s",
                request_id,
                exc,
            )

        hits = self.index.search(
            question,
            query_vector,
            top_k=top_k,
            mode=retrieval_mode,
            status="active",
            audience=audience,
            as_of=date.today().isoformat(),
        )
        if not hits:
            return self._refuse(
                request_id=request_id,
                reason="no_relevant_source",
                hits=[],
                warnings=warnings,
                debug=debug,
                started=started,
            )

        top_dense = (
            max((hit.dense_score or 0.0) for hit in hits) if retrieval_mode != "bm25" else None
        )
        if top_dense is not None and top_dense < self.settings.min_dense_score:
            return self._refuse(
                request_id=request_id,
                reason="low_relevance",
                hits=hits,
                warnings=warnings,
                debug=debug,
                started=started,
            )

        context_hits = hits[: self.settings.context_top_k]
        if debug is not None:
            debug.update(
                {
                    "retrieval_mode": retrieval_mode,
                    "retrieval": [
                        {
                            "chunk_id": hit.chunk["chunk_id"],
                            "doc_id": hit.chunk["doc_id"],
                            "section_path": hit.chunk["section_path"],
                            "dense_score": hit.dense_score,
                            "bm25_score": hit.bm25_score,
                            "rrf_score": hit.rrf_score,
                        }
                        for hit in hits
                    ],
                    "top_dense": top_dense,
                }
            )

        try:
            self._check_budget()
            generation = generate_answer(
                self.llm,
                build_messages(
                    question,
                    context_hits,
                    mode=request.mode,
                    max_context_chars=self.settings.max_context_chars,
                ),
            )
            self._request_count += 1
        except GenerationError as exc:
            if exc.status in {402, 403, 429}:
                logger.error(
                    "request_id=%s generation_quota_exhausted status=%s error=%s",
                    request_id,
                    exc.status,
                    exc,
                )
                return self._refuse(
                    request_id=request_id,
                    reason="llm_quota_exhausted",
                    hits=context_hits,
                    warnings=warnings,
                    debug=debug,
                    started=started,
                    internal_notes=QUOTA_INTERNAL_NOTES,
                    customer_reply=QUOTA_CUSTOMER_REPLY,
                )
            logger.error("request_id=%s generation_failed=%s", request_id, exc)
            return self._refuse(
                request_id=request_id,
                reason="generation_failed",
                hits=context_hits,
                warnings=warnings,
                debug=debug,
                started=started,
                internal_notes=SERVICE_BUSY_INTERNAL_NOTES,
                customer_reply=SERVICE_BUSY_CUSTOMER_REPLY,
            )
        except ServiceUnavailable as exc:
            logger.error("request_id=%s generation_failed=%s", request_id, exc)
            return self._refuse(
                request_id=request_id,
                reason="generation_failed",
                hits=context_hits,
                warnings=warnings,
                debug=debug,
                started=started,
                internal_notes=SERVICE_BUSY_INTERNAL_NOTES,
                customer_reply=SERVICE_BUSY_CUSTOMER_REPLY,
            )

        answer = generation.answer
        retrieved_ids = {hit.chunk["doc_id"] for hit in context_hits}
        cited_ids = [doc_id for doc_id in answer.cited_doc_ids if doc_id in retrieved_ids]
        for match in _CITATION_RE.findall(answer.internal_notes):
            if match in retrieved_ids and match not in cited_ids:
                cited_ids.append(match)

        citation_valid = bool(cited_ids) if answer.answerable else True
        if answer.answerable and not citation_valid:
            warnings.append("Jawaban tidak menyertakan sitasi yang valid")

        customer_reply, leak_warnings = scrub_customer_reply(answer.customer_reply)
        warnings.extend(leak_warnings)
        if leak_warnings:
            customer_reply = REFUSAL_CUSTOMER_REPLY
            answer.answerable = False
            answer.escalation_reason = "guardrail internal leak"

        if answer.answerable and not customer_reply:
            warnings.append("customer_reply kosong")
            customer_reply = REFUSAL_CUSTOMER_REPLY
            answer.answerable = False

        needs_escalation = bool(
            answer.needs_escalation
            or not answer.answerable
            or leak_warnings
            or (answer.answerable and not citation_valid)
        )
        escalation_reason = answer.escalation_reason
        if not answer.answerable and not escalation_reason:
            escalation_reason = "informasi tidak tersedia di knowledge base"
        if leak_warnings:
            escalation_reason = "guardrail internal leak"
        if answer.answerable and not citation_valid and not escalation_reason:
            escalation_reason = "sitasi tidak valid"

        final_cited_ids = cited_ids if answer.answerable else []

        if debug is not None:
            debug.update(
                {
                    "generation_attempts": generation.attempts,
                    "cited_doc_ids_from_model": answer.cited_doc_ids,
                    "cited_doc_ids_valid": cited_ids,
                }
            )

        response = self._base_response(
            request_id=request_id,
            answerable=answer.answerable,
            internal_notes=answer.internal_notes.strip() or "-",
            customer_reply=customer_reply,
            citations=self._citations(context_hits, final_cited_ids),
            sources=self._sources(context_hits, set(final_cited_ids)),
            confidence=answer.confidence if answer.answerable else 0.0,
            needs_escalation=needs_escalation,
            escalation_reason=escalation_reason,
            refusal_reason=None
            if answer.answerable
            else (answer.escalation_reason or "not_available_in_kb"),
            citation_valid=citation_valid,
            model=generation.model,
            latency_ms=int((time.perf_counter() - started) * 1000),
            usage=generation.usage,
            warnings=list(dict.fromkeys(warnings)),
            debug=debug,
        )

        logger.info(
            "chat request_id=%s mode=%s answerable=%s citations=%s "
            "retrieval_mode=%s top_dense=%s model=%s latency_ms=%s question=%s",
            request_id,
            request.mode,
            response.answerable,
            len(response.citations),
            retrieval_mode,
            f"{top_dense:.3f}" if top_dense is not None else "-",
            response.model,
            response.latency_ms,
            redact_for_log(question),
        )
        return response
