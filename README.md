# TravelKita RAG — Customer Service Copilot

Portfolio project: asisten knowledge base untuk agen Customer Service TravelKita.
Dokumen perusahaan bersifat **fiktif/sintetis**; project ini bukan layanan nyata.

Status saat ini: **Fase 4 selesai — evaluasi generation**.
Index nyata ada di `data/index/` (85 chunk, 4096 dimensi, ~1,4 MB). Deploy ke
FastAPI Cloud belum dikerjakan.

## Arsitektur data (Fase 1)

```
dokumen/*.md
    │
    ├─ audit metadata / versi / duplikat / referensi
    │
    ├─ chunker Markdown-aware (tabel tidak dipotong)
    │
    ├─ embedding offline via OpenRouter
    │
    └─ data/index/
         ├─ chunks.jsonl
         ├─ embeddings.npy   (float32, L2-normalized)
         └─ manifest.json
                │
                └─ NumPy cosine + BM25 → Reciprocal Rank Fusion
```

Tanpa ChromaDB, tanpa server database. Corpus 25 dokumen aktif ≈ 85 chunk,
jadi pencarian brute-force NumPy lebih sederhana dan jauh lebih cepat cold
start-nya.

## Quick start

Prasyarat: Python 3.12 dan [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env
# Development:
#   LLM_PROVIDER=deepseek
#   DEEPSEEK_API_KEY=...
# Embedding tetap butuh OpenRouter:
#   OPENROUTER_API_KEY=...
```

Untuk deploy/demo dengan OpenRouter:

```dotenv
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=...
```

DeepSeek tidak menyediakan endpoint embeddings, jadi index tetap memakai
`nvidia/nemotron-3.5-embed-8b:free` dari OpenRouter.

Audit data:

```bash
uv run python scripts/audit_data.py
```

Build index (memanggil OpenRouter Embeddings):

```bash
uv run python scripts/build_index.py
```

Evaluasi retrieval (50 pertanyaan):

```bash
uv run python scripts/evaluate_retrieval.py
```

Baseline BM25 tanpa memanggil API (bisa dijalankan tanpa API key):

```bash
uv run python scripts/evaluate_retrieval.py \
  --provider none \
  --modes bm25
```

Cek konsistensi artefak index:

```bash
uv run python scripts/check_index.py --root dokumen
```

Test:

```bash
uv run pytest
uv run ruff check .
```

### Smoke test tanpa API key

Untuk memvalidasi pipeline tanpa memakai kuota:

```bash
uv run python scripts/build_index.py --provider hash --out /tmp/index-smoke
uv run python scripts/evaluate_retrieval.py \
  --index /tmp/index-smoke \
  --provider hash \
  --out /tmp/eval-smoke
```

Provider `hash` bersifat sintetis (feature hashing). Hasilnya **bukan** baseline
kualitas retrieval; hanya memastikan kode, chunking, dan format index berjalan.

## Hasil audit saat ini

- 31 file Markdown: **25 aktif**, 3 superseded (versi lama), 3 noise.
- 0 error, 15 warning.
- Warning: 15 FAQ tidak punya field `version`; `effective_date` diturunkan dari
  `last_updated`.
- Tidak ada duplikasi `doc_id` pada dokumen aktif.
- Laporan: `data/audit/report.md` dan `data/audit/report.json`.

## Baseline retrieval (nyata)

Embedding: `nvidia/nemotron-3.5-embed-8b:free` (4096 dimensi).
Dihitung pada 48 pertanyaan yang punya `source_doc_ids`; 2 pertanyaan
unanswerable dipisahkan untuk evaluasi refusal.

| Mode | Recall@5 | Hit@5 | MRR@10 | nDCG@5 |
|---|---:|---:|---:|---:|
| Dense | 0.955 | 1.000 | **0.990** | **0.937** |
| BM25 | 0.941 | 1.000 | 0.929 | 0.886 |
| Hybrid RRF | **0.976** | 1.000 | 0.958 | 0.925 |

Temuan:

- Hybrid menang di **Recall@5** (0.976), artinya paling sering menemukan semua
  dokumen yang dibutuhkan dalam top-5.
- Dense menang di **MRR/nDCG**, artinya dokumen paling relevan biasanya berada
  di peringkat paling atas.
- BM25 sudah kuat, tetapi turun di pertanyaan `hard` (Recall@5 0.833).
- Sisa miss terutama pertanyaan multi-dokumen (mis. overbooking butuh
  `KB-POL-003` + `KB-POL-005`). Ini kandidat untuk perbaikan di fase generation
  (menaikkan top-k context) atau query expansion.

Detail: `data/eval/retrieval_report.md`.

## UI (Fase 3)

Jalankan server lalu buka `http://127.0.0.1:8000/`:

```bash
uv run fastapi dev app/main.py
```

| Halaman | Isi |
|---|---|
| `/` | Chat pelanggan: balasan, chip sumber, feedback |
| `/internal/eval` | Dashboard retrieval (tidak ditautkan) |
| `/internal/documents` | Daftar dokumen (tidak ditautkan) |
| `/internal/documents/{doc_id}` | Detail dokumen + chunk (tidak ditautkan) |
| `/internal/about` | Arsitektur, keputusan, batasan (tidak ditautkan) |

UI publik sengaja hanya menampilkan **Chat**. Tidak ada statistik retrieval,
skor, model, latency, internal notes, atau debug. Default UI memakai mode
`public`, sehingga SOP internal tidak dipakai.

Stack UI: **Jinja2 + HTMX + vanilla JS + CSS manual**. Tidak ada Node/build
step, tidak ada CDN. HTMX di-vendor di `static/js/htmx.min.js`.

Detail: `docs/PHASE3.md`.

### Fallback BM25

Jika embedding query gagal karena kuota OpenRouter habis, backend otomatis
memakai **BM25**. API menambahkan warning di response; UI pelanggan tetap
menampilkan jawaban biasa. Chat tetap jalan dengan DeepSeek/OpenRouter, dan
hybrid kembali aktif saat embedding tersedia.

## Evaluasi Generation (Fase 4)

Jalankan:

```bash
# Agent: seluruh KB
uv run python scripts/evaluate_generation.py --mode agent --judge-limit 20

# Public: hanya pertanyaan yang ground truth-nya public
uv run python scripts/evaluate_generation.py \
  --mode public --only-public-ground-truth --judge-limit 20 --tag customer
```

Hasil utama:

| Skenario | Answer rate | Citation valid | Leak | Judge correctness | Hallucination | p95 latency |
|---|---:|---:|---:|---:|---:|---:|
| Agent, 50 pertanyaan | 1.000 | 1.000 | 0 | 4.70 | 0/20 | 4.9 s |
| Public customer, 38 pertanyaan | 1.000 | 1.000 | 0 | 4.85 | 0/20 | 3.8 s |
| Public safety SOP, 8 pertanyaan | 0.875 | 1.000 | 0 | — | — | 4.1 s |

Catatan penting:

- Semua run generation memakai **BM25 fallback** karena kuota embedding
  OpenRouter habis. Hasil ini belum mengukur hybrid + generation.
- Judge memakai `deepseek-v4-pro`; generator `deepseek-flash`. Masih satu
  provider, jadi ada self-provider bias.
- SOP adalah area terlemah (judge correctness 3.50) karena pertanyaan
  multi-dokumen; lihat `docs/PHASE4.md`.

Laporan:

- `data/eval/generation_agent_report.md`
- `data/eval/generation_public_customer_report.md`
- `data/eval/generation_public_report.md`

## API (Fase 2)

Jalankan server lokal:

```bash
uv run fastapi dev app/main.py
```

Endpoint:

| Method | Path | Fungsi |
|---|---|---|
| POST | `/api/v1/chat` | Pertanyaan → `internal_notes` + `customer_reply` + sitasi |
| GET | `/api/v1/health` | Status index/service |
| GET | `/api/v1/ready` | Kesiapan service |
| GET | `/api/v1/documents` | Daftar dokumen |
| GET | `/api/v1/documents/{doc_id}` | Detail dokumen + chunk |
| GET | `/api/v1/meta` | Versi index, model, prompt |
| POST | `/api/v1/feedback` | Thumbs up/down (log-only) |

Contoh:

```bash
curl -s http://127.0.0.1:8000/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Refund ke GoPay berapa lama dan berapa biaya adminnya?","mode":"agent"}' \
  | python -m json.tool
```

Response memisahkan:

- **`internal_notes`** — dasar kebijakan/SOP dan hal yang perlu dicek agen.
- **`customer_reply`** — balasan siap kirim, tanpa sitasi/prosedur internal.
- **`citations`** / **`sources`** — dokumen yang dikutip dan seluruh sumber
  yang di-retrieve.
- **`answerable`, `confidence`, `needs_escalation`, `citation_valid`** —
  sinyal untuk UI dan evaluasi.

### Guardrails yang aktif

- Validasi panjang pesan dan penolakan prompt injection.
- Redaksi email, nomor HP, nomor kartu, dan OTP sebelum dikirim ke LLM.
- Refusal gate jika retrieval kosong atau skor relevansi terlalu rendah.
- Model dipaksa menjawab hanya dari context dan menentukan `answerable`.
- Validasi sitasi: doc_id yang tidak ada di context ditandai tidak valid.
- `customer_reply` dibersihkan dari penanda `KB-*`; jika terdeteksi bocoran
  prosedur internal, jawaban diubah menjadi refusal + eskalasi.
- Rate limit per IP dan budget request harian (in-memory, per replica).

### Provider chat: development vs deploy

| Mode | Provider | Model | Catatan |
|---|---|---|---|
| Development | DeepSeek | `deepseek-flash` | Murah, JSON output, thinking dimatikan |
| Deploy/demo | NVIDIA NIM | `minimaxai/minimax-m3.1-flash` | Gratis, ~40 RPM, JSON mode, 12 s |
| Deploy/demo (lama) | OpenRouter | `baidu/ernie-5.5-flash-preview:free` | Gratis, 50 req/hari, sering 429 |

Provider chat dan embedding kini **generik**: `LLM_PROVIDER` boleh nama apa pun
selama endpoint-nya OpenAI-compatible, lalu isi `LLM_BASE_URL`, `LLM_API_KEY`,
dan `LLM_MODEL`. Hanya `deepseek` dan `openrouter` yang punya shorthand khusus.
Menambah provider baru cukup edit `.env`, tanpa menyentuh kode.

- DeepSeek dan Groq **tidak punya embeddings**. NVIDIA NIM punya:
  `nvidia/nemotron-3.5-embed-8b`. Vector query dari NVIDIA identik dengan yang
  dipakai membangun index (`cosine 1.000000`), jadi index tidak perlu dibangun
  ulang. Model ini asimetris sehingga `EMBEDDING_INPUT_TYPE=query` wajib diisi,
  dan rebuild index harus memakai `--input-type passage`.
- DeepSeek `deepseek-flash` mendukung JSON output. Thinking mode dimatikan
  (`thinking: {"type": "disabled"}`) agar lebih cepat dan murah.
- OpenRouter free dibatasi ~50 request/hari; **embedding query ikut dihitung**.
  Jika kuota habis, aplikasi otomatis memakai BM25 fallback dan tetap bisa
  menjawab lewat DeepSeek. Pantau kuota di
  `GET https://openrouter.ai/api/v1/key`.
- Latency OpenRouter free sekitar 12–18 detik. DeepSeek non-thinking biasanya
  lebih cepat; ukur sendiri dengan `latency_ms` di response.
- Ganti provider cukup lewat env:

```dotenv
# Provider generik — contoh NVIDIA NIM
LLM_PROVIDER=nvidia
LLM_BASE_URL=https://integrate.api.nvidia.com/v1
LLM_API_KEY=nvapi-...
LLM_MODEL=minimaxai/minimax-m3.1-flash

# Embedding ikut NVIDIA; key dan base_url diwarisi dari LLM_* di atas
EMBEDDING_PROVIDER=nvidia
EMBEDDING_MODEL=nvidia/nemotron-3.5-embed-8b
EMBEDDING_INPUT_TYPE=query
```

Shorthand lama tetap berfungsi:

```dotenv
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=...
```

### Jika key/kuota bermasalah

| Kondisi | Perilaku |
|---|---|
| `DEEPSEEK_API_KEY` kosong atau placeholder seperti `-`, `OPENROUTER_API_KEY` ada | Fallback otomatis ke OpenRouter |
| Provider membalas **429** (rate limit sementara) | Pesan "layanan sedang ramai, coba lagi dalam satu menit", reason `llm_rate_limited`. Body 429 dan `Retry-After` ikut dicatat di log |
| Provider membalas **402/403** (kredit/kuota habis) | Pesan "mencapai batas kapasitas harian", reason `llm_quota_exhausted` |
| Embedding gagal (429/5xx) | Otomatis BM25 fallback + warning di response; chat tetap jalan |
| Semua key kosong | Index tetap dimuat, tetapi `/api/v1/ready` = 503 dan `/api/v1/chat` = 503 |

Catatan: `/api/v1/ready` tidak memanggil provider (agar tidak membakar kuota),
jadi statusnya bisa `ready` meskipun kuota harian sudah habis. Kuota baru
terdeteksi saat request chat.

## Troubleshooting embedding 502

Model `nvidia/nemotron-3.5-embed-1b:free` saat diuji **gagal untuk batch >1**
(HTTP 502 `service inference failed`) meskipun satu input berhasil. Gunakan
model default `nvidia/nemotron-3.5-embed-8b:free`, atau:

```bash
uv run python scripts/build_index.py --batch-size 1
```

## Keputusan retrieval

- **Dense**: cosine similarity dengan vektor NumPy yang sudah dinormalisasi.
- **BM25**: penting untuk angka spesifik (`7 hari kerja`, `Rp 25.000`) dan
  `doc_id` seperti `KB-POL-002`.
- **Hybrid**: Reciprocal Rank Fusion (RRF), default.
- Filter metadata: `status=active`, `effective_date <= as_of`, `audience`.
- Dokumen konflik versi dan noise **tidak** masuk index produksi; keduanya
  disimpan sebagai fixture untuk pengujian robustness.

## Test

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Status: **63 test passed** (data pipeline, retrieval, generation, guardrails,
API, UI Jinja/HTMX, provider config, judge).

## Struktur

```
app/
  main.py         # API JSON + halaman Jinja + HTMX routes
  core/           # config, logging, rate limit
  services/chat.py# orkestrasi retrieval + generation + guardrails
  schemas/chat.py # Pydantic request/response
  rag/
    audit.py      # validasi metadata, duplikat, versi, referensi
    chunking.py   # section-aware + table-safe chunker
    embeddings.py # OpenRouter + hash smoke provider
    eval_report.py# loader dashboard evaluasi
    frontmatter.py# parser YAML front matter
    index.py      # NumPy cosine + BM25 + RRF
    llm.py        # DeepSeek/OpenRouter chat client
    prompt.py     # system prompt + context builder
    generation.py # parser JSON + validasi schema
    judge.py      # LLM-as-judge evaluasi generation
    guardrails.py # injection, PII, scrub output
    metrics.py    # recall, MRR, nDCG
  templates/      # Jinja: chat, eval, about, documents, partials
  static/         # CSS, vanilla JS, htmx.min.js
scripts/
  audit_data.py
  build_index.py
  check_index.py
  evaluate_retrieval.py
  evaluate_generation.py
tests/
data/audit/       # laporan audit
data/index/       # artefak index (dibuat oleh build_index)
data/eval/        # hasil evaluasi (dibuat oleh evaluate_retrieval)
```

## Belum dikerjakan

- Deploy ke FastAPI Cloud + CI.
- Rerun generation eval dengan hybrid retrieval setelah kuota embedding tersedia.
- Streaming response (opsional).
- Autentikasi/basic auth untuk demo publik.
- Multi-turn conversation dan penyimpanan feedback.
- Perbaikan retrieval multi-dokumen (force majeure, Platinum/viral).

## Disclaimer

Seluruh nama perusahaan, kebijakan, harga, dan prosedur adalah data sintetis
untuk keperluan portfolio. Jangan memasukkan data pribadi nyata. Model gratis
OpenRouter dapat memakai request untuk perbaikan produk; gunakan hanya data
sintetis.
