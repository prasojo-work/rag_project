"""LLM-as-judge for generation evaluation."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.rag.generation import extract_json_object
from app.rag.llm import ChatClient

logger = logging.getLogger(__name__)


class JudgeError(RuntimeError):
    pass


class JudgeResult(BaseModel):
    correctness: int = Field(ge=1, le=5)
    completeness: int = Field(ge=1, le=5)
    faithfulness: int = Field(ge=1, le=5)
    citation_support: int = Field(ge=1, le=5)
    escalation: int = Field(ge=1, le=5)
    hallucination: bool = False
    notes: str = ""

    @field_validator(
        "correctness",
        "completeness",
        "faithfulness",
        "citation_support",
        "escalation",
        mode="before",
    )
    @classmethod
    def normalize_score(cls, value: Any) -> int:
        try:
            number = int(float(value))
        except (TypeError, ValueError):
            return 1
        return min(5, max(1, number))

    @field_validator("notes", mode="before")
    @classmethod
    def normalize_notes(cls, value: Any) -> str:
        return "" if value is None else str(value)


JUDGE_SYSTEM_PROMPT = """\
Anda adalah evaluator independen untuk sistem RAG customer service TravelKita.
Tugas Anda menilai kualitas jawaban model terhadap ground truth dan konteks
yang diberikan. Bersikaplah ketat, tetapi adil.

Rubrik 1-5:
- correctness: seberapa benar fakta/angka/kebijakan dibanding ground truth.
- completeness: seberapa lengkap informasi penting yang diminta.
- faithfulness: seberapa jauh jawaban hanya bersandar pada konteks, tanpa
  mengarang kebijakan, angka, status, atau ketersediaan.
- citation_support: apakah sitasi yang diberikan benar-benar mendukung klaim.
- escalation: apakah keputusan menjawab/menolak/menawarkan eskalasi tepat.
- hallucination: true jika ada klaim faktual yang tidak didukung konteks atau
  bertentangan dengan ground truth.
- notes: alasan singkat, sebutkan fakta yang salah/hilang bila ada.

Jangan memberi nilai tinggi hanya karena jawaban panjang. Penalti angka yang
salah, kebijakan yang dikarang, dan janji di luar kebijakan.

Kembalikan HANYA JSON valid:
{
  "correctness": 1,
  "completeness": 1,
  "faithfulness": 1,
  "citation_support": 1,
  "escalation": 1,
  "hallucination": false,
  "notes": "..."
}
"""


def build_judge_messages(
    *,
    question: str,
    ground_truth: str,
    context: str,
    customer_reply: str,
    internal_notes: str,
    expected_refusal: bool,
) -> list[dict[str, str]]:
    user = "\n".join(
        [
            f"EXPECTED_REFUSAL: {str(expected_refusal).lower()}",
            "",
            "PERTANYAAN:",
            question,
            "",
            "GROUND TRUTH:",
            ground_truth,
            "",
            "KONTEKS YANG DIBERIKAN KE MODEL:",
            context or "(tidak ada konteks)",
            "",
            "JAWABAN PELANGGAN:",
            customer_reply or "(kosong)",
            "",
            "CATATAN INTERNAL:",
            internal_notes or "(kosong)",
            "",
            "Nilai sesuai rubrik. Kembalikan hanya JSON.",
        ]
    )
    return [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def parse_judge(content: str) -> JudgeResult:
    parsed = extract_json_object(content)
    return JudgeResult.model_validate(parsed)


def judge_answer(
    client: ChatClient,
    *,
    question: str,
    ground_truth: str,
    context: str,
    customer_reply: str,
    internal_notes: str,
    expected_refusal: bool,
    max_attempts: int = 2,
) -> tuple[JudgeResult, str]:
    messages = build_judge_messages(
        question=question,
        ground_truth=ground_truth,
        context=context,
        customer_reply=customer_reply,
        internal_notes=internal_notes,
        expected_refusal=expected_refusal,
    )
    last_error: Exception | None = None
    content = ""
    for attempt in range(1, max_attempts + 1):
        try:
            result = client.complete(messages, response_format=True)
            content = result.content
            return parse_judge(content), content
        except Exception as exc:  # Judge failure should not abort eval.
            last_error = exc
            logger.warning("Judge gagal attempt=%s: %s", attempt, exc)
            if attempt < max_attempts:
                messages = [
                    *messages,
                    {"role": "assistant", "content": content or "(kosong)"},
                    {
                        "role": "user",
                        "content": "JSON tidak valid. Kembalikan hanya JSON sesuai skema.",
                    },
                ]
    raise JudgeError(f"Judge gagal: {last_error}")


def judge_to_dict(result: JudgeResult) -> dict[str, Any]:
    return result.model_dump()
