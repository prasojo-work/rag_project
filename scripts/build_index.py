"""Build the offline NumPy + BM25 index from the Markdown knowledge base."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from app.rag.audit import audit_documents  # noqa: E402
from app.rag.chunking import chunk_documents  # noqa: E402
from app.rag.embeddings import get_embedding_provider  # noqa: E402

CHUNKER_VERSION = "1.0"


def _display(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _index_version(chunks: list) -> str:
    digest = hashlib.sha256(
        "\n".join(chunk.embedding_text for chunk in chunks).encode("utf-8")
    ).hexdigest()[:8]
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{digest}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="dokumen")
    parser.add_argument("--out", default="data/index")
    parser.add_argument(
        "--provider",
        default="openrouter",
        choices=["openrouter", "hash"],
        help="hash hanya untuk smoke test, bukan index produksi",
    )
    parser.add_argument("--model", default=None)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--max-tokens", type=int, default=500)
    parser.add_argument("--table-max-tokens", type=int, default=900)
    parser.add_argument(
        "--include-fixtures",
        action="store_true",
        help="Ikutkan dokumen superseded/noise untuk eksperimen robustness",
    )
    parser.add_argument(
        "--input-type",
        default=os.getenv("EMBEDDING_INPUT_TYPE", "") or None,
        help="search_document/search_query jika model mendukung",
    )
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    root = Path(args.root) if Path(args.root).is_absolute() else ROOT / args.root
    out = Path(args.out) if Path(args.out).is_absolute() else ROOT / args.out

    audit = audit_documents(root)
    if audit.has_errors():
        print("Audit menemukan error. Perbaiki dulu sebelum build index.", file=sys.stderr)
        for issue in audit.errors:
            print(f"  ERROR [{issue.code}] {issue.source_path}: {issue.message}", file=sys.stderr)
        return 1

    if args.include_fixtures:
        documents = audit.documents
    else:
        documents = [document for document in audit.documents if document.status == "active"]

    if not documents:
        print("Tidak ada dokumen yang bisa di-index.", file=sys.stderr)
        return 1

    chunks = chunk_documents(
        documents,
        max_tokens=args.max_tokens,
        table_max_tokens=args.table_max_tokens,
    )
    if not chunks:
        print("Chunker tidak menghasilkan chunk.", file=sys.stderr)
        return 1

    print("Build index")
    print(f"  Dokumen       : {len(documents)}")
    print(f"  Chunk         : {len(chunks)}")
    print(f"  Provider      : {args.provider}")
    print(f"  Rata-rata token: {sum(c.token_estimate for c in chunks) / len(chunks):.1f}")

    provider = get_embedding_provider(
        args.provider,
        model=args.model,
        batch_size=args.batch_size,
        input_type=args.input_type,
        base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        http_referer=os.getenv("OPENROUTER_HTTP_REFERER") or None,
        x_title=os.getenv("OPENROUTER_X_TITLE") or None,
    )
    if provider.synthetic:
        print(
            "  PERINGATAN    : provider hash bersifat sintetis; "
            "jangan pakai sebagai baseline kualitas.",
            file=sys.stderr,
        )

    print(
        f"  Embedding     : {provider.model} "
        f"({math.ceil(len(chunks) / args.batch_size)} request batch)"
    )
    embeddings = provider.embed(
        [chunk.embedding_text for chunk in chunks],
        input_type=args.input_type,
    )
    if embeddings.shape[0] != len(chunks):
        print("Jumlah embedding tidak sesuai jumlah chunk.", file=sys.stderr)
        return 1

    out.mkdir(parents=True, exist_ok=True)
    with (out / "chunks.jsonl").open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(json.dumps(chunk.to_dict(), ensure_ascii=False) + "\n")
    np.save(out / "embeddings.npy", embeddings.astype(np.float32))

    document_summaries = []
    for document in sorted(documents, key=lambda item: item.doc_id):
        document_summaries.append(
            {
                **document.summary(),
                "chunk_count": sum(1 for chunk in chunks if chunk.doc_id == document.doc_id),
            }
        )

    manifest = {
        "index_version": _index_version(chunks),
        "created_at": datetime.now(UTC).isoformat(),
        "source_root": str(root.relative_to(ROOT)) if root.is_relative_to(ROOT) else str(root),
        "chunker_version": CHUNKER_VERSION,
        "max_tokens": args.max_tokens,
        "table_max_tokens": args.table_max_tokens,
        "embedding_provider": provider.name,
        "embedding_model": provider.model,
        "embedding_synthetic": provider.synthetic,
        "dimension": int(embeddings.shape[1]),
        "normalized": True,
        "document_count": len(documents),
        "chunk_count": len(chunks),
        "status_counts": {
            status: sum(1 for document in documents if document.status == status)
            for status in sorted({document.status for document in documents})
        },
        "documents": document_summaries,
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"  Index version : {manifest['index_version']}")
    print(f"  Output        : {_display(out)}")
    print("  Contoh chunk  :")
    for chunk in chunks[:3]:
        print(f"    - {chunk.chunk_id} ({chunk.chunk_type}, {chunk.token_estimate} token)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
