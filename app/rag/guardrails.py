"""Input/output guardrails for the customer-service copilot."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_INJECTION_PATTERNS = [
    r"abaikan\s+(semua\s+)?instruksi",
    r"lupakan\s+(semua\s+)?instruksi",
    r"ignore\s+(all\s+)?(previous\s+)?instructions",
    r"disregard\s+(all\s+)?(previous\s+)?instructions",
    r"system\s*prompt",
    r"prompt\s*sistem",
    r"kamu\s+sekarang\s+adalah",
    r"you\s+are\s+now\s+",
    r"jailbreak",
    r"developer\s+message",
    r"reveal\s+.*(prompt|instruction)",
    r"bypass\s+.*(aturan|rule|guardrail)",
]

_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_PHONE_RE = re.compile(r"(?:\+62|62|0)8[0-9][0-9\s.-]{7,14}[0-9]")
_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
_OTP_RE = re.compile(r"(?i)\b(otp|kode\s+otp|kode\s+verifikasi)\b([^\d]{0,16})(\d{4,8})\b")
_KB_MARKER_RE = re.compile(r"\[?\bKB-(?:POL|FAQ|SOP)-\d{3}\b\]?", re.IGNORECASE)
_INTERNAL_LEAK_RE = re.compile(
    r"(system\s*prompt|prompt\s*sistem|instruksi\s+internal|"
    r"sop\s+internal|kb-sop-\d+|handover\s+shift)",
    re.IGNORECASE,
)

_SAFE_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


@dataclass
class GuardrailResult:
    ok: bool
    sanitized_text: str
    warnings: list[str] = field(default_factory=list)
    reason: str | None = None
    injection_pattern: str | None = None


def detect_prompt_injection(text: str) -> str | None:
    for pattern in _INJECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return pattern
    return None


def redact_sensitive(text: str) -> tuple[str, list[str]]:
    warnings: list[str] = []
    redacted = text

    def replace_email(match: re.Match[str]) -> str:
        warnings.append("email disamarkan")
        return "[EMAIL]"

    def replace_phone(match: re.Match[str]) -> str:
        warnings.append("nomor telepon disamarkan")
        return "[NOMOR_HP]"

    def replace_card(match: re.Match[str]) -> str:
        warnings.append("nomor kartu disamarkan")
        return "[NOMOR_KARTU]"

    def replace_otp(match: re.Match[str]) -> str:
        warnings.append("kode OTP disamarkan")
        return f"{match.group(1)}{match.group(2)}[OTP]"

    redacted = _EMAIL_RE.sub(replace_email, redacted)
    redacted = _CARD_RE.sub(replace_card, redacted)
    redacted = _PHONE_RE.sub(replace_phone, redacted)
    redacted = _OTP_RE.sub(replace_otp, redacted)
    return redacted, list(dict.fromkeys(warnings))


def validate_message(message: str, max_chars: int) -> GuardrailResult:
    text = _SAFE_CHAR_RE.sub("", message).strip()
    if not text:
        return GuardrailResult(
            ok=False,
            sanitized_text="",
            reason="Pesan kosong.",
        )
    if len(text) > max_chars:
        return GuardrailResult(
            ok=False,
            sanitized_text=text,
            reason=f"Pesan terlalu panjang (maksimal {max_chars} karakter).",
        )

    injection = detect_prompt_injection(text)
    if injection:
        return GuardrailResult(
            ok=False,
            sanitized_text=text,
            reason="Pesan mengandung instruksi yang tidak dapat diproses.",
            injection_pattern=injection,
        )

    sanitized, warnings = redact_sensitive(text)
    return GuardrailResult(ok=True, sanitized_text=sanitized, warnings=warnings)


def scrub_customer_reply(text: str) -> tuple[str, list[str]]:
    """Remove internal KB markers and flag obvious internal leaks."""

    warnings: list[str] = []
    cleaned = _KB_MARKER_RE.sub("", text or "").strip()
    if _INTERNAL_LEAK_RE.search(cleaned):
        warnings.append("customer_reply mengandung penanda internal")
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, warnings


def redact_for_log(text: str, max_chars: int = 300) -> str:
    redacted, _ = redact_sensitive(text)
    redacted = " ".join(redacted.split())
    return redacted[:max_chars]
