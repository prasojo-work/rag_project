"""Knowledge-base audit: metadata, versions, duplicates, and references."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

from app.rag.frontmatter import split_front_matter
from app.rag.models import AuditIssue, AuditResult, Document

_REFERENCE_RE = re.compile(r"\bKB-(?:POL|FAQ|SOP)-\d{3}\b")
_VERSION_RE = re.compile(r"\d+")


def classify_path(relative_path: str) -> tuple[str, str]:
    """Return ``(status, audience)`` for a document path."""

    if "uji_robustness/konflik" in relative_path:
        return "superseded", "internal"
    if "uji_robustness/noise" in relative_path:
        return "noise", "internal"
    if relative_path.startswith("dokumen/sop/") or relative_path.startswith("sop/"):
        return "active", "internal"
    return "active", "public"


def version_tuple(version: str | None) -> tuple[int, ...]:
    if not version:
        return ()
    return tuple(int(part) for part in _VERSION_RE.findall(str(version))[:4])


def _as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def load_documents(root: Path) -> tuple[list[Document], list[AuditIssue]]:
    """Load all Markdown documents under ``root``.

    Invalid documents are returned as audit errors and skipped from the list so
    the index builder never silently indexes incomplete metadata.
    """

    root = root.resolve()
    documents: list[Document] = []
    issues: list[AuditIssue] = []

    for path in sorted(root.rglob("*.md")):
        relative = path.relative_to(root).as_posix()
        status, inferred_audience = classify_path(relative)
        raw = path.read_text(encoding="utf-8")
        front_matter, body, front_matter_error = split_front_matter(raw)

        if front_matter_error:
            severity = "error" if status == "active" else "warning"
            issues.append(
                AuditIssue(
                    severity=severity,
                    code="front_matter",
                    message=front_matter_error,
                    source_path=relative,
                )
            )

        doc_id = _as_optional_str(front_matter.get("doc_id"))
        title = _as_optional_str(front_matter.get("title"))
        category = _as_optional_str(front_matter.get("category"))

        missing = [
            field
            for field, value in (
                ("doc_id", doc_id),
                ("title", title),
                ("category", category),
            )
            if not value
        ]
        if missing:
            issues.append(
                AuditIssue(
                    severity="error",
                    code="missing_required_metadata",
                    message=f"Field wajib tidak ada/kosong: {', '.join(missing)}",
                    source_path=relative,
                    doc_id=doc_id,
                )
            )
            continue

        last_updated = _as_optional_str(front_matter.get("last_updated"))
        effective_date = _as_optional_str(front_matter.get("effective_date"))
        if effective_date:
            effective_date_source = "explicit"
        elif last_updated:
            effective_date = last_updated
            effective_date_source = "last_updated"
        else:
            effective_date_source = "missing"

        if not effective_date and status == "active":
            issues.append(
                AuditIssue(
                    severity="error",
                    code="missing_effective_date",
                    message="Dokumen aktif tidak punya effective_date maupun last_updated",
                    source_path=relative,
                    doc_id=doc_id,
                )
            )

        for date_field, date_value in (
            ("effective_date", effective_date),
            ("last_updated", last_updated),
        ):
            if not date_value:
                continue
            try:
                date.fromisoformat(date_value)
            except ValueError:
                issues.append(
                    AuditIssue(
                        severity="error" if status == "active" else "warning",
                        code="invalid_date",
                        message=f"{date_field} bukan tanggal ISO (YYYY-MM-DD): {date_value}",
                        source_path=relative,
                        doc_id=doc_id,
                    )
                )

        version = _as_optional_str(front_matter.get("version"))
        if not version and status == "active":
            issues.append(
                AuditIssue(
                    severity="warning",
                    code="missing_version",
                    message="Dokumen aktif tidak punya field version; dianggap versi tunggal",
                    source_path=relative,
                    doc_id=doc_id,
                )
            )

        if not body.strip():
            issues.append(
                AuditIssue(
                    severity="warning",
                    code="empty_body",
                    message="Body dokumen kosong",
                    source_path=relative,
                    doc_id=doc_id,
                )
            )

        audience = _as_optional_str(front_matter.get("audience")) or inferred_audience
        document = Document(
            doc_id=doc_id,
            title=title,
            category=category,
            subcategory=_as_optional_str(front_matter.get("subcategory")),
            version=version,
            last_updated=last_updated,
            effective_date=effective_date,
            owner=_as_optional_str(front_matter.get("owner")),
            status=status,
            audience=audience,
            source_path=relative,
            body=body,
            front_matter=front_matter,
            doc_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            effective_date_source=effective_date_source,
        )
        documents.append(document)

    _check_duplicates(documents, issues)
    _check_versions(documents, issues)
    _check_references(documents, issues)

    return documents, issues


def _check_duplicates(documents: list[Document], issues: list[AuditIssue]) -> None:
    active: dict[str, list[Document]] = defaultdict(list)
    for document in documents:
        if document.status == "active":
            active[document.doc_id].append(document)

    for doc_id, group in active.items():
        if len(group) > 1:
            paths = ", ".join(document.source_path for document in group)
            for document in group:
                issues.append(
                    AuditIssue(
                        severity="error",
                        code="duplicate_active_doc_id",
                        message=f"doc_id {doc_id} muncul lebih dari sekali di index aktif: {paths}",
                        source_path=document.source_path,
                        doc_id=doc_id,
                    )
                )


def _check_versions(documents: list[Document], issues: list[AuditIssue]) -> None:
    by_doc_id: dict[str, list[Document]] = defaultdict(list)
    for document in documents:
        by_doc_id[document.doc_id].append(document)

    for doc_id, group in by_doc_id.items():
        active_versions = [
            version_tuple(document.version) for document in group if document.status == "active"
        ]
        superseded_versions = [
            version_tuple(document.version) for document in group if document.status == "superseded"
        ]
        if not active_versions or not superseded_versions:
            continue

        active_version = max(active_versions)
        superseded_version = max(superseded_versions)
        if active_version and superseded_version and active_version < superseded_version:
            issues.append(
                AuditIssue(
                    severity="error",
                    code="active_version_older",
                    message=(
                        f"Versi aktif {active_version} lebih lama dari versi superseded "
                        f"{superseded_version}"
                    ),
                    doc_id=doc_id,
                )
            )


def _check_references(documents: list[Document], issues: list[AuditIssue]) -> None:
    known_ids = {document.doc_id for document in documents}
    for document in documents:
        references = set(_REFERENCE_RE.findall(document.body))
        for reference in sorted(references - known_ids):
            issues.append(
                AuditIssue(
                    severity="warning",
                    code="unknown_reference",
                    message=f"Referensi {reference} tidak ditemukan di knowledge base",
                    source_path=document.source_path,
                    doc_id=document.doc_id,
                )
            )


def audit_documents(root: Path) -> AuditResult:
    documents, issues = load_documents(root)
    active_documents = [document for document in documents if document.status == "active"]
    stats = {
        "total_documents": len(documents),
        "by_status": dict(Counter(document.status for document in documents)),
        "by_category": dict(Counter(document.category for document in documents)),
        "active_documents": len(active_documents),
        "active_by_category": dict(Counter(document.category for document in active_documents)),
        "error_count": sum(1 for issue in issues if issue.severity == "error"),
        "warning_count": sum(1 for issue in issues if issue.severity == "warning"),
    }
    return AuditResult(documents=documents, issues=issues, stats=stats)


def write_audit_report(result: AuditResult, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "report.json"
    markdown_path = out_dir / "report.md"

    payload = {
        "stats": result.stats,
        "documents": [document.summary() for document in result.documents],
        "issues": [asdict(issue) for issue in result.issues],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    active = [document for document in result.documents if document.status == "active"]
    lines = [
        "# Audit Knowledge Base",
        "",
        "Dihasilkan otomatis oleh `scripts/audit_data.py`.",
        "",
        "## Ringkasan",
        "",
        f"- Total dokumen: **{result.stats['total_documents']}**",
        f"- Dokumen aktif: **{result.stats['active_documents']}**",
        f"- Error: **{result.stats['error_count']}**",
        f"- Warning: **{result.stats['warning_count']}**",
        f"- Status: `{result.stats['by_status']}`",
        f"- Kategori aktif: `{result.stats['active_by_category']}`",
        f"- Kategori semua: `{result.stats['by_category']}`",
        "",
        "## Dokumen Aktif",
        "",
        "| doc_id | Versi | Berlaku | Kategori | Judul |",
        "|---|---|---|---|---|",
    ]
    for document in sorted(active, key=lambda item: (item.category, item.doc_id)):
        lines.append(
            f"| {document.doc_id} | {document.version or '-'} | "
            f"{document.effective_date or '-'} | {document.category} | {document.title} |"
        )

    lines.extend(["", "## Issues", ""])
    if not result.issues:
        lines.append("Tidak ada issue.")
    else:
        lines.append("| Severity | Code | doc_id | Pesan |")
        lines.append("|---|---|---|---|")
        for issue in sorted(result.issues, key=lambda item: (item.severity, item.code)):
            lines.append(
                f"| {issue.severity} | {issue.code} | {issue.doc_id or '-'} | "
                f"{issue.message.replace('|', '/')} |"
            )

    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path
