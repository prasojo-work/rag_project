from __future__ import annotations

from app.rag.chunking import chunk_document, chunk_documents, iter_sections
from app.rag.models import Document


def make_document(body: str, category: str = "policy") -> Document:
    return Document(
        doc_id="KB-POL-002",
        title="Kebijakan Refund",
        category=category,
        subcategory="refund",
        version="2.5",
        last_updated="2025-08-20",
        effective_date="2025-09-01",
        owner="Divisi Refund",
        status="active",
        audience="public" if category != "sop" else "internal",
        source_path="dokumen/document_kebijakan/KB-POL-002.md",
        body=body,
        front_matter={},
        doc_hash="abc",
        effective_date_source="explicit",
    )


def test_iter_sections_builds_heading_paths() -> None:
    body = """
# Judul

Intro.

## 1. Prinsip

Isi prinsip.

### 1.1 Detail

Isi detail.

## 2. Tabel

Isi tabel.
"""
    sections = iter_sections(body)
    paths = [section.path for section in sections]
    assert "Umum" in paths
    assert "1. Prinsip" in paths
    assert "1. Prinsip > 1.1 Detail" in paths
    assert "2. Tabel" in paths


def test_table_is_not_split_mid_row_and_header_is_repeated() -> None:
    rows = "\n".join(f"| Metode {index} | {index} hari |" for index in range(1, 31))
    body = f"""
# Kebijakan

## 2. Metode

Tabel berikut menjelaskan proses refund.

| Metode | Lama |
|---|---|
{rows}

Setelah tabel ada penjelasan.
"""
    chunks = chunk_document(make_document(body), max_tokens=60, table_max_tokens=80)
    table_chunks = [chunk for chunk in chunks if chunk.chunk_type == "table"]

    assert len(table_chunks) > 1
    for chunk in table_chunks:
        assert "| Metode | Lama |" in chunk.text
        assert "|---|---|" in chunk.text

    merged = "\n".join(chunk.text for chunk in table_chunks)
    for index in range(1, 31):
        assert f"Metode {index}" in merged


def test_faq_document_is_one_chunk() -> None:
    body = """
# Bagaimana cara refund?

Refund akan diproses setelah pembatalan disetujui.

1. Buka menu Pesanan.
2. Pilih refund.
"""
    chunks = chunk_document(make_document(body, category="faq"))
    assert len(chunks) == 1
    assert chunks[0].section_path == "Umum"
    assert chunks[0].chunk_type == "faq"
    assert "Dokumen: KB-POL-002" in chunks[0].embedding_text


def test_long_prose_is_split_under_limit() -> None:
    paragraphs = "\n\n".join(
        "Kalimat panjang tentang kebijakan refund dan pembatalan tiket. " * 8 for _ in range(5)
    )
    body = f"# Kebijakan\n\n## 1. Penjelasan\n\n{paragraphs}\n"
    chunks = chunk_document(make_document(body), max_tokens=100)
    assert len(chunks) > 1
    assert all(chunk.token_estimate <= 130 for chunk in chunks)


def test_chunk_ids_are_unique() -> None:
    body = """
# Kebijakan

## 1. A

Isi A.

## 1. A

Isi A kedua.
"""
    chunks = chunk_document(make_document(body))
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)


def test_chunk_ids_are_unique_across_document_versions() -> None:
    body = """
# Kebijakan

## 1. A

Isi A.
"""
    document = make_document(body)
    chunks = chunk_documents([document, document])
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)
