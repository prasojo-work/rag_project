"""Markdown-aware, table-safe chunking for the TravelKita knowledge base."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass

from app.rag.models import Chunk, Document
from app.rag.text import estimate_tokens, normalize_whitespace, slugify

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")
_LIST_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Section:
    path: str
    heading_line: str | None
    lines: list[str]


def _is_table_start(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    first = lines[index].lstrip()
    second = lines[index + 1].lstrip()
    return first.startswith("|") and bool(_TABLE_SEPARATOR_RE.match(second))


def iter_sections(body: str) -> list[Section]:
    """Split a Markdown body into heading-scoped sections.

    H1 is treated as the document title, not as a section. Content directly
    under H1 (common in FAQ documents) becomes section ``Umum``.
    """

    lines = body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    sections: list[Section] = []
    stack: list[tuple[int, str]] = []
    current_lines: list[str] = []
    current_path = "Umum"
    current_heading_line: str | None = None

    def flush() -> None:
        nonlocal current_lines
        content = "\n".join(current_lines).strip()
        if content:
            sections.append(
                Section(
                    path=current_path,
                    heading_line=current_heading_line,
                    lines=current_lines,
                )
            )
        current_lines = []

    for line in lines:
        match = _HEADING_RE.match(line)
        if not match:
            current_lines.append(line)
            continue

        flush()
        level = len(match.group(1))
        heading_text = match.group(2).strip()

        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, heading_text))

        visible = [text for heading_level, text in stack if heading_level > 1]
        current_path = " > ".join(visible) if visible else "Umum"
        current_heading_line = line.strip() if level > 1 else None

    flush()
    return sections


def _hard_split(text: str, max_tokens: int) -> list[str]:
    max_chars = max(200, max_tokens * 4)
    return [text[index : index + max_chars].strip() for index in range(0, len(text), max_chars)]


def _split_oversized_text(text: str, max_tokens: int) -> list[str]:
    if estimate_tokens(text) <= max_tokens:
        return [text.strip()]

    pieces: list[str] = []
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block:
            continue
        if estimate_tokens(block) <= max_tokens:
            pieces.append(block)
            continue

        for line in block.split("\n"):
            line = line.rstrip()
            if not line:
                continue
            if estimate_tokens(line) <= max_tokens:
                pieces.append(line)
                continue

            for sentence in _SENTENCE_RE.split(line):
                sentence = sentence.strip()
                if not sentence:
                    continue
                if estimate_tokens(sentence) <= max_tokens:
                    pieces.append(sentence)
                else:
                    pieces.extend(_hard_split(sentence, max_tokens))
    return pieces


def split_prose(lines: list[str], max_tokens: int = 500) -> list[str]:
    text = normalize_whitespace("\n".join(lines))
    if not text:
        return []
    if estimate_tokens(text) <= max_tokens:
        return [text]

    blocks = _split_oversized_text(text, max_tokens)
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for block in blocks:
        block_tokens = estimate_tokens(block)
        separator_tokens = estimate_tokens("\n\n") if current else 0
        if current and current_tokens + separator_tokens + block_tokens > max_tokens:
            chunks.append("\n\n".join(current).strip())
            current = [block]
            current_tokens = block_tokens
        else:
            current.append(block)
            current_tokens += separator_tokens + block_tokens
    if current:
        chunks.append("\n\n".join(current).strip())
    return chunks


def split_table(lines: list[str], max_tokens: int = 900) -> list[str]:
    """Split a table while repeating the header and separator rows."""

    non_empty = [line for line in lines if line.strip()]
    if len(non_empty) < 2:
        return [normalize_whitespace("\n".join(non_empty))] if non_empty else []

    header = non_empty[:2]
    rows = non_empty[2:]
    if not rows:
        return ["\n".join(header)]

    groups: list[list[str]] = []
    current: list[str] = []
    for row in rows:
        candidate = header + current + [row]
        if current and estimate_tokens("\n".join(candidate)) > max_tokens:
            groups.append(header + current)
            current = [row]
        else:
            current.append(row)
    if current:
        groups.append(header + current)
    return ["\n".join(group) for group in groups]


def split_table_segments(lines: list[str]) -> Iterable[tuple[str, list[str]]]:
    """Yield alternating ``prose`` and ``table`` segments from section lines."""

    index = 0
    prose_buffer: list[str] = []

    while index < len(lines):
        if not _is_table_start(lines, index):
            prose_buffer.append(lines[index])
            index += 1
            continue

        if prose_buffer:
            yield "prose", prose_buffer
            prose_buffer = []

        table_lines: list[str] = []
        while index < len(lines) and lines[index].strip().startswith("|"):
            table_lines.append(lines[index])
            index += 1
        yield "table", table_lines

    if prose_buffer:
        yield "prose", prose_buffer


def _chunk_type(section_path: str, segment_type: str, text: str, category: str) -> str:
    if segment_type == "table":
        return "table"
    if "riwayat versi" in section_path.lower():
        return "changelog"
    if category == "faq":
        return "faq"
    content_lines = [line for line in text.splitlines() if line.strip()]
    if content_lines:
        list_lines = sum(1 for line in content_lines if _LIST_RE.match(line))
        if list_lines / len(content_lines) >= 0.4:
            return "steps"
    return "prose"


def make_embedding_text(chunk: Chunk) -> str:
    version = chunk.version or "-"
    effective_date = chunk.effective_date or "-"
    subcategory = chunk.subcategory or "-"
    return "\n".join(
        [
            f"Dokumen: {chunk.doc_id} — {chunk.title}",
            (
                f"Kategori: {chunk.category}/{subcategory} | Versi: {version} | "
                f"Berlaku: {effective_date} | Status: {chunk.status} | "
                f"Audiens: {chunk.audience}"
            ),
            f"Bagian: {chunk.section_path}",
            f"Tipe: {chunk.chunk_type}",
            "---",
            chunk.text,
        ]
    )


def chunk_document(
    document: Document,
    max_tokens: int = 500,
    table_max_tokens: int = 900,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    part_number = 0

    for section in iter_sections(document.body):
        for segment_type, segment_lines in split_table_segments(section.lines):
            if segment_type == "table":
                parts = split_table(segment_lines, max_tokens=table_max_tokens)
            else:
                parts = split_prose(segment_lines, max_tokens=max_tokens)

            for part in parts:
                part = part.strip()
                if not part:
                    continue

                part_number += 1
                text = f"{section.heading_line}\n\n{part}" if section.heading_line else part
                text = normalize_whitespace(text)

                section_slug = slugify(section.path)
                chunk_id = f"{document.doc_id}::{section_slug}::{part_number:02d}"
                chunk = Chunk(
                    chunk_id=chunk_id,
                    doc_id=document.doc_id,
                    title=document.title,
                    category=document.category,
                    subcategory=document.subcategory,
                    version=document.version,
                    effective_date=document.effective_date,
                    last_updated=document.last_updated,
                    status=document.status,
                    audience=document.audience,
                    section_path=section.path,
                    chunk_type=_chunk_type(section.path, segment_type, part, document.category),
                    text=text,
                    embedding_text="",
                    token_estimate=estimate_tokens(text),
                    source_path=document.source_path,
                    doc_hash=document.doc_hash,
                    chunk_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                )
                chunk.embedding_text = make_embedding_text(chunk)
                chunks.append(chunk)

    # Guard against accidental duplicate IDs if a section heading repeats.
    seen: dict[str, int] = {}
    for chunk in chunks:
        if chunk.chunk_id in seen:
            seen[chunk.chunk_id] += 1
            chunk.chunk_id = f"{chunk.chunk_id}-{seen[chunk.chunk_id]}"
        else:
            seen[chunk.chunk_id] = 1

    return chunks


def chunk_documents(
    documents: Iterable[Document],
    max_tokens: int = 500,
    table_max_tokens: int = 900,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for document in documents:
        chunks.extend(
            chunk_document(
                document,
                max_tokens=max_tokens,
                table_max_tokens=table_max_tokens,
            )
        )

    # Active and superseded versions can share a doc_id/section. Keep chunk IDs
    # globally unique so fixtures can be indexed alongside production docs.
    seen: dict[str, int] = {}
    for chunk in chunks:
        if chunk.chunk_id in seen:
            seen[chunk.chunk_id] += 1
            chunk.chunk_id = f"{chunk.chunk_id}-{seen[chunk.chunk_id]}"
            chunk.embedding_text = make_embedding_text(chunk)
        else:
            seen[chunk.chunk_id] = 1

    return chunks
