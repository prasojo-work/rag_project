"""Text utilities shared by ingestion, retrieval, and evaluation."""

from __future__ import annotations

import math
import re

# Keep negations ("tidak", "tanpa", "belum") because they change policy meaning.
STOPWORDS = {
    "ada",
    "adalah",
    "akan",
    "anda",
    "antar",
    "atau",
    "bagi",
    "bahwa",
    "bila",
    "bisa",
    "dalam",
    "dan",
    "dapat",
    "dari",
    "dengan",
    "di",
    "dimana",
    "ini",
    "itu",
    "jika",
    "juga",
    "ke",
    "kepada",
    "kita",
    "maka",
    "mereka",
    "oleh",
    "pada",
    "para",
    "saat",
    "sebagai",
    "sedang",
    "sehingga",
    "setelah",
    "sudah",
    "tersebut",
    "untuk",
    "yang",
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def estimate_tokens(text: str) -> int:
    """Cheap token estimate for Bahasa Indonesia.

    Roughly 4 characters per token. This is intentionally dependency-free: the
    exact tokenizer is model-specific and only used for chunk sizing.
    """

    return max(1, math.ceil(len(text) / 4))


def normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def tokenize(text: str) -> list[str]:
    """Tokenize for BM25.

    Lowercase, keep alphanumerics, drop common function words. Single digits are
    kept because policy answers often hinge on "7 hari" or "3 hari".
    """

    tokens = _TOKEN_RE.findall(text.lower())
    return [token for token in tokens if token.isdigit() or token not in STOPWORDS]


def slugify(text: str, max_length: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (slug or "bagian")[:max_length].strip("-")


def truncate(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"
