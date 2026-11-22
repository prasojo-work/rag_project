"""Evaluate dense, BM25, and hybrid retrieval against the 50-question set."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.rag.embeddings import get_embedding_provider  # noqa: E402
from app.rag.index import NumPyIndex  # noqa: E402
from app.rag.metrics import (  # noqa: E402
    hit_at_k,
    mean,
    mrr_at_k,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    unique_doc_ranking,
)

METRIC_KEYS = ["recall@5", "hit@5", "precision@5", "mrr@10", "ndcg@5"]


def _question_metrics(relevant: set[str], ranked: list[str]) -> dict[str, float | None]:
    return {
        "recall@5": recall_at_k(relevant, ranked, k=5),
        "hit@5": hit_at_k(relevant, ranked, k=5),
        "precision@5": precision_at_k(relevant, ranked, k=5),
        "mrr@10": mrr_at_k(relevant, ranked, k=10),
        "ndcg@5": ndcg_at_k(relevant, ranked, k=5),
    }


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    answerable = [row for row in rows if row["relevant"]]
    return {
        "count": len(rows),
        "answerable": len(answerable),
        "unanswerable": len(rows) - len(answerable),
        **{key: mean(row["metrics"][key] for row in answerable) for key in METRIC_KEYS},
    }


def _group(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(field, "-"))].append(row)
    return {key: _aggregate(value) for key, value in sorted(grouped.items())}


def _fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:.3f}"


def _display(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def main() -> int:
    # Load .env first: argparse defaults are derived from it, and reading
    # os.getenv() before load_dotenv() silently returned None.
    load_dotenv(ROOT / ".env")
    settings = Settings()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", default="data/index")
    parser.add_argument("--eval", default="hasil_evaluasi/eval_set.json")
    parser.add_argument("--out", default="data/eval")
    parser.add_argument(
        "--provider",
        default=None,
        help=(
            "openrouter | hash | none (BM25-only) | nama endpoint "
            f"OpenAI-compatible. Default: {settings.embedding_provider_name}"
        ),
    )
    parser.add_argument("--model", default=None)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--modes", default="dense,bm25,hybrid")
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Batasi jumlah pertanyaan (untuk menghemat kuota saat debug)",
    )
    parser.add_argument(
        "--input-type",
        default=None,
        help="Default: EMBEDDING_INPUT_TYPE dari .env (wajib untuk model asimetris)",
    )
    args = parser.parse_args()
    input_type = args.input_type or settings.embedding_input_type or None
    provider_choice = args.provider or settings.embedding_provider_name
    index_dir = Path(args.index) if Path(args.index).is_absolute() else ROOT / args.index
    eval_path = Path(args.eval) if Path(args.eval).is_absolute() else ROOT / args.eval
    out_dir = Path(args.out) if Path(args.out).is_absolute() else ROOT / args.out

    index = NumPyIndex.load(index_dir)
    questions = json.loads(eval_path.read_text(encoding="utf-8"))
    if args.limit:
        questions = questions[: args.limit]
    if not questions:
        print("Eval set kosong.", file=sys.stderr)
        return 1

    modes = [mode.strip() for mode in args.modes.split(",") if mode.strip()]
    print("Evaluasi retrieval")
    print(f"  Index         : {index.stats()}")
    print(f"  Pertanyaan    : {len(questions)}")
    print(f"  Mode          : {modes}")

    needs_embeddings = any(mode in {"dense", "hybrid"} for mode in modes)
    if needs_embeddings and provider_choice == "none":
        print(
            "--provider none hanya untuk mode bm25; dense/hybrid butuh embedding.",
            file=sys.stderr,
        )
        return 1
    if needs_embeddings:
        if provider_choice == "openrouter":
            embed_key = settings.openrouter_api_key
            embed_base = settings.openrouter_base_url
            embed_referer = settings.openrouter_http_referer or None
            embed_title = settings.openrouter_x_title or None
        elif provider_choice == "hash":
            embed_key = None
            embed_base = None
            embed_referer = None
            embed_title = None
        else:
            embed_key = settings.resolved_embedding_api_key
            embed_base = settings.resolved_embedding_base_url
            embed_referer = None
            embed_title = None

        provider = get_embedding_provider(
            provider_choice,
            api_key=embed_key,
            model=args.model or settings.embedding_model,
            batch_size=args.batch_size,
            input_type=input_type,
            base_url=embed_base,
            http_referer=embed_referer,
            x_title=embed_title,
        )
        if provider.synthetic:
            print(
                "  PERINGATAN    : provider hash bersifat sintetis; "
                "metrik dense/hybrid tidak mencerminkan kualitas produksi.",
                file=sys.stderr,
            )
        print(f"  Embedding     : {provider.name} / {provider.model}")
        query_vectors = provider.embed(
            [question["question"] for question in questions],
            input_type=input_type,
        )
        if query_vectors.shape[0] != len(questions):
            print("Jumlah embedding query tidak sesuai.", file=sys.stderr)
            return 1
        provider_name = provider.name
        provider_model = provider.model
        provider_synthetic = provider.synthetic
    else:
        print("  Embedding     : dilewati (BM25-only)")
        query_vectors = np.zeros((len(questions), index.embeddings.shape[1]), dtype=np.float32)
        provider_name = "none"
        provider_model = "none"
        provider_synthetic = False

    report: dict[str, Any] = {
        "meta": {
            "index_version": index.manifest.get("index_version"),
            "embedding_provider": provider_name,
            "embedding_model": provider_model,
            "embedding_synthetic": provider_synthetic,
            "top_k": args.top_k,
            "as_of": args.as_of,
            "question_count": len(questions),
        },
        "modes": {},
    }

    for mode in modes:
        rows: list[dict[str, Any]] = []
        for question, query_vector in zip(questions, query_vectors, strict=True):
            hits = index.search(
                question["question"],
                query_vector,
                top_k=args.top_k,
                mode=mode,
                status="active",
                audience=None,
                as_of=args.as_of,
            )
            ranked_docs = unique_doc_ranking([hit.chunk["doc_id"] for hit in hits], k=args.top_k)
            relevant = set(question.get("source_doc_ids") or [])
            rows.append(
                {
                    "question": question["question"],
                    "difficulty": question.get("difficulty", "-"),
                    "category": question.get("category", "-"),
                    "relevant": sorted(relevant),
                    "ranked_docs": ranked_docs,
                    "ranked_chunks": [
                        {
                            "chunk_id": hit.chunk["chunk_id"],
                            "doc_id": hit.chunk["doc_id"],
                            "section_path": hit.chunk["section_path"],
                            "dense_score": hit.dense_score,
                            "bm25_score": hit.bm25_score,
                            "rrf_score": hit.rrf_score,
                        }
                        for hit in hits
                    ],
                    "metrics": _question_metrics(relevant, ranked_docs),
                }
            )

        report["modes"][mode] = {
            "overall": _aggregate(rows),
            "by_difficulty": _group(rows, "difficulty"),
            "by_category": _group(rows, "category"),
            "questions": rows,
        }

        print(f"\n[{mode}]")
        print(f"  Recall@5   : {_fmt(report['modes'][mode]['overall']['recall@5'])}")
        print(f"  Hit@5      : {_fmt(report['modes'][mode]['overall']['hit@5'])}")
        print(f"  MRR@10     : {_fmt(report['modes'][mode]['overall']['mrr@10'])}")
        print(f"  nDCG@5     : {_fmt(report['modes'][mode]['overall']['ndcg@5'])}")
        print(f"  Answerable : {report['modes'][mode]['overall']['answerable']}")

    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "retrieval_results.json"
    markdown_path = out_dir / "retrieval_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Evaluasi Retrieval",
        "",
        f"- Index version: `{report['meta']['index_version']}`",
        f"- Embedding: `{provider_model}`" + (" (SINTETIS)" if provider_synthetic else ""),
        f"- Pertanyaan: {len(questions)}",
        f"- Top-k: {args.top_k} | as-of: {args.as_of}",
        "",
        "## Ringkasan",
        "",
        "| Mode | Recall@5 | Hit@5 | Precision@5 | MRR@10 | nDCG@5 | Answerable |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for mode in modes:
        overall = report["modes"][mode]["overall"]
        lines.append(
            f"| {mode} | {_fmt(overall['recall@5'])} | {_fmt(overall['hit@5'])} | "
            f"{_fmt(overall['precision@5'])} | {_fmt(overall['mrr@10'])} | "
            f"{_fmt(overall['ndcg@5'])} | {overall['answerable']} |"
        )

    lines.extend(["", "## Per Difficulty", ""])
    lines.extend(
        [
            "| Mode | Difficulty | Recall@5 | Hit@5 | MRR@10 | nDCG@5 | n |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for mode in modes:
        for difficulty, values in report["modes"][mode]["by_difficulty"].items():
            lines.append(
                f"| {mode} | {difficulty} | {_fmt(values['recall@5'])} | "
                f"{_fmt(values['hit@5'])} | {_fmt(values['mrr@10'])} | "
                f"{_fmt(values['ndcg@5'])} | {values['count']} |"
            )

    lines.extend(
        [
            "",
            "## Catatan",
            "",
            "- Metrik dihitung pada level dokumen (dedupe chunk per doc_id).",
            "- Pertanyaan tanpa `source_doc_ids` tidak dihitung dalam metrik retrieval;",
            "  pertanyaan tersebut dipakai untuk evaluasi refusal di fase generation.",
            "- Jika provider `hash`, angka ini hanya smoke test pipeline.",
        ]
    )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\nLaporan JSON : {_display(json_path)}")
    print(f"Laporan MD   : {_display(markdown_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
