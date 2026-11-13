from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from app.rag.embeddings import HashEmbeddings
from app.rag.index import NumPyIndex


def make_chunk(
    chunk_id: str,
    doc_id: str,
    text: str,
    *,
    status: str = "active",
    effective_date: str = "2025-01-01",
) -> dict:
    return {
        "chunk_id": chunk_id,
        "doc_id": doc_id,
        "title": doc_id,
        "category": "policy",
        "subcategory": "refund",
        "version": "1.0",
        "effective_date": effective_date,
        "last_updated": effective_date,
        "status": status,
        "audience": "public",
        "section_path": "Umum",
        "chunk_type": "prose",
        "text": text,
        "embedding_text": text,
        "token_estimate": 10,
        "source_path": f"{doc_id}.md",
        "doc_hash": "hash",
        "chunk_hash": chunk_id,
    }


def build_index() -> NumPyIndex:
    chunks = [
        make_chunk("c1", "KB-POL-001", "Refund ke GoPay diproses 1 sampai 3 hari kerja."),
        make_chunk("c2", "KB-POL-002", "Pembatalan tiket pesawat non-refundable."),
        make_chunk(
            "c3",
            "KB-POL-003",
            "Kebijakan lama refund 14 hari kerja.",
            status="superseded",
        ),
        make_chunk(
            "c4",
            "KB-POL-004",
            "Aturan baru berlaku tahun depan.",
            effective_date="2099-01-01",
        ),
    ]
    texts = [chunk["text"] for chunk in chunks]
    vectors = HashEmbeddings().embed(texts)
    return NumPyIndex(
        chunks=chunks,
        embeddings=vectors,
        manifest={"index_version": "test", "dimension": vectors.shape[1]},
    )


def test_dense_search_returns_relevant_doc() -> None:
    index = build_index()
    query = "refund gopay berapa hari"
    vector = HashEmbeddings().embed([query])[0]
    hits = index.search(query, vector, top_k=2, mode="dense")
    assert hits
    assert hits[0].chunk["doc_id"] == "KB-POL-001"


def test_hybrid_filters_superseded_and_future_docs() -> None:
    index = build_index()
    query = "refund 14 hari kerja"
    vector = HashEmbeddings().embed([query])[0]
    hits = index.search(
        query,
        vector,
        top_k=10,
        mode="hybrid",
        status="active",
        as_of="2026-01-01",
    )
    doc_ids = {hit.chunk["doc_id"] for hit in hits}
    assert "KB-POL-003" not in doc_ids
    assert "KB-POL-004" not in doc_ids


def test_bm25_finds_exact_number() -> None:
    index = build_index()
    vector = HashEmbeddings().embed(["placeholder"])[0]
    hits = index.search("14 hari kerja", vector, top_k=5, mode="bm25", status=None)
    assert any(hit.chunk["doc_id"] == "KB-POL-003" for hit in hits)


def test_load_roundtrip(tmp_path: Path) -> None:
    chunks = [
        make_chunk("c1", "KB-POL-001", "Refund ke GoPay 1 sampai 3 hari kerja."),
        make_chunk("c2", "KB-POL-002", "Pembatalan tiket pesawat."),
    ]
    vectors = HashEmbeddings().embed([chunk["text"] for chunk in chunks])
    index_dir = tmp_path / "index"
    index_dir.mkdir()
    (index_dir / "chunks.jsonl").write_text(
        "\n".join(json.dumps(chunk) for chunk in chunks) + "\n", encoding="utf-8"
    )
    np.save(index_dir / "embeddings.npy", vectors)
    (index_dir / "manifest.json").write_text(
        json.dumps({"index_version": "test", "dimension": vectors.shape[1]}),
        encoding="utf-8",
    )

    loaded = NumPyIndex.load(index_dir)
    assert loaded.stats()["chunks"] == 2
    assert loaded.stats()["documents"] == 2
