"""FastAPI application for the TravelKita CS copilot."""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.core.config import ROOT, Settings
from app.core.logging import configure_logging
from app.core.security import RateLimiter, client_key
from app.rag.embeddings import get_embedding_provider
from app.rag.eval_report import load_retrieval_view
from app.rag.guardrails import redact_for_log
from app.rag.index import NumPyIndex
from app.rag.llm import ChatClient
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    DocumentChunk,
    DocumentDetail,
    DocumentInfo,
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    MetaResponse,
    ReadyResponse,
)
from app.services.chat import (
    ChatService,
    InputRejected,
    ServiceUnavailable,
    UpstreamError,
)

logger = logging.getLogger(__name__)

SUGGESTED_QUESTIONS = [
    {
        "label": "Batalkan tiket pesawat",
        "hint": "Langkah dan syaratnya",
        "text": "Bagaimana cara membatalkan tiket pesawat saya?",
    },
    {
        "label": "Refund GoPay",
        "hint": "Lama proses dan biaya admin",
        "text": "Refund ke GoPay berapa lama dan berapa biaya adminnya?",
    },
    {
        "label": "Reschedule hotel",
        "hint": "Ubah tanggal menginap",
        "text": "Bagaimana cara reschedule hotel yang sudah saya pesan?",
    },
    {
        "label": "E-tiket belum masuk",
        "hint": "Cek email dan kirim ulang",
        "text": "E-tiket saya belum masuk email, apa yang harus saya lakukan?",
    },
    {
        "label": "Cara pakai voucher",
        "hint": "Kode promo dan syaratnya",
        "text": "Bagaimana cara memakai voucher TravelKita saat checkout?",
    },
]


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "-")


def _error(
    status: int,
    code: str,
    message: str,
    request: Request,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": _request_id(request),
            }
        },
        headers=headers,
    )


def create_app(
    settings: Settings | None = None,
    service: ChatService | None = None,
) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level)

    provider = settings.chat_provider
    if provider not in {"deepseek", "openrouter"}:
        raise ValueError(f"LLM_PROVIDER tidak dikenal: {provider}")
    chat_key_available = bool(settings.chat_api_key)
    if provider == "deepseek" and not settings.deepseek_api_key and settings.openrouter_api_key:
        # Development convenience: if DEEPSEEK_API_KEY is not set yet, use
        # OpenRouter instead of failing to boot.
        provider = "openrouter"
        chat_key_available = True

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.rate_limiter = RateLimiter(settings.rate_limit_per_minute)
        app.state.index = service.index if service is not None else None
        app.state.service = service
        app.state.llm_configured = service is not None or chat_key_available
        app.state.chat_provider = provider
        app.state.chat_model = (
            settings.chat_models[0] if settings.chat_models else settings.llm_model
        )
        app.state.startup_error = None

        if service is None:
            try:
                index = NumPyIndex.load(settings.resolved_index_dir)
                app.state.index = index
                embedder = get_embedding_provider(
                    "openrouter",
                    api_key=settings.openrouter_api_key,
                    model=settings.embedding_model,
                    batch_size=settings.embedding_batch_size,
                    input_type=settings.embedding_input_type or None,
                    base_url=settings.openrouter_base_url,
                    http_referer=settings.openrouter_http_referer or None,
                    x_title=settings.openrouter_x_title or None,
                )
                if provider == "deepseek":
                    chat_api_key = settings.deepseek_api_key
                    chat_base_url = settings.deepseek_base_url
                    chat_models = settings.chat_models
                    chat_referer = None
                    chat_title = None
                else:
                    chat_api_key = settings.openrouter_api_key
                    chat_base_url = settings.openrouter_base_url
                    chat_models = settings.model_candidates
                    chat_referer = settings.openrouter_http_referer or None
                    chat_title = settings.openrouter_x_title or None

                app.state.chat_model = chat_models[0]
                llm = ChatClient(
                    chat_api_key,
                    chat_models,
                    provider=provider,
                    base_url=chat_base_url,
                    temperature=settings.llm_temperature,
                    max_tokens=settings.llm_max_tokens,
                    reasoning_effort=settings.llm_reasoning_effort or None,
                    thinking_disabled=settings.deepseek_thinking_disabled,
                    timeout=settings.request_timeout,
                    http_referer=chat_referer,
                    x_title=chat_title,
                )
                app.state.service = ChatService(
                    settings,
                    index,
                    embedder,
                    llm,
                )
            except Exception as exc:
                app.state.startup_error = str(exc)
                logger.exception("Aplikasi gagal menyiapkan service: %s", exc)

        yield

    app = FastAPI(
        title="TravelKita RAG — CS Copilot",
        description=(
            "Asisten knowledge base untuk agen Customer Service TravelKita. "
            "Data sintetis untuk portfolio."
        ),
        version="0.3.0",
        lifespan=lifespan,
    )
    templates = Jinja2Templates(directory=str(ROOT / "templates"))
    templates.env.filters["pct"] = lambda value: f"{float(value or 0) * 100:.0f}%"
    templates.env.filters["score"] = lambda value: f"{float(value or 0):.3f}"
    app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def enforce_rate_limit(request: Request) -> None:
        allowed, retry_after = request.app.state.rate_limiter.allow(client_key(request))
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Terlalu banyak request. Coba lagi sebentar.",
                headers={"Retry-After": str(retry_after)},
            )

    def get_index(request: Request) -> NumPyIndex:
        index = getattr(request.app.state, "index", None)
        if index is None:
            raise ServiceUnavailable("Index belum siap.")
        return index

    def get_service(request: Request) -> ChatService:
        chat_service = getattr(request.app.state, "service", None)
        if chat_service is None:
            raise ServiceUnavailable("Service chat belum siap. Cek konfigurasi server.")
        return chat_service

    def base_context(request: Request, active: str) -> dict[str, Any]:
        index = getattr(request.app.state, "index", None)
        service_ready = getattr(request.app.state, "service", None) is not None
        health = {
            "status": "ok" if index is not None and service_ready else "degraded",
            "index_version": index.manifest.get("index_version") if index else None,
        }
        return {
            "request": request,
            "active": active,
            "settings": request.app.state.settings,
            "health": health,
            "index_meta": index.manifest if index else None,
            "llm_provider": getattr(request.app.state, "chat_provider", "-"),
            "llm_model": getattr(request.app.state, "chat_model", "-"),
            "max_input_chars": request.app.state.settings.max_input_chars,
        }

    def render(
        request: Request,
        template: str,
        *,
        active: str,
        context: dict[str, Any] | None = None,
        status_code: int = 200,
    ) -> HTMLResponse:
        payload = base_context(request, active)
        payload.update(context or {})
        return templates.TemplateResponse(
            request=request,
            name=template,
            context=payload,
            status_code=status_code,
        )

    def find_document(index: NumPyIndex, doc_id: str) -> dict[str, Any] | None:
        summary = next(
            (
                document
                for document in index.manifest.get("documents", [])
                if document.get("doc_id") == doc_id
            ),
            None,
        )
        if summary is None:
            return None
        chunks = [
            {
                "chunk_id": chunk["chunk_id"],
                "section_path": chunk["section_path"],
                "chunk_type": chunk.get("chunk_type", "prose"),
                "text": chunk.get("text", ""),
                "token_estimate": chunk.get("token_estimate", 0),
            }
            for chunk in index.chunks
            if chunk["doc_id"] == doc_id
        ]
        return {**summary, "chunks": chunks}

    def html_rate_limit(request: Request) -> str | None:
        allowed, retry_after = request.app.state.rate_limiter.allow(client_key(request))
        if allowed:
            return None
        return f"Terlalu banyak request. Coba lagi dalam {retry_after} detik."

    @app.exception_handler(InputRejected)
    async def input_rejected_handler(request: Request, exc: InputRejected):
        return _error(400, "input_rejected", exc.reason, request)

    @app.exception_handler(ServiceUnavailable)
    async def service_unavailable_handler(request: Request, exc: ServiceUnavailable):
        return _error(503, "service_unavailable", str(exc), request)

    @app.exception_handler(UpstreamError)
    async def upstream_error_handler(request: Request, exc: UpstreamError):
        return _error(502, "upstream_error", str(exc), request)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return _error(422, "validation_error", "Input tidak valid.", request)

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException):
        return _error(
            exc.status_code,
            "http_error",
            str(exc.detail),
            request,
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error request_id=%s", _request_id(request))
        return _error(500, "internal_error", "Terjadi kesalahan internal.", request)

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def chat_page(request: Request) -> HTMLResponse:
        return render(
            request,
            "chat.html",
            active="chat",
            context={"suggested_questions": SUGGESTED_QUESTIONS},
        )

    @app.get("/internal/eval", response_class=HTMLResponse, include_in_schema=False)
    def eval_page(request: Request) -> HTMLResponse:
        view = load_retrieval_view(ROOT / "data/eval" / "retrieval_results.json")
        return render(request, "eval.html", active="internal", context={"view": view})

    @app.get("/internal/about", response_class=HTMLResponse, include_in_schema=False)
    def about_page(request: Request) -> HTMLResponse:
        return render(request, "about.html", active="internal")

    @app.get("/internal/documents", response_class=HTMLResponse, include_in_schema=False)
    def documents_page(request: Request) -> HTMLResponse:
        index = getattr(request.app.state, "index", None)
        documents = []
        if index is not None:
            documents = sorted(
                [
                    document
                    for document in index.manifest.get("documents", [])
                    if document.get("status") == "active"
                ],
                key=lambda item: item.get("doc_id", ""),
            )
        return render(
            request,
            "documents.html",
            active="internal",
            context={"documents": documents},
        )

    @app.get(
        "/internal/documents/{doc_id}",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    def document_page(request: Request, doc_id: str) -> HTMLResponse:
        index = getattr(request.app.state, "index", None)
        if index is None:
            return render(
                request,
                "error_page.html",
                active="internal",
                context={
                    "title": "Index belum siap",
                    "message": "Jalankan build index terlebih dahulu.",
                },
                status_code=503,
            )
        document = find_document(index, doc_id)
        if document is None:
            return render(
                request,
                "error_page.html",
                active="internal",
                context={
                    "title": "Dokumen tidak ditemukan",
                    "message": f"{doc_id} tidak ada di index aktif.",
                },
                status_code=404,
            )
        return render(
            request,
            "document_detail.html",
            active="internal",
            context={"document": document},
        )

    @app.post("/chat", response_class=HTMLResponse, include_in_schema=False)
    def chat_htmx(
        request: Request,
        message: str = Form(default=""),
        mode: str = Form("public"),
        debug: str | None = Form(default=None),
    ) -> HTMLResponse:
        limited = html_rate_limit(request)
        if limited:
            return render(
                request,
                "partials/error.html",
                active="chat",
                context={"title": "Rate limit", "message": limited},
            )

        service_local = getattr(request.app.state, "service", None)
        if service_local is None:
            return render(
                request,
                "partials/error.html",
                active="chat",
                context={
                    "title": "Service belum siap",
                    "message": "Index atau API key belum dikonfigurasi di server.",
                },
            )

        mode = mode if mode in {"agent", "public"} else "agent"
        try:
            response = service_local.answer(
                ChatRequest(message=message, mode=mode, debug=debug is not None)
            )
        except InputRejected as exc:
            return render(
                request,
                "partials/error.html",
                active="chat",
                context={"title": "Input ditolak", "message": exc.reason},
            )
        except ServiceUnavailable as exc:
            return render(
                request,
                "partials/error.html",
                active="chat",
                context={"title": "Service tidak tersedia", "message": str(exc)},
            )
        except Exception:
            logger.exception("UI chat error request_id=%s", _request_id(request))
            return render(
                request,
                "partials/error.html",
                active="chat",
                context={
                    "title": "Terjadi kesalahan",
                    "message": "Permintaan gagal diproses. Coba lagi sebentar.",
                },
            )

        return render(
            request,
            "partials/answer.html",
            active="chat",
            context={"response": response, "question": message, "mode": mode},
        )

    @app.post("/feedback", response_class=HTMLResponse, include_in_schema=False)
    def feedback_htmx(
        request: Request,
        message_id: str = Form(default=""),
        rating: str = Form(...),
        comment: str = Form(default=""),
    ) -> HTMLResponse:
        limited = html_rate_limit(request)
        if limited:
            return render(
                request,
                "partials/error.html",
                active="chat",
                context={"title": "Rate limit", "message": limited},
            )
        if rating not in {"up", "down"}:
            return render(
                request,
                "partials/error.html",
                active="chat",
                context={"title": "Feedback tidak valid", "message": "Rating harus up atau down."},
            )
        logger.info(
            "ui feedback request_id=%s message_id=%s rating=%s comment=%s",
            _request_id(request),
            message_id or "-",
            rating,
            redact_for_log(comment),
        )
        return render(request, "partials/feedback.html", active="chat")

    @app.get(
        "/partials/documents/{doc_id}",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    def source_drawer_partial(
        request: Request,
        doc_id: str,
        section: str | None = Query(default=None),
    ) -> HTMLResponse:
        index = getattr(request.app.state, "index", None)
        if index is None:
            return render(
                request,
                "partials/error.html",
                active="chat",
                context={"title": "Index belum siap", "message": "Dokumen tidak tersedia."},
            )
        document = find_document(index, doc_id)
        if document is None or document.get("audience") != "public":
            return render(
                request,
                "partials/error.html",
                active="chat",
                context={
                    "title": "Sumber tidak tersedia",
                    "message": "Informasi ini tidak dapat ditampilkan untuk pelanggan.",
                },
            )
        if section:
            document["chunks"] = [
                chunk for chunk in document["chunks"] if chunk["section_path"] == section
            ]
        return render(
            request,
            "partials/source_drawer.html",
            active="chat",
            context={"document": document},
        )

    @app.get("/api/v1/health", response_model=HealthResponse)
    def health(request: Request) -> HealthResponse:
        index = getattr(request.app.state, "index", None)
        service_ready = getattr(request.app.state, "service", None) is not None
        return HealthResponse(
            status="ok" if index is not None and service_ready else "degraded",
            index_loaded=index is not None,
            index_version=index.manifest.get("index_version") if index else None,
        )

    @app.get("/api/v1/ready", response_model=ReadyResponse)
    def ready(request: Request):
        index = getattr(request.app.state, "index", None)
        service_ready = getattr(request.app.state, "service", None) is not None
        payload = ReadyResponse(
            ready=index is not None and service_ready,
            index_loaded=index is not None,
            llm_configured=bool(getattr(request.app.state, "llm_configured", False)),
            index_version=index.manifest.get("index_version") if index else None,
        )
        if not payload.ready:
            return JSONResponse(status_code=503, content=payload.model_dump())
        return payload

    @app.post("/api/v1/chat", response_model=ChatResponse)
    def chat(
        payload: ChatRequest,
        request: Request,
        _: None = Depends(enforce_rate_limit),
    ) -> ChatResponse:
        chat_service = get_service(request)
        return chat_service.answer(payload)

    @app.get("/api/v1/documents", response_model=list[DocumentInfo])
    def list_documents(
        request: Request,
        category: str | None = Query(default=None),
        audience: str | None = Query(default=None),
        status: str | None = Query(default="active"),
    ) -> list[DocumentInfo]:
        index = get_index(request)
        documents: list[DocumentInfo] = []
        for document in index.manifest.get("documents", []):
            if category and document.get("category") != category:
                continue
            if audience and document.get("audience") != audience:
                continue
            if status and document.get("status") != status:
                continue
            documents.append(DocumentInfo(**document))
        return sorted(documents, key=lambda item: item.doc_id)

    @app.get("/api/v1/documents/{doc_id}", response_model=DocumentDetail)
    def get_document(
        doc_id: str,
        request: Request,
        audience: str | None = Query(default=None),
    ) -> DocumentDetail:
        index = get_index(request)
        summary: dict[str, Any] | None = None
        for document in index.manifest.get("documents", []):
            if document.get("doc_id") == doc_id:
                summary = document
                break
        if summary is None:
            raise HTTPException(status_code=404, detail=f"Dokumen {doc_id} tidak ditemukan.")

        chunks = [
            DocumentChunk(
                chunk_id=chunk["chunk_id"],
                section_path=chunk["section_path"],
                chunk_type=chunk.get("chunk_type", "prose"),
                text=chunk.get("text", ""),
                token_estimate=chunk.get("token_estimate", 0),
            )
            for chunk in index.chunks
            if chunk["doc_id"] == doc_id and (not audience or chunk.get("audience") == audience)
        ]
        return DocumentDetail(**summary, chunks=chunks)

    @app.get("/api/v1/meta", response_model=MetaResponse)
    def meta(request: Request) -> MetaResponse:
        index = get_index(request)
        settings_local: Settings = request.app.state.settings
        manifest = index.manifest
        return MetaResponse(
            index_version=manifest.get("index_version"),
            created_at=manifest.get("created_at"),
            embedding_model=manifest.get("embedding_model"),
            embedding_dimension=manifest.get("dimension"),
            chunk_count=manifest.get("chunk_count", len(index.chunks)),
            document_count=manifest.get("document_count", 0),
            llm_provider=getattr(request.app.state, "chat_provider", settings_local.chat_provider),
            llm_model=getattr(request.app.state, "chat_model", settings_local.llm_model),
            prompt_version=settings_local.prompt_version,
            status_counts=manifest.get("status_counts", {}),
        )

    @app.post("/api/v1/feedback", response_model=FeedbackResponse)
    def feedback(
        payload: FeedbackRequest,
        request: Request,
        _: None = Depends(enforce_rate_limit),
    ) -> FeedbackResponse:
        logger.info(
            "feedback request_id=%s message_id=%s rating=%s comment=%s",
            _request_id(request),
            payload.message_id or "-",
            payload.rating,
            redact_for_log(payload.comment or ""),
        )
        return FeedbackResponse(accepted=True, message="Terima kasih atas feedback-nya.")

    return app


app = create_app()
