from __future__ import annotations

import pytest

from app.rag.generation import (
    GenerationError,
    extract_json_object,
    generate_answer,
    parse_answer,
)
from tests.support import FakeLLM


def test_extract_json_from_code_fence() -> None:
    parsed = extract_json_object('```json\n{"answerable": true, "customer_reply": "Halo"}\n```')
    assert parsed["answerable"] is True


def test_parse_answer_clamps_confidence_and_normalizes_none() -> None:
    answer = parse_answer(
        '{"answerable": true, "confidence": 1.5, "customer_reply": null, '
        '"internal_notes": null, "cited_doc_ids": "KB-POL-002"}'
    )
    assert answer.confidence == 1.0
    assert answer.customer_reply == ""
    assert answer.internal_notes == ""
    assert answer.cited_doc_ids == ["KB-POL-002"]


def test_invalid_json_raises() -> None:
    with pytest.raises(GenerationError):
        extract_json_object("bukan json")


def test_generate_answer_retries_malformed_json() -> None:
    llm = FakeLLM("bukan json", '{"answerable": true, "customer_reply": "ok"}')
    result = generate_answer(llm, [{"role": "user", "content": "tes"}])
    assert result.attempts == 2
    assert result.answer.answerable is True
    assert len(llm.calls) == 2
