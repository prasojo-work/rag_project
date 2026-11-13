"""Validate index artifacts and optionally check staleness against source docs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from app.rag.audit import audit_documents  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", default="data/index")
    parser.add_argument(
        "--root",
        default=None,
        help="Opsional: cek apakah index masih cocok dengan dokumen sumber",
    )
    args = parser.parse_args()

    index_dir = Path(args.index) if Path(args.index).is_absolute() else ROOT / args.index
    errors: list[str] = []
    warnings: list[str] = []

    manifest_path = index_dir / "manifest.json"
    chunks_path = index_dir / "chunks.jsonl"
    embeddings_path = index_dir / "embeddings.npy"
    for path in (manifest_path, chunks_path, embeddings_path):
        if not path.exists():
            print(f"ERROR: file tidak ditemukan: {path}", file=sys.stderr)
            return 1

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    chunks = [
        json.loads(line)
        for line in chunks_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    embeddings = np.load(embeddings_path)

    if manifest.get("chunk_count") != len(chunks):
        errors.append(f"manifest.chunk_count {manifest.get('chunk_count')} != {len(chunks)} chunk")
    if embeddings.shape[0] != len(chunks):
        errors.append(f"embeddings rows {embeddings.shape[0]} != {len(chunks)} chunk")
    if manifest.get("dimension") != embeddings.shape[1]:
        errors.append(f"manifest.dimension {manifest.get('dimension')} != {embeddings.shape[1]}")
    if not np.isfinite(embeddings).all():
        errors.append("embeddings mengandung NaN/Inf")

    norms = np.linalg.norm(embeddings, axis=1)
    if len(norms) and not np.allclose(norms, 1.0, atol=1e-4):
        warnings.append("sebagian vektor tidak L2-normalized")

    chunk_ids = [chunk.get("chunk_id") for chunk in chunks]
    if len(set(chunk_ids)) != len(chunk_ids):
        errors.append("chunk_id duplikat")

    required = {"chunk_id", "doc_id", "status", "audience", "text", "section_path"}
    for chunk in chunks:
        missing = required - set(chunk)
        if missing:
            errors.append(f"chunk {chunk.get('chunk_id')} kehilangan field {sorted(missing)}")

    if args.root:
        root = Path(args.root) if Path(args.root).is_absolute() else ROOT / args.root
        audit = audit_documents(root)
        active_docs = {
            document.doc_id: document for document in audit.documents if document.status == "active"
        }
        indexed_docs = {
            document["doc_id"]: document
            for document in manifest.get("documents", [])
            if document.get("status") == "active"
        }
        for doc_id in sorted(set(active_docs) - set(indexed_docs)):
            warnings.append(f"dokumen aktif belum ada di index: {doc_id}")
        for doc_id in sorted(set(indexed_docs) - set(active_docs)):
            warnings.append(f"dokumen di index sudah tidak aktif/hilang: {doc_id}")
        for doc_id in sorted(set(active_docs) & set(indexed_docs)):
            if active_docs[doc_id].doc_hash != indexed_docs[doc_id].get("doc_hash"):
                warnings.append(f"dokumen berubah, index perlu dibangun ulang: {doc_id}")

    print(f"Index     : {index_dir}")
    print(f"Chunks    : {len(chunks)}")
    print(f"Dimensi   : {embeddings.shape[1]}")
    print(f"Versi     : {manifest.get('index_version')}")
    print(f"Model     : {manifest.get('embedding_model')}")
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
