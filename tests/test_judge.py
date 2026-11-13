from __future__ import annotations

import pytest

from app.rag.generation import GenerationError
from app.rag.judge import build_judge_messages, parse_judge


def test_parse_judge_valid() -> None:
    result = parse_judge(
        '{"correctness": 5, "completeness": 4, "faithfulness": 5, '
        '"citation_support": 5, "escalation": 4, "hallucination": false, '
        '"notes": "baik"}'
    )
    assert result.correctness == 5
    assert result.hallucination is False


def test_parse_judge_clamps_scores() -> None:
    result = parse_judge(
        '{"correctness": 9, "completeness": 0, "faithfulness": "4", '
        '"citation_support": 3, "escalation": 2, "hallucination": false}'
    )
    assert result.correctness == 5
    assert result.completeness == 1
    assert result.faithfulness == 4


def test_parse_judge_invalid_raises() -> None:
    with pytest.raises(GenerationError):
        parse_judge("bukan json")


def test_build_judge_messages_contains_required_fields() -> None:
    messages = build_judge_messages(
        question="Refund GoPay?",
        ground_truth="1-3 hari kerja",
        context="Konteks refund",
        customer_reply="Refund 1-3 hari.",
        internal_notes="Catatan",
        expected_refusal=False,
    )
    user = messages[1]["content"]
    assert "Refund GoPay?" in user
    assert "1-3 hari kerja" in user
    assert "EXPECTED_REFUSAL: false" in user
