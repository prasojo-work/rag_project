from __future__ import annotations

import pytest

from app.rag.metrics import (
    hit_at_k,
    mrr_at_k,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    unique_doc_ranking,
)


def test_unique_doc_ranking_dedupes_in_order() -> None:
    assert unique_doc_ranking(["a", "a", "b", "c", "b"]) == ["a", "b", "c"]


def test_recall_and_hit() -> None:
    relevant = {"a", "b"}
    ranked = ["a", "c", "b"]
    assert recall_at_k(relevant, ranked, k=2) == 0.5
    assert hit_at_k(relevant, ranked, k=1) == 1.0
    assert precision_at_k(relevant, ranked, k=3) == pytest.approx(2 / 3)


def test_mrr() -> None:
    assert mrr_at_k({"b"}, ["a", "b"], k=10) == 0.5
    assert mrr_at_k({"x"}, ["a", "b"], k=10) == 0.0


def test_ndcg() -> None:
    assert ndcg_at_k({"a"}, ["a"], k=5) == 1.0
    assert ndcg_at_k({"a"}, ["b", "a"], k=5) < 1.0


def test_unanswerable_returns_none() -> None:
    assert recall_at_k(set(), ["a"], k=5) is None
    assert mrr_at_k(set(), ["a"], k=5) is None
    assert ndcg_at_k(set(), ["a"], k=5) is None
