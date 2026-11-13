from __future__ import annotations

from pathlib import Path

from app.rag.audit import audit_documents, classify_path


def write_doc(root: Path, relative: str, front_matter: str, body: str = "# Judul\n\nIsi.") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{front_matter.strip()}\n---\n\n{body}\n", encoding="utf-8")


def test_classify_path() -> None:
    assert classify_path("sop/KB-SOP-001.md") == ("active", "internal")
    assert classify_path("faq/KB-FAQ-001.md") == ("active", "public")
    assert classify_path("uji_robustness/konflik/KB-POL-002.md") == (
        "superseded",
        "internal",
    )
    assert classify_path("uji_robustness/noise/KB-NOISE-001.md") == (
        "noise",
        "internal",
    )


def test_audit_flags_duplicate_active_doc_id(tmp_path: Path) -> None:
    root = tmp_path / "dokumen"
    front_matter = """
doc_id: KB-POL-001
title: Kebijakan A
category: policy
version: 1.0
last_updated: 2025-01-01
effective_date: 2025-01-02
"""
    write_doc(root, "document_kebijakan/a.md", front_matter)
    write_doc(root, "document_kebijakan/b.md", front_matter)

    result = audit_documents(root)
    codes = {issue.code for issue in result.issues}
    assert "duplicate_active_doc_id" in codes
    assert result.has_errors()


def test_audit_falls_back_effective_date_and_warns_missing_version(tmp_path: Path) -> None:
    root = tmp_path / "dokumen"
    front_matter = """
doc_id: KB-FAQ-001
title: FAQ A
category: faq
last_updated: 2025-07-08
"""
    write_doc(root, "faq/a.md", front_matter)
    result = audit_documents(root)

    document = result.documents[0]
    assert document.effective_date == "2025-07-08"
    assert document.effective_date_source == "last_updated"
    assert document.audience == "public"
    assert any(issue.code == "missing_version" for issue in result.warnings)


def test_audit_flags_active_version_older_than_superseded(tmp_path: Path) -> None:
    root = tmp_path / "dokumen"
    write_doc(
        root,
        "document_kebijakan/active.md",
        """
doc_id: KB-POL-002
title: Refund
category: policy
version: 1.0
effective_date: 2024-01-01
""",
    )
    write_doc(
        root,
        "uji_robustness/konflik/old.md",
        """
doc_id: KB-POL-002
title: Refund lama
category: policy
version: 2.0
effective_date: 2025-01-01
""",
    )

    result = audit_documents(root)
    assert any(issue.code == "active_version_older" for issue in result.errors)


def test_audit_flags_invalid_date(tmp_path: Path) -> None:
    root = tmp_path / "dokumen"
    write_doc(
        root,
        "faq/a.md",
        """
doc_id: KB-FAQ-001
title: FAQ A
category: faq
version: 1.0
last_updated: 08-07-2025
""",
    )
    result = audit_documents(root)
    assert any(issue.code == "invalid_date" for issue in result.errors)


def test_audit_flags_unknown_reference(tmp_path: Path) -> None:
    root = tmp_path / "dokumen"
    write_doc(
        root,
        "faq/a.md",
        """
doc_id: KB-FAQ-001
title: FAQ A
category: faq
version: 1.0
last_updated: 2025-01-01
""",
        body="# FAQ A\n\nLihat KB-POL-999 untuk detail.",
    )
    result = audit_documents(root)
    assert any(issue.code == "unknown_reference" for issue in result.warnings)
