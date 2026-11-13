"""Parse and validate structured answers from the chat model."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.rag.guardrails import redact_for_log
from app.rag.llm import ChatClient, LLMError

logger = logging.getLogger(__name__)

_CODE_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)


class GenerationError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class LLMAnswer(BaseModel):
    answerable: bool
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    internal_notes: str = ""
    customer_reply: str = ""
    cited_doc_ids: list[str] = Field(default_factory=list)
    needs_escalation: bool = False
    escalation_reason: str | None = None

    @field_validator("confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        return min(1.0, max(0.0, number))

    @field_validator("internal_notes", "customer_reply", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return "" if value is None else str(value)

    @field_validator("cited_doc_ids", mode="before")
    @classmethod
    def normalize_cited_doc_ids(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []


@dataclass
class GenerationResult:
    answer: LLMAnswer
    raw_content: str
    model: str
    usage: dict[str, Any] | None
    attempts: int


def extract_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    fence = _CODE_FENCE_RE.match(text)
    if fence:
        text = fence.group(1).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise GenerationError("Model tidak mengembalikan objek JSON.") from None
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise GenerationError(f"JSON model tidak valid: {exc}") from exc

    if not isinstance(parsed, dict):
        raise GenerationError("JSON model bukan objek.")
    return parsed


def parse_answer(content: str) -> LLMAnswer:
    parsed = extract_json_object(content)
    try:
        return LLMAnswer.model_validate(parsed)
    except Exception as exc:
        raise GenerationError(f"Skema jawaban tidak valid: {exc}") from exc


def generate_answer(
    llm: ChatClient,
    messages: list[dict[str, str]],
    *,
    max_attempts: int = 2,
) -> GenerationResult:
    """Call the model and retry once if the JSON answer is malformed."""

    working_messages = list(messages)
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = llm.complete(working_messages, response_format=True)
        except LLMError as exc:
            raise GenerationError(str(exc), status=exc.status) from exc

        try:
            answer = parse_answer(result.content)
            return GenerationResult(
                answer=answer,
                raw_content=result.content,
                model=result.model,
                usage=result.usage,
                attempts=attempt,
            )
        except GenerationError as exc:
            last_error = exc
            logger.warning(
                "Parse answer gagal attempt=%s finish_reason=%s usage=%s content=%s",
                attempt,
                result.finish_reason,
                result.usage,
                redact_for_log(result.content, max_chars=800),
            )
            if attempt >= max_attempts:
                break
            working_messages = [
                *messages,
                {"role": "assistant", "content": result.content},
                {
                    "role": "user",
                    "content": (
                        "JSON sebelumnya tidak valid atau tidak sesuai skema. "
                        "Kembalikan HANYA objek JSON valid sesuai skema, tanpa "
                        "penjelasan dan tanpa markdown code fence."
                    ),
                },
            ]

    raise GenerationError(f"Jawaban model tidak dapat diparse: {last_error}")
