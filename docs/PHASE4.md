# Fase 4 — Evaluasi Generation

## Tujuan

Mengukur kualitas jawaban, bukan hanya retrieval:

- correctness terhadap ground truth,
- completeness,
- faithfulness terhadap konteks,
- citation support,
- refusal/eskalasi,
- kebocoran penanda internal,
- latency dan token usage.

## Metodologi

Dua lapis evaluasi:

1. **Deterministik (semua pertanyaan)**
   - answer/refusal
   - citation validity
   - source hit & citation hit
   - internal leak
   - latency
   - token prompt/completion
   - retrieval mode (hybrid/BM25)

2. **LLM-as-judge (subset stratifikasi, default 20)**
   - 2 pertanyaan unanswerable
   - ~50% hard, ~30% medium, ~20% easy
   - skor 1–5: correctness, completeness, faithfulness, citation support,
     escalation
   - boolean hallucination + catatan

Judge memakai `deepseek-v4-pro`; generator memakai `deepseek-flash`. Keduanya
satu provider, jadi masih ada **self-provider bias**. Validasi manual subset
tetap disarankan.

Hasil generation di-cache per `mode + index_version + generator + prompt_version`.
Judge di-cache per pertanyaan. Rerun tidak memanggil API untuk item yang sudah
ada, kecuali `--refresh`.

## Perintah

```bash
# Agent mode: seluruh KB, ground truth lengkap
uv run python scripts/evaluate_generation.py --mode agent --judge-limit 20

# Public mode: hanya pertanyaan yang ground-truth-nya public
uv run python scripts/evaluate_generation.py \
  --mode public \
  --only-public-ground-truth \
  --judge-limit 20 \
  --tag customer

# Public safety: pertanyaan SOP, tanpa judge
uv run python scripts/evaluate_generation.py \
  --mode public \
  --only-categories sop \
  --judge-limit 0
```

Output:

- `data/eval/generation_agent.json` + `generation_agent_report.md`
- `data/eval/generation_public_customer.json` + report
- `data/eval/generation_public.json` + report (safety SOP)

## Hasil

### Agent mode — 50 pertanyaan

| Metrik | Nilai |
|---|---:|
| Answer rate (48 answerable) | 1.000 |
| Refusal accuracy (2 unanswerable) | 1.000 |
| Citation validity | 1.000 |
| Source hit rate | 1.000 |
| Citation hit rate | 1.000 |
| Internal leak | 0 |
| Judge correctness | 4.70 / 5 |
| Completeness | 4.60 / 5 |
| Faithfulness | 4.85 / 5 |
| Citation support | 4.65 / 5 |
| Escalation | 4.85 / 5 |
| Hallucination | 0 / 20 |
| Latency p50 / p95 | 3.842 / 4.922 ms |
| Retrieval mode | BM25 fallback 50/50 |

Per kategori (judge correctness):

| Kategori | Nilai |
|---|---:|
| Booking | 5.00 |
| Refund | 5.00 |
| Pembatalan | 4.50 |
| Pembayaran | 4.50 |
| SOP | 3.50 |

### Public customer mode — 38 pertanyaan public-ground-truth

| Metrik | Nilai |
|---|---:|
| Answer rate | 1.000 |
| Citation validity | 1.000 |
| Internal leak | 0 |
| Internal sources | 0 |
| Judge correctness | 4.85 / 5 |
| Completeness | 4.80 / 5 |
| Faithfulness | 4.95 / 5 |
| Citation support | 4.85 / 5 |
| Escalation | 4.95 / 5 |
| Hallucination | 0 / 20 |
| Latency p50 / p95 | 2.968 / 3.792 ms |
| Retrieval mode | BM25 fallback 38/38 |

### Public safety — 8 pertanyaan SOP

| Metrik | Nilai |
|---|---:|
| Internal leak | 0 |
| Internal sources | 0 |
| Answer rate | 0.875 |
| Citation validity | 1.000 |

Satu pertanyaan handover SOP ditolak dengan sopan; ini perilaku yang benar
untuk mode publik karena SOP internal tidak boleh dipakai.

## Temuan utama

1. **Tidak ada kebocoran internal** pada mode public. Tidak ada `KB-*`, `SOP`,
   atau system prompt di `customer_reply`.
2. **Refusal 2/2** untuk pertanyaan yang tidak ada di KB.
3. **Konflik versi 3/3** mendapat judge correctness 5.00 dan citation hit 1.00.
4. **SOP adalah area terlemah** (3.50). Penyebabnya retrieval multi-dokumen:
   pertanyaan force majeure dan Platinum/viral membutuhkan SOP + policy yang
   tidak semuanya masuk context. Jawaban tetap aman, tetapi kurang lengkap.
5. **Pembayaran/refund** punya beberapa kekurangan detail: biaya e-wallet/QRIS,
   potongan admin tiket kereta, dan nuansa biaya admin untuk kegagalan sistem.
6. **Tidak ada hallucination** yang ditandai judge pada 20 sampel.
7. **Latency DeepSeek** ~3 detik (p50) di mode public; jauh lebih cepat dari
   model free OpenRouter.

## Catatan penting

Semua run generation di atas memakai **BM25 fallback** karena kuota embedding
OpenRouter free habis. Hasil ini valid untuk kondisi deploy saat ini, tetapi
belum mengukur hybrid retrieval + generation. Setelah kuota reset/top-up,
jalankan ulang tanpa cache generation (atau hapus cache mode terkait) untuk
membandingkan hybrid vs BM25.

Judge juga berasal dari provider yang sama (DeepSeek). Untuk klaim yang lebih
kuat, validasi 10–20 jawaban secara manual atau gunakan judge dari provider
berbeda.

## Rekomendasi perbaikan

1. Naikkan `CONTEXT_TOP_K` untuk pertanyaan multi-dokumen atau tambahkan query
   expansion (“force majeure”, “Platinum”, “viral”).
2. Perbaiki chunking/prompt untuk tabel biaya refund agar semua metode
   (kartu, VA, e-wallet, QRIS, PayLater, Wallet) ikut terbaca.
3. Tambahkan aturan prompt: untuk pertanyaan biaya, kutip seluruh tabel biaya
   yang relevan, bukan hanya satu baris.
4. Rerun generation eval dengan hybrid retrieval setelah kuota embedding
   tersedia.
5. Validasi manual pada 10 jawaban SOP dan 10 jawaban pembayaran.
