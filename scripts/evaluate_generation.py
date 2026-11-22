"""Evaluate generation quality on the 50-question golden set.

Two layers:
1. Deterministic checks for all questions (citations, refusal, leakage, latency).
2. LLM-as-judge on a stratified subset (default 20 questions).

Results are cached so reruns do not spend API quota again.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from app.core.config import Settings, is_secret_set  # noqa: E402
from app.rag.embeddings import get_embedding_provider  # noqa: E402
from app.rag.index import NumPyIndex  # noqa: E402
from app.rag.judge import JudgeError, judge_answer, judge_to_dict  # noqa: E402
from app.rag.llm import ChatClient  # noqa: E402
from app.schemas.chat import ChatRequest  # noqa: E402
from app.services.chat import ChatService  # noqa: E402

_LEAK_RE = re.compile(
    r"(\[?KB-(?:POL|FAQ|SOP)-\d{3}\]?|\bSOP\b|system\s*prompt|"
    r"instruksi\s+internal|handover\s+shift)",
    re.IGNORECASE,
)


def _display(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _mean(values: list[float | int | None]) -> float | None:
    usable = [float(value) for value in values if value is not None]
    return sum(usable) / len(usable) if usable else None


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(0.95 * (len(ordered) - 1)))
    return ordered[index]


def _fmt(value: float | None, digits: int = 3) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def _qid(question: str) -> str:
    return hashlib.sha1(question.encode("utf-8")).hexdigest()[:12]


def _safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value or "unknown")


def _build_service(settings: Settings) -> ChatService:
    index = NumPyIndex.load(settings.resolved_index_dir)
    if not settings.resolved_embedding_api_key:
        raise RuntimeError(
            f"API key embedding untuk provider {settings.embedding_provider_name!r} belum di-set"
        )
    if settings.embedding_provider_name == "openrouter":
        embed_referer = settings.openrouter_http_referer or None
        embed_title = settings.openrouter_x_title or None
    else:
        embed_referer = None
        embed_title = None
    embedder = get_embedding_provider(
        settings.embedding_provider_name,
        api_key=settings.resolved_embedding_api_key,
        model=settings.embedding_model,
        batch_size=settings.embedding_batch_size,
        input_type=settings.embedding_input_type or None,
        base_url=settings.resolved_embedding_base_url,
        http_referer=embed_referer,
        x_title=embed_title,
    )

    provider = settings.chat_provider
    if (
        provider == "deepseek"
        and not is_secret_set(settings.deepseek_api_key)
        and settings.openrouter_api_key
    ):
        provider = "openrouter"
    if provider == "deepseek":
        chat_key = settings.deepseek_api_key
        chat_base = settings.deepseek_base_url
        chat_models = settings.chat_models
        referer = None
        title = None
    elif provider == "openrouter":
        chat_key = settings.openrouter_api_key
        chat_base = settings.openrouter_base_url
        chat_models = settings.model_candidates
        referer = settings.openrouter_http_referer or None
        title = settings.openrouter_x_title or None
    else:
        chat_key = settings.llm_api_key
        chat_base = settings.llm_base_url
        chat_models = settings.model_candidates
        referer = None
        title = None
    if not is_secret_set(chat_key):
        raise RuntimeError(f"API key chat untuk provider {provider!r} kosong")

    llm = ChatClient(
        chat_key,
        chat_models,
        provider=provider,
        base_url=chat_base,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        reasoning_effort=settings.llm_reasoning_effort or None,
        thinking_disabled=settings.deepseek_thinking_disabled,
        timeout=settings.request_timeout,
        http_referer=referer,
        x_title=title,
    )
    return ChatService(settings, index, embedder, llm)


def _build_judge(settings: Settings, judge_model: str | None) -> ChatClient:
    model = judge_model or settings.judge_model
    if is_secret_set(settings.deepseek_api_key):
        models = [model, *settings.judge_models]
        if model not in models:
            models.insert(0, model)
        return ChatClient(
            settings.deepseek_api_key,
            list(dict.fromkeys(models)),
            provider="deepseek",
            base_url=settings.deepseek_base_url,
            temperature=0.0,
            max_tokens=700,
            thinking_disabled=True,
            timeout=settings.request_timeout,
        )
    if is_secret_set(settings.openrouter_api_key):
        return ChatClient(
            settings.openrouter_api_key,
            [model, settings.llm_model],
            provider="openrouter",
            base_url=settings.openrouter_base_url,
            temperature=0.0,
            max_tokens=700,
            timeout=settings.request_timeout,
        )
    raise RuntimeError("Tidak ada API key untuk judge")


def _context_from_response(
    response: dict[str, Any],
    chunk_by_id: dict[str, dict[str, Any]],
    max_chars: int,
) -> str:
    blocks: list[str] = []
    used = 0
    for source in response.get("sources", []):
        chunk = chunk_by_id.get(source.get("chunk_id"))
        if not chunk:
            continue
        block = "\n".join(
            [
                f"[{chunk['doc_id']}] {chunk['title']} — {chunk['section_path']}",
                chunk.get("text", ""),
            ]
        )
        if used + len(block) > max_chars and blocks:
            break
        blocks.append(block)
        used += len(block)
    return "\n\n".join(blocks)


def _metrics(
    response: dict[str, Any],
    expected_docs: set[str],
    expected_refusal: bool,
) -> dict[str, Any]:
    sources = response.get("sources", [])
    citations = response.get("citations", [])
    retrieval_docs = list(dict.fromkeys(source["doc_id"] for source in sources))
    cited_docs = list(dict.fromkeys(citation["doc_id"] for citation in citations))
    customer_reply = response.get("customer_reply") or ""
    leak = bool(_LEAK_RE.search(customer_reply))
    internal_sources = [source for source in sources if source.get("audience") == "internal"]
    source_overlap = set(retrieval_docs) & expected_docs
    citation_overlap = set(cited_docs) & expected_docs
    return {
        "answered": bool(response.get("answerable")),
        "refused": not bool(response.get("answerable")),
        "expected_refusal": expected_refusal,
        "refusal_correct": (
            (not bool(response.get("answerable")))
            if expected_refusal
            else bool(response.get("answerable"))
        ),
        "citation_valid": bool(response.get("citation_valid")),
        "citation_count": len(citations),
        "source_count": len(sources),
        "source_hit": bool(source_overlap) if expected_docs else None,
        "source_coverage": (len(source_overlap) / len(expected_docs) if expected_docs else None),
        "citation_hit": bool(citation_overlap) if expected_docs else None,
        "citation_coverage": (
            len(citation_overlap) / len(expected_docs) if expected_docs else None
        ),
        "retrieval_docs": retrieval_docs,
        "cited_docs": cited_docs,
        "internal_source_count": len(internal_sources),
        "leak": leak,
        "latency_ms": response.get("latency_ms"),
        "confidence": response.get("confidence"),
        "customer_reply_length": len(customer_reply),
        "internal_notes_length": len(response.get("internal_notes") or ""),
        "needs_escalation": bool(response.get("needs_escalation")),
        "retrieval_mode": (response.get("debug") or {}).get("retrieval_mode"),
    }


def _select_judge(results: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if limit <= 0 or limit >= len(results):
        return results

    selected: list[dict[str, Any]] = []
    selected_ids: set[int] = set()

    def add(candidates: list[dict[str, Any]], take: int) -> None:
        for result in sorted(candidates, key=lambda item: item["index"]):
            if len(selected) >= limit:
                return
            if take <= 0:
                return
            if result["index"] in selected_ids:
                continue
            selected.append(result)
            selected_ids.add(result["index"])
            take -= 1

    add([result for result in results if result["expected_refusal"]], 2)

    groups = {
        "hard": [result for result in results if result["difficulty"] == "hard"],
        "medium": [result for result in results if result["difficulty"] == "medium"],
        "easy": [result for result in results if result["difficulty"] == "easy"],
    }
    remaining = max(0, limit - len(selected))
    shares = {"hard": 0.5, "medium": 0.3, "easy": 0.2}
    for key in ("hard", "medium", "easy"):
        add(groups[key], int(round(remaining * shares[key])))

    # Fill any remaining slots with questions not selected yet.
    add(results, limit - len(selected))
    return selected[:limit]


def _summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    answerable = [result for result in results if not result["expected_refusal"]]
    refusal = [result for result in results if result["expected_refusal"]]
    answered = [result for result in results if result["metrics"]["answered"]]
    judged = [result for result in results if result.get("judge")]
    latencies = [
        float(result["metrics"]["latency_ms"])
        for result in results
        if result["metrics"].get("latency_ms") is not None
    ]
    prompt_tokens = sum(
        int((result.get("response", {}).get("usage") or {}).get("prompt_tokens") or 0)
        for result in results
    )
    completion_tokens = sum(
        int((result.get("response", {}).get("usage") or {}).get("completion_tokens") or 0)
        for result in results
    )
    retrieval_modes: dict[str, int] = {}
    for result in results:
        mode = result["metrics"].get("retrieval_mode") or "unknown"
        retrieval_modes[mode] = retrieval_modes.get(mode, 0) + 1

    return {
        "count": len(results),
        "retrieval_mode_counts": retrieval_modes,
        "answerable_questions": len(answerable),
        "expected_refusal_questions": len(refusal),
        "answered": len(answered),
        "answer_rate": len(answered) / len(answerable) if answerable else None,
        "refusal_accuracy": (
            sum(1 for result in refusal if result["metrics"]["refused"]) / len(refusal)
            if refusal
            else None
        ),
        "citation_validity": _mean([result["metrics"]["citation_valid"] for result in answered]),
        "source_hit_rate": _mean([result["metrics"]["source_hit"] for result in answerable]),
        "citation_hit_rate": _mean([result["metrics"]["citation_hit"] for result in answered]),
        "leak_count": sum(1 for result in results if result["metrics"]["leak"]),
        "internal_source_count": sum(
            result["metrics"]["internal_source_count"] for result in results
        ),
        "latency_p50_ms": statistics.median(latencies) if latencies else None,
        "latency_p95_ms": _p95(latencies),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "judge_count": len(judged),
        "judge_correctness": _mean([r["judge"]["correctness"] for r in judged]),
        "judge_completeness": _mean([r["judge"]["completeness"] for r in judged]),
        "judge_faithfulness": _mean([r["judge"]["faithfulness"] for r in judged]),
        "judge_citation_support": _mean([r["judge"]["citation_support"] for r in judged]),
        "judge_escalation": _mean([r["judge"]["escalation"] for r in judged]),
        "hallucination_count": sum(1 for result in judged if result["judge"].get("hallucination")),
    }


def _group_summary(results: list[dict[str, Any]], field: str) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        grouped.setdefault(str(result.get(field, "-")), []).append(result)
    return {key: _summary(value) for key, value in sorted(grouped.items())}


def _improvement_notes(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = []
    for result in results:
        judge = result.get("judge")
        if not judge:
            continue
        if judge.get("correctness", 5) >= 5 and judge.get("completeness", 5) >= 5:
            continue
        notes.append(
            {
                "question": result["question"],
                "category": result["category"],
                "correctness": judge.get("correctness"),
                "completeness": judge.get("completeness"),
                "notes": judge.get("notes", ""),
            }
        )
    notes.sort(key=lambda item: (item["correctness"], item["completeness"]))
    return notes[:6]


def _failure_cases(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for result in results:
        reasons: list[str] = []
        metrics = result["metrics"]
        if result["expected_refusal"] and metrics["answered"]:
            reasons.append("seharusnya refusal tetapi dijawab")
        if not result["expected_refusal"] and metrics["refused"]:
            reasons.append("tidak menjawab padahal answerable")
        if metrics["leak"]:
            reasons.append("customer_reply mengandung penanda internal")
        if metrics["answered"] and not metrics["citation_valid"]:
            reasons.append("sitasi tidak valid")
        judge = result.get("judge")
        if judge and judge.get("hallucination"):
            reasons.append("judge menandai hallucination")
        if judge and judge.get("correctness", 5) <= 3:
            reasons.append(f"correctness rendah ({judge['correctness']}/5)")
        if reasons:
            failures.append(
                {
                    "question": result["question"],
                    "difficulty": result["difficulty"],
                    "category": result["category"],
                    "reasons": reasons,
                    "customer_reply": (result["response"].get("customer_reply") or "")[:500],
                    "judge_notes": (judge or {}).get("notes", ""),
                    "judge_correctness": (judge or {}).get("correctness"),
                }
            )
    return failures[:12]


def _conflict_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    conflicts = [
        result
        for result in results
        if "versi" in result["question"].lower() or "konflik" in (result.get("notes") or "").lower()
    ]
    return {
        "count": len(conflicts),
        "citation_hit_rate": _mean([result["metrics"]["citation_hit"] for result in conflicts]),
        "judge_correctness": _mean(
            [result["judge"]["correctness"] for result in conflicts if result.get("judge")]
        ),
        "items": conflicts,
    }


def _write_report(
    *,
    path: Path,
    meta: dict[str, Any],
    summary: dict[str, Any],
    by_difficulty: dict[str, Any],
    by_category: dict[str, Any],
    conflict: dict[str, Any],
    failures: list[dict[str, Any]],
    improvements: list[dict[str, Any]],
) -> None:
    lines = [
        "# Evaluasi Generation",
        "",
        f"- Mode: `{meta['mode']}`",
        f"- Index: `{meta['index_version']}`",
        f"- Generator: `{meta['chat_provider']}` / `{meta['chat_model']}`",
        f"- Judge: `{meta['judge_model']}` (n={summary['judge_count']}, "
        f"error={summary.get('judge_errors', 0)})",
        f"- Pertanyaan: {summary['count']}",
        f"- Error: {meta.get('error_count', 0)}",
        f"- Tanggal: {meta['as_of']}",
        f"- Retrieval mode: `{summary.get('retrieval_mode_counts', {})}`",
        "",
        "## Ringkasan",
        "",
        "| Metrik | Nilai |",
        "|---|---:|",
        f"| Answer rate (answerable) | {_fmt(summary['answer_rate'])} |",
        f"| Refusal accuracy (expected refusal) | {_fmt(summary['refusal_accuracy'])} |",
        f"| Citation validity (answered) | {_fmt(summary['citation_validity'])} |",
        f"| Source hit rate | {_fmt(summary['source_hit_rate'])} |",
        f"| Citation hit rate | {_fmt(summary['citation_hit_rate'])} |",
        f"| Internal leak | {summary['leak_count']} |",
        (
            "| Internal sources (public mode harus 0) | "
            if meta["mode"] == "public"
            else "| Internal sources (agent mode, wajar) | "
        )
        + f"{summary['internal_source_count']} |",
        f"| Latency p50 (ms) | {_fmt(summary['latency_p50_ms'], 0)} |",
        f"| Latency p95 (ms) | {_fmt(summary['latency_p95_ms'], 0)} |",
        f"| Token prompt / completion | {summary['prompt_tokens']} / "
        f"{summary['completion_tokens']} |",
        "",
        "### LLM Judge (1–5)",
        "",
        "| Dimensi | Rata-rata |",
        "|---|---:|",
        f"| Correctness | {_fmt(summary['judge_correctness'], 2)} |",
        f"| Completeness | {_fmt(summary['judge_completeness'], 2)} |",
        f"| Faithfulness | {_fmt(summary['judge_faithfulness'], 2)} |",
        f"| Citation support | {_fmt(summary['judge_citation_support'], 2)} |",
        f"| Escalation | {_fmt(summary['judge_escalation'], 2)} |",
        f"| Hallucination | {summary['hallucination_count']} / {summary['judge_count']} |",
        "",
        "## Per Difficulty",
        "",
        "| Difficulty | n | Answer rate | Refusal acc | Citation valid | "
        "Source hit | Judge correctness |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for key, value in by_difficulty.items():
        lines.append(
            f"| {key} | {value['count']} | {_fmt(value['answer_rate'])} | "
            f"{_fmt(value['refusal_accuracy'])} | {_fmt(value['citation_validity'])} | "
            f"{_fmt(value['source_hit_rate'])} | {_fmt(value['judge_correctness'], 2)} |"
        )

    lines.extend(
        [
            "",
            "## Per Kategori",
            "",
            "| Kategori | n | Answer rate | Refusal acc | Citation valid | Judge correctness |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for key, value in by_category.items():
        lines.append(
            f"| {key} | {value['count']} | {_fmt(value['answer_rate'])} | "
            f"{_fmt(value['refusal_accuracy'])} | {_fmt(value['citation_validity'])} | "
            f"{_fmt(value['judge_correctness'], 2)} |"
        )

    lines.extend(
        [
            "",
            "## Konflik Versi",
            "",
            f"- Pertanyaan terdeteksi: {conflict['count']}",
            f"- Citation hit rate: {_fmt(conflict['citation_hit_rate'])}",
            f"- Judge correctness: {_fmt(conflict['judge_correctness'], 2)}",
            "",
            "## Failure Cases",
            "",
        ]
    )
    if not failures:
        lines.append("Tidak ada failure case pada kriteria yang diperiksa.")
    else:
        for item in failures:
            lines.extend(
                [
                    f"### {item['question']}",
                    "",
                    f"- Difficulty/category: `{item['difficulty']}` / `{item['category']}`",
                    f"- Alasan: {', '.join(item['reasons'])}",
                    f"- Judge correctness: {item['judge_correctness']}",
                    f"- Catatan judge: {item['judge_notes'] or '-'}",
                    "",
                    "```text",
                    item["customer_reply"],
                    "```",
                    "",
                ]
            )

    lines.extend(["", "## Catatan Peningkatan dari Judge", ""])
    if not improvements:
        lines.append("Tidak ada catatan peningkatan pada subset judge.")
    else:
        for item in improvements:
            lines.extend(
                [
                    f"- **{item['question']}**",
                    f"  - kategori: `{item['category']}` · correctness {item['correctness']}/5 · "
                    f"completeness {item['completeness']}/5",
                    f"  - {item['notes'] or '-'}",
                ]
            )

    lines.extend(
        [
            "",
            "## Catatan Metodologi",
            "",
            "- Metrik deterministik dihitung untuk semua pertanyaan.",
            "- LLM judge dijalankan pada subset stratifikasi (unanswerable + hard lebih dulu).",
            "- Generator dan judge sama-sama memakai DeepSeek; ini self-judge bias yang perlu",
            "  disadari. Untuk klaim lebih kuat, validasi manual subset atau pakai model judge",
            "  dari provider berbeda.",
            "- Mode `agent` dipakai untuk mengukur kualitas KB penuh. Untuk UI pelanggan",
            "  (mode `public`), jalankan subset safety terpisah.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval", default="hasil_evaluasi/eval_set.json")
    parser.add_argument("--out", default="data/eval")
    parser.add_argument("--mode", choices=["agent", "public"], default="agent")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--only-categories",
        default=None,
        help="Filter kategori, mis. sop atau refund,pembatalan",
    )
    parser.add_argument("--judge-limit", type=int, default=20)
    parser.add_argument("--judge-model", default=None)
    parser.add_argument("--no-judge", action="store_true")
    parser.add_argument("--refresh", action="store_true", help="Abaikan cache")
    parser.add_argument("--max-context-chars", type=int, default=8000)
    parser.add_argument(
        "--only-public-ground-truth",
        action="store_true",
        help="Hanya pertanyaan yang seluruh source_doc_ids-nya public",
    )
    parser.add_argument("--tag", default=None, help="Suffix nama output")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    settings = Settings()
    eval_path = Path(args.eval) if Path(args.eval).is_absolute() else ROOT / args.eval
    out_dir = Path(args.out) if Path(args.out).is_absolute() else ROOT / args.out
    questions = json.loads(eval_path.read_text(encoding="utf-8"))
    if args.only_categories:
        categories = {item.strip() for item in args.only_categories.split(",") if item.strip()}
        questions = [question for question in questions if question.get("category") in categories]
    if args.limit:
        questions = questions[: args.limit]
    if not questions:
        print("Tidak ada pertanyaan setelah filter.", file=sys.stderr)
        return 1

    service = _build_service(settings)
    index = service.index
    chunk_by_id = {chunk["chunk_id"]: chunk for chunk in index.chunks}
    audience_by_doc = {
        document["doc_id"]: document.get("audience", "public")
        for document in index.manifest.get("documents", [])
    }
    if args.only_public_ground_truth:
        questions = [
            question
            for question in questions
            if question.get("source_doc_ids")
            and all(
                audience_by_doc.get(doc_id) == "public" for doc_id in question["source_doc_ids"]
            )
        ]
    if not questions:
        print("Tidak ada pertanyaan setelah filter audience.", file=sys.stderr)
        return 1
    index_version = _safe(str(index.manifest.get("index_version") or "unknown"))
    generator_key = _safe(
        f"{settings.chat_provider}-{settings.chat_models[0]}-{settings.prompt_version}"
    )
    cache_root = out_dir / "cache" / "generation" / args.mode / index_version / generator_key
    cache_root.mkdir(parents=True, exist_ok=True)

    judge_client = (
        None if args.no_judge or args.judge_limit == 0 else _build_judge(settings, args.judge_model)
    )
    judge_model = (args.judge_model or settings.judge_model) if judge_client else "none"
    judge_cache_root = out_dir / "cache" / "judge" / _safe(judge_model)
    judge_cache_root.mkdir(parents=True, exist_ok=True)

    print("Evaluasi generation")
    print(f"  Mode          : {args.mode}")
    print(f"  Pertanyaan    : {len(questions)}")
    print(f"  Generator     : {settings.chat_provider} / {settings.chat_models[0]}")
    print(f"  Judge         : {judge_model} (limit {args.judge_limit})")
    print(f"  Index         : {index_version}")
    print()

    results: list[dict[str, Any]] = []
    for number, question in enumerate(questions, start=1):
        qid = _qid(question["question"])
        cache_path = cache_root / f"{qid}.json"
        response: dict[str, Any] | None = None
        if cache_path.exists() and not args.refresh:
            try:
                response = json.loads(cache_path.read_text(encoding="utf-8"))["response"]
            except (OSError, json.JSONDecodeError, KeyError):
                response = None

        if response is None:
            try:
                response = service.answer(
                    ChatRequest(
                        message=question["question"],
                        mode=args.mode,
                        debug=True,
                    )
                ).model_dump()
                cache_path.write_text(
                    json.dumps({"question": question["question"], "response": response}),
                    encoding="utf-8",
                )
            except Exception as exc:
                print(f"  [{number:02d}] ERROR {qid}: {exc}", file=sys.stderr)
                results.append(
                    {
                        "index": number,
                        "question": question["question"],
                        "ground_truth": question.get("ground_truth_answer", ""),
                        "difficulty": question.get("difficulty", "-"),
                        "category": question.get("category", "-"),
                        "notes": question.get("notes", ""),
                        "source_doc_ids": question.get("source_doc_ids") or [],
                        "expected_refusal": not bool(question.get("source_doc_ids")),
                        "response": {},
                        "metrics": {},
                        "judge": None,
                        "error": str(exc),
                    }
                )
                continue

        expected_docs = set(question.get("source_doc_ids") or [])
        expected_refusal = not expected_docs
        metrics = _metrics(response, expected_docs, expected_refusal)
        results.append(
            {
                "index": number,
                "question": question["question"],
                "ground_truth": question.get("ground_truth_answer", ""),
                "difficulty": question.get("difficulty", "-"),
                "category": question.get("category", "-"),
                "notes": question.get("notes", ""),
                "source_doc_ids": sorted(expected_docs),
                "expected_refusal": expected_refusal,
                "response": response,
                "metrics": metrics,
                "judge": None,
                "error": None,
            }
        )
        print(
            f"  [{number:02d}/{len(questions)}] answered={metrics['answered']} "
            f"cit_valid={metrics['citation_valid']} "
            f"mode={metrics['retrieval_mode']} "
            f"latency={metrics['latency_ms']}ms"
        )

    judge_errors = 0
    if judge_client:
        selected = _select_judge(results, args.judge_limit)
        print(f"\nLLM judge untuk {len(selected)} pertanyaan")
        for number, result in enumerate(selected, start=1):
            if result.get("error") or not result.get("response"):
                continue
            qid = _qid(result["question"])
            cache_path = judge_cache_root / f"{qid}.json"
            judge_data = None
            if cache_path.exists() and not args.refresh:
                try:
                    judge_data = json.loads(cache_path.read_text(encoding="utf-8"))["judge"]
                except (OSError, json.JSONDecodeError, KeyError):
                    judge_data = None
            if judge_data is None:
                context = _context_from_response(
                    result["response"],
                    chunk_by_id,
                    args.max_context_chars,
                )
                try:
                    judged, _ = judge_answer(
                        judge_client,
                        question=result["question"],
                        ground_truth=result["ground_truth"],
                        context=context,
                        customer_reply=result["response"].get("customer_reply", ""),
                        internal_notes=result["response"].get("internal_notes", ""),
                        expected_refusal=result["expected_refusal"],
                    )
                    judge_data = judge_to_dict(judged)
                    cache_path.write_text(json.dumps({"judge": judge_data}), encoding="utf-8")
                except JudgeError as exc:
                    judge_errors += 1
                    print(f"  judge ERROR {qid}: {exc}", file=sys.stderr)
                    continue
            result["judge"] = judge_data
            print(
                f"  [{number:02d}/{len(selected)}] correctness="
                f"{judge_data.get('correctness')} hallucination="
                f"{judge_data.get('hallucination')}"
            )

    valid_results = [result for result in results if not result.get("error")]
    error_results = [result for result in results if result.get("error")]
    summary = _summary(valid_results)
    summary["judge_errors"] = judge_errors
    by_difficulty = _group_summary(valid_results, "difficulty")
    by_category = _group_summary(valid_results, "category")
    conflict = _conflict_summary(valid_results)
    failures = _failure_cases(valid_results)
    improvements = _improvement_notes(valid_results)
    for error in error_results:
        failures.insert(
            0,
            {
                "question": error["question"],
                "difficulty": error["difficulty"],
                "category": error["category"],
                "reasons": [f"error: {error['error']}"],
                "customer_reply": "",
                "judge_notes": "",
                "judge_correctness": None,
            },
        )

    meta = {
        "mode": args.mode,
        "as_of": date.today().isoformat(),
        "index_version": index_version,
        "chat_provider": settings.chat_provider,
        "chat_model": settings.chat_models[0],
        "judge_model": judge_model,
        "judge_limit": args.judge_limit,
        "question_count": len(questions),
        "error_count": len(error_results),
        "eval_file": _display(eval_path),
        "tag": args.tag or "",
        "public_ground_truth_only": args.only_public_ground_truth,
    }
    payload = {
        "meta": meta,
        "summary": summary,
        "by_difficulty": by_difficulty,
        "by_category": by_category,
        "conflict": {
            "count": conflict["count"],
            "citation_hit_rate": conflict["citation_hit_rate"],
            "judge_correctness": conflict["judge_correctness"],
        },
        "failures": failures,
        "results": results,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"generation_{args.mode}"
    if args.tag:
        stem += f"_{_safe(args.tag)}"
    json_path = out_dir / f"{stem}.json"
    markdown_path = out_dir / f"{stem}_report.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_report(
        path=markdown_path,
        meta=meta,
        summary=summary,
        by_difficulty=by_difficulty,
        by_category=by_category,
        conflict=conflict,
        failures=failures,
        improvements=improvements,
    )

    print("\nRingkasan")
    print(f"  Error             : {len(error_results)}")
    print(f"  Answer rate       : {_fmt(summary['answer_rate'])}")
    print(f"  Refusal accuracy  : {_fmt(summary['refusal_accuracy'])}")
    print(f"  Citation validity : {_fmt(summary['citation_validity'])}")
    print(f"  Leak              : {summary['leak_count']}")
    print(f"  Judge correctness : {_fmt(summary['judge_correctness'], 2)}")
    print(f"  Hallucination     : {summary['hallucination_count']}/{summary['judge_count']}")
    print(
        "  Latency p50/p95   : "
        f"{_fmt(summary['latency_p50_ms'], 0)} / "
        f"{_fmt(summary['latency_p95_ms'], 0)} ms"
    )
    print(f"\nLaporan JSON : {_display(json_path)}")
    print(f"Laporan MD   : {_display(markdown_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
