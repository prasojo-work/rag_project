"""Data models for documents, chunks, and audit results."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Document:
    doc_id: str
    title: str
    category: str
    subcategory: str | None
    version: str | None
    last_updated: str | None
    effective_date: str | None
    owner: str | None
    status: str
    audience: str
    source_path: str
    body: str
    front_matter: dict[str, Any]
    doc_hash: str
    effective_date_source: str

    def summary(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "title": self.title,
            "category": self.category,
            "subcategory": self.subcategory,
            "version": self.version,
            "last_updated": self.last_updated,
            "effective_date": self.effective_date,
            "effective_date_source": self.effective_date_source,
            "owner": self.owner,
            "status": self.status,
            "audience": self.audience,
            "source_path": self.source_path,
            "doc_hash": self.doc_hash,
        }


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    title: str
    category: str
    subcategory: str | None
    version: str | None
    effective_date: str | None
    last_updated: str | None
    status: str
    audience: str
    section_path: str
    chunk_type: str
    text: str
    embedding_text: str
    token_estimate: int
    source_path: str
    doc_hash: str
    chunk_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AuditIssue:
    severity: str
    code: str
    message: str
    source_path: str | None = None
    doc_id: str | None = None


@dataclass
class AuditResult:
    documents: list[Document]
    issues: list[AuditIssue]
    stats: dict[str, Any] = field(default_factory=dict)

    @property
    def errors(self) -> list[AuditIssue]:
        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def warnings(self) -> list[AuditIssue]:
        return [issue for issue in self.issues if issue.severity == "warning"]

    def has_errors(self) -> bool:
        return bool(self.errors)
