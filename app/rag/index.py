"""In-memory NumPy + BM25 index for a small knowledge base."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
from rank_bm25 import BM25Okapi

from app.rag.text import tokenize


@dataclass
class SearchHit:
    chunk: dict[str, Any]
    dense_score: float | None = None
    bm25_score: float | None = None
    rrf_score: float | None = None
    dense_rank: int | None = None
    bm25_rank: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class NumPyIndex:
    """Dense cosine search + BM25, fused with Reciprocal Rank Fusion."""

    def __init__(
        self,
        chunks: list[dict[str, Any]],
        embeddings: np.ndarray,
        manifest: dict[str, Any],
    ) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"Jumlah chunk ({len(chunks)}) != jumlah embedding ({len(embeddings)})"
            )
        if not chunks:
            raise ValueError("Index kosong")

        self.chunks = chunks
        self.embeddings = np.asarray(embeddings, dtype=np.float32)
        self.manifest = manifest
        norms = np.linalg.norm(self.embeddings, axis=1, keepdims=True)
        self.embeddings = self.embeddings / np.maximum(norms, 1e-12)

        self.statuses = np.array([chunk.get("status", "active") for chunk in chunks])
        self.audiences = np.array([chunk.get("audience", "public") for chunk in chunks])
        self.effective_dates = np.array(
            [chunk.get("effective_date") or chunk.get("last_updated") or "" for chunk in chunks]
        )
        self.doc_ids = np.array([chunk["doc_id"] for chunk in chunks])

        # BM25 gets title + section context in addition to the body. This matters
        # for FAQ chunks whose body does not repeat the H1 question.
        self._tokenized = [
            tokenize(
                " ".join(
                    [
                        chunk.get("title", ""),
                        chunk.get("section_path", ""),
                        chunk.get("text", ""),
                    ]
                )
            )
            for chunk in chunks
        ]
        self.bm25 = BM25Okapi(self._tokenized) if any(self._tokenized) else None

    @classmethod
    def load(cls, index_dir: Path | str) -> NumPyIndex:
        index_dir = Path(index_dir)
        manifest = json.loads((index_dir / "manifest.json").read_text(encoding="utf-8"))
        chunks = [
            json.loads(line)
            for line in (index_dir / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        embeddings = np.load(index_dir / "embeddings.npy")
        dimension = manifest.get("dimension")
        if dimension and embeddings.shape[1] != dimension:
            raise ValueError(f"Dimensi embedding {embeddings.shape[1]} != manifest {dimension}")
        return cls(chunks=chunks, embeddings=embeddings, manifest=manifest)

    def _mask(
        self,
        status: str | None = "active",
        audience: str | None = None,
        as_of: str | None = None,
    ) -> np.ndarray:
        mask = np.ones(len(self.chunks), dtype=bool)
        if status:
            mask &= self.statuses == status
        if audience:
            mask &= self.audiences == audience
        if as_of:
            mask &= self.effective_dates <= as_of
        return mask

    @staticmethod
    def _ranked(
        scores: np.ndarray, mask: np.ndarray, min_score: float | None = None
    ) -> list[tuple[int, float]]:
        valid = np.flatnonzero(mask)
        if not len(valid):
            return []
        if min_score is not None:
            valid = valid[scores[valid] > min_score]
        if not len(valid):
            return []
        order = valid[np.argsort(-scores[valid], kind="stable")]
        return [(int(index), float(scores[index])) for index in order]

    def dense_ranking(
        self,
        query_vector: np.ndarray,
        *,
        status: str | None = "active",
        audience: str | None = None,
        as_of: str | None = None,
    ) -> list[tuple[int, float]]:
        query_vector = np.asarray(query_vector, dtype=np.float32).reshape(-1)
        if query_vector.shape[0] != self.embeddings.shape[1]:
            raise ValueError(
                f"Dimensi query {query_vector.shape[0]} != index {self.embeddings.shape[1]}"
            )
        norm = np.linalg.norm(query_vector)
        if norm:
            query_vector = query_vector / norm
        scores = self.embeddings @ query_vector
        return self._ranked(scores, self._mask(status, audience, as_of))

    def bm25_ranking(
        self,
        query: str,
        *,
        status: str | None = "active",
        audience: str | None = None,
        as_of: str | None = None,
    ) -> list[tuple[int, float]]:
        if self.bm25 is None:
            return []
        tokens = tokenize(query)
        if not tokens:
            return []
        scores = np.asarray(self.bm25.get_scores(tokens), dtype=np.float64)
        return self._ranked(scores, self._mask(status, audience, as_of), min_score=0.0)

    @staticmethod
    def _fuse(
        dense: list[tuple[int, float]],
        bm25: list[tuple[int, float]],
        *,
        rrf_k: int = 60,
        dense_weight: float = 1.0,
        bm25_weight: float = 1.0,
    ) -> list[tuple[int, float]]:
        scores: dict[int, float] = {}
        for rank, (index, _) in enumerate(dense, start=1):
            scores[index] = scores.get(index, 0.0) + dense_weight / (rrf_k + rank)
        for rank, (index, _) in enumerate(bm25, start=1):
            scores[index] = scores.get(index, 0.0) + bm25_weight / (rrf_k + rank)
        return sorted(scores.items(), key=lambda item: (-item[1], item[0]))

    def search(
        self,
        query: str,
        query_vector: np.ndarray | None,
        *,
        top_k: int = 10,
        mode: str = "hybrid",
        status: str | None = "active",
        audience: str | None = None,
        as_of: str | None = None,
        rrf_k: int = 60,
        dense_weight: float = 1.0,
        bm25_weight: float = 1.0,
    ) -> list[SearchHit]:
        mode = mode.lower()
        if mode not in {"dense", "bm25", "hybrid"}:
            raise ValueError(f"Mode retrieval tidak dikenal: {mode}")
        if mode in {"dense", "hybrid"} and query_vector is None:
            raise ValueError(f"Mode {mode} membutuhkan query_vector")

        dense = (
            self.dense_ranking(query_vector, status=status, audience=audience, as_of=as_of)
            if query_vector is not None
            else []
        )
        bm25 = self.bm25_ranking(query, status=status, audience=audience, as_of=as_of)
        dense_scores = dict(dense)
        bm25_scores = dict(bm25)
        dense_ranks = {index: rank for rank, (index, _) in enumerate(dense, start=1)}
        bm25_ranks = {index: rank for rank, (index, _) in enumerate(bm25, start=1)}

        if mode == "dense":
            selected = [(index, score) for index, score in dense[:top_k]]
        elif mode == "bm25":
            selected = [(index, score) for index, score in bm25[:top_k]]
        else:
            fused = self._fuse(
                dense,
                bm25,
                rrf_k=rrf_k,
                dense_weight=dense_weight,
                bm25_weight=bm25_weight,
            )
            selected = fused[:top_k]

        return [
            SearchHit(
                chunk=self.chunks[index],
                dense_score=dense_scores.get(index),
                bm25_score=bm25_scores.get(index),
                rrf_score=score if mode == "hybrid" else None,
                dense_rank=dense_ranks.get(index),
                bm25_rank=bm25_ranks.get(index),
            )
            for index, score in selected
        ]

    def stats(self) -> dict[str, Any]:
        return {
            "chunks": len(self.chunks),
            "documents": len({chunk["doc_id"] for chunk in self.chunks}),
            "embedding_dimension": int(self.embeddings.shape[1]),
            "status_counts": {
                status: int((self.statuses == status).sum())
                for status in sorted(set(self.statuses.tolist()))
            },
            "index_version": self.manifest.get("index_version"),
        }
