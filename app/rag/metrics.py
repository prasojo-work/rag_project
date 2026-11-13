"""Retrieval metrics for doc-level evaluation."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence


def unique_doc_ranking(doc_ids: Iterable[str], k: int | None = None) -> list[str]:
    seen: set[str] = set()
    ranking: list[str] = []
    for doc_id in doc_ids:
        if doc_id in seen:
            continue
        seen.add(doc_id)
        ranking.append(doc_id)
        if k is not None and len(ranking) >= k:
            break
    return ranking


def recall_at_k(relevant: set[str], ranked: Sequence[str], k: int = 5) -> float | None:
    if not relevant:
        return None
    return len(set(ranked[:k]) & relevant) / len(relevant)


def hit_at_k(relevant: set[str], ranked: Sequence[str], k: int = 5) -> float | None:
    if not relevant:
        return None
    return 1.0 if set(ranked[:k]) & relevant else 0.0


def precision_at_k(relevant: set[str], ranked: Sequence[str], k: int = 5) -> float | None:
    if not relevant:
        return None
    top = ranked[:k]
    if not top:
        return 0.0
    return len(set(top) & relevant) / len(top)


def mrr_at_k(relevant: set[str], ranked: Sequence[str], k: int = 10) -> float | None:
    if not relevant:
        return None
    for rank, doc_id in enumerate(ranked[:k], start=1):
        if doc_id in relevant:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(relevant: set[str], ranked: Sequence[str], k: int = 5) -> float | None:
    if not relevant:
        return None

    dcg = 0.0
    for rank, doc_id in enumerate(ranked[:k], start=1):
        if doc_id in relevant:
            dcg += 1.0 / math.log2(rank + 1)

    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    if idcg == 0:
        return None
    return dcg / idcg


def mean(values: Iterable[float | None]) -> float | None:
    usable = [value for value in values if value is not None]
    if not usable:
        return None
    return sum(usable) / len(usable)
