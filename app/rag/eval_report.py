"""Load retrieval evaluation results for the Jinja dashboard."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MODE_LABELS = {
    "dense": "Dense",
    "bm25": "BM25",
    "hybrid": "Hybrid RRF",
}


def load_retrieval_view(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    modes: list[dict[str, Any]] = []
    for key in ("dense", "bm25", "hybrid"):
        mode = (data.get("modes") or {}).get(key)
        if not mode:
            continue
        modes.append(
            {
                "key": key,
                "label": MODE_LABELS.get(key, key),
                "overall": mode.get("overall", {}),
                "by_difficulty": mode.get("by_difficulty", {}),
            }
        )

    failure_cases: list[dict[str, Any]] = []
    hybrid = (data.get("modes") or {}).get("hybrid") or next(
        iter((data.get("modes") or {}).values()), None
    )
    if hybrid:
        for question in hybrid.get("questions", []):
            relevant = question.get("relevant") or []
            recall = (question.get("metrics") or {}).get("recall@5")
            if relevant and recall is not None and recall < 1.0:
                failure_cases.append(
                    {
                        "question": question.get("question", ""),
                        "difficulty": question.get("difficulty", "-"),
                        "category": question.get("category", "-"),
                        "recall": recall,
                        "relevant": relevant,
                        "ranked": (question.get("ranked_docs") or [])[:5],
                    }
                )
    failure_cases.sort(key=lambda item: item["recall"])

    return {
        "meta": data.get("meta", {}),
        "modes": modes,
        "failure_cases": failure_cases[:8],
        "failure_count": len(failure_cases),
    }
