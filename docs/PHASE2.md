# Fase 2 — Generation, Guardrails, dan API

## Tujuan

1. Mengubah retrieval menjadi jawaban terstruktur yang aman dipakai agen.
2. Memisahkan catatan internal dan balasan pelanggan.
3. Menolak pertanyaan di luar KB, bukan mengarang.
4. Menyediakan API FastAPI yang bisa diuji dan dideploy.

## Alur request

```
POST /api/v1/chat
  -> validasi input + redaksi PII + deteksi prompt injection
  -> embedding query (cache LRU)
  -> hybrid retrieval (dense + BM25 + RRF)
  -> filter status=active, effective_date, audience
  -> refusal gate (kosong / skor rendah)
  -> prompt + context berlabel doc_id/versi/section
  -> OpenRouter chat completion (JSON mode)
  -> validasi skema + validasi sitasi
  -> scrub customer_reply
  -> response terstruktur
```

## Response schema

Field utama:

| Field | Arti |
|---|---|
| `answerable` | Model menilai context cukup atau tidak |
| `internal_notes` | Dasar kebijakan/SOP, hal yang harus dicek, opsi eskalasi |
| `customer_reply` | Balasan siap kirim, tanpa sitasi/prosedur internal |
| `citations` | Dokumen yang benar-benar dikutip dan valid |
| `sources` | Semua chunk yang di-retrieve, dengan skor |
| `confidence` | 0.0–1.0 dari model (0 jika refusal) |
| `needs_escalation` | Perlu diteruskan ke manusia/tim terkait |
| `refusal_reason` | Alasan jika tidak answerable |
| `citation_valid` | Ada minimal satu sitasi valid untuk jawaban answerable |
| `warnings` | PII disamarkan, sitasi tidak valid, potensi leak, dll. |
| `debug` | Hanya jika `debug=true`: skor retrieval, chunk, attempt |

## Guardrails

### Input

- Pesan kosong / terlalu panjang ditolak.
- Prompt injection (ID/EN) ditolak dengan HTTP 400.
- Email, nomor HP, nomor kartu, dan OTP diredaksi sebelum dikirim ke LLM.
  Peringatan redaksi dikembalikan di `warnings`.

### Retrieval

- Hanya dokumen `status=active`.
- `effective_date <= hari ini`.
- Mode `public` hanya mengambil `audience=public`; mode `agent` boleh
  mengambil SOP internal.
- Refusal tanpa LLM jika tidak ada hasil atau skor dense teratas di bawah
  `MIN_DENSE_SCORE`.

### Generation

- System prompt melarang jawaban di luar context, menjanjikan di luar
  kebijakan, membocorkan system prompt, atau meminta OTP/PIN/CVV.
- Model wajib mengembalikan JSON dengan `answerable`, `internal_notes`,
  `customer_reply`, `cited_doc_ids`, `needs_escalation`.
- Jika context tidak cukup, `answerable=false` dan `customer_reply` berisi
  permintaan maaf + eskalasi.
- `customer_reply` tidak boleh menyebut `KB-*`, SOP internal, atau prosedur
  internal. Pelanggaran -> refusal + eskalasi.

### Citation

- `cited_doc_ids` harus subset dari doc_id yang ada di context.
- Sitasi inline `[KB-...]` di `internal_notes` ikut diekstrak.
- Jika jawaban answerable tetapi tidak punya sitasi valid:
  `citation_valid=false`, `needs_escalation=true`, `warnings` diisi.
- `sources` tetap dikembalikan agar agen bisa memeriksa sendiri.

## API

| Method | Path | Catatan |
|---|---|---|
| POST | `/api/v1/chat` | JSON, non-streaming |
| GET | `/api/v1/health` | Tidak memanggil layanan eksternal |
| GET | `/api/v1/ready` | 503 jika index/service belum siap |
| GET | `/api/v1/documents` | Filter category/audience/status |
| GET | `/api/v1/documents/{doc_id}` | Metadata + chunk |
| GET | `/api/v1/meta` | Index/model/prompt version |
| POST | `/api/v1/feedback` | Log-only |

Error format:

```json
{"error": {"code": "input_rejected", "message": "...", "request_id": "..."}}
```

- 400 input/injection
- 422 schema request
- 429 rate limit (ada `Retry-After`)
- 503 service/index belum siap
- 500 error internal

Rate limit in-memory per IP. FastAPI Cloud bisa menjalankan sampai 3 replica,
jadi limit efektif bisa 3x. Untuk produksi, pindahkan ke Cloudflare/Redis.

## Provider chat

| Mode | Provider | Model | Catatan |
|---|---|---|---|
| Development | DeepSeek | `deepseek-flash` | Murah, JSON output, thinking disabled |
| Deploy/demo | OpenRouter | `baidu/ernie-5.5-flash-preview:free` | Gratis; fallback Gemma 26B |

DeepSeek memakai endpoint OpenAI-compatible
`https://api.deepseek.com/chat/completions`. Model `deepseek-flash` mendukung
JSON Output; thinking mode dimatikan agar latency dan output token lebih rendah.
DeepSeek **tidak menyediakan embeddings**, sehingga query embedding tetap
memakai OpenRouter `nvidia/nemotron-3.5-embed-8b:free`.

## Hasil uji free model OpenRouter

| Model | Catatan |
|---|---|
| `google/gemma-4-31b-it:free` | Sering 429 upstream |
| `google/gemma-4-26b-a4b-it:free` | JSON bagus, tetapi kadang 429 |
| `baidu/ernie-5.5-flash-preview:free` | JSON bagus, paling stabil saat diuji |
| `openrouter/free` | Auto-router; bisa memilih model reasoning yang mengembalikan content kosong |
| `nvidia/nemotron-3.5-lightning:free` | Reasoning panjang; content bisa kosong jika max_tokens habis |

Default OpenRouter: ERNIE primary, Gemma 26B fallback. `reasoning_effort=low`
dikirim jika didukung; jika ditolak, client retry tanpa parameter itu. Untuk
DeepSeek, payload memakai `thinking={"type":"disabled"}` dan tidak mengirim
`reasoning_effort`.

## Hasil smoke test nyata

| Kasus | Hasil |
|---|---|
| Refund GoPay berapa lama + biaya admin | answerable, sitasi `KB-POL-002`, ~17,8 dtk (termasuk fallback) |
| Visa Jepang | refusal, `answerable=false`, ~14,2 dtk |
| Biaya admin kartu kredit via API | answerable, 2 sitasi, ~12,4 dtk |

Catatan: pada kasus kartu kredit, model perlu satu retry karena JSON pertama
tidak lolos skema. Retry ini memakai satu request tambahan. Untuk menghemat
kuota, `max_tokens` dinaikkan ke 1400 agar JSON tidak terpotong.

Kuota free key selama pengembangan sempat tersisa 2/50 request. Ini normal
karena diagnostik model/embedding. Evaluasi penuh harus dijadwalkan, bukan
dijalankan berulang.

## Test

- 49 test lulus.
- Test mencakup: parsing JSON, retry, clamp confidence, guardrail injection,
  redaksi PII, refusal, sitasi tidak valid, leak SOP, filter mode publik,
  endpoint API, rate limit 429, serta payload provider DeepSeek/OpenRouter.

## Batasan

- Generation belum dievaluasi pada 50 pertanyaan; baru smoke test.
- Latency 12–18 detik dengan model free; perlu loading state/streaming di UI.
- Rate limit dan budget bersifat per-process, bukan global.
- Belum ada autentikasi; endpoint dokumen menampilkan SOP internal (data
  sintetis). Untuk demo publik, pertimbangkan basic auth atau mode public.
- Feedback hanya masuk log (retensi log FastAPI Cloud 1 hari).
- `data/index` harus ikut deploy atau dibangun ulang sebelum deploy.
