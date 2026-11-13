# Evaluasi Generation

- Mode: `public`
- Index: `20261113T130908Z-f7cc4e68`
- Generator: `deepseek` / `deepseek-flash`
- Judge: `none` (n=0, error=0)
- Pertanyaan: 8
- Error: 0
- Tanggal: 2026-11-13
- Retrieval mode: `{'bm25': 8}`

## Ringkasan

| Metrik | Nilai |
|---|---:|
| Answer rate (answerable) | 0.875 |
| Refusal accuracy (expected refusal) | - |
| Citation validity (answered) | 1.000 |
| Source hit rate | 0.875 |
| Citation hit rate | 1.000 |
| Internal leak | 0 |
| Internal sources (public mode harus 0) | 0 |
| Latency p50 (ms) | 2986 |
| Latency p95 (ms) | 4096 |
| Token prompt / completion | 20698 / 3456 |

### LLM Judge (1–5)

| Dimensi | Rata-rata |
|---|---:|
| Correctness | - |
| Completeness | - |
| Faithfulness | - |
| Citation support | - |
| Escalation | - |
| Hallucination | 0 / 0 |

## Per Difficulty

| Difficulty | n | Answer rate | Refusal acc | Citation valid | Source hit | Judge correctness |
|---|---:|---:|---:|---:|---:|---:|
| easy | 3 | 0.667 | - | 1.000 | 0.667 | - |
| hard | 2 | 1.000 | - | 1.000 | 1.000 | - |
| medium | 3 | 1.000 | - | 1.000 | 1.000 | - |

## Per Kategori

| Kategori | n | Answer rate | Refusal acc | Citation valid | Judge correctness |
|---|---:|---:|---:|---:|---:|
| sop | 8 | 0.875 | - | 1.000 | - |

## Konflik Versi

- Pertanyaan terdeteksi: 0
- Citation hit rate: -
- Judge correctness: -

## Failure Cases

### Apa saja yang harus dicatat saat handover shift CS dan bagaimana formatnya?

- Difficulty/category: `easy` / `sop`
- Alasan: tidak menjawab padahal answerable
- Judge correctness: None
- Catatan judge: -

```text
Mohon maaf, untuk saat ini saya belum memiliki informasi yang cukup untuk menjawab pertanyaan tersebut. Agar tidak memberikan informasi yang keliru, saya sarankan Anda menghubungi Customer Service TravelKita melalui live chat, email, WhatsApp, atau telepon pada pukul 07.00–22.00 WIB. Tim kami akan dengan senang hati membantu Anda. Terima kasih atas pengertiannya.
```


## Catatan Peningkatan dari Judge

Tidak ada catatan peningkatan pada subset judge.

## Catatan Metodologi

- Metrik deterministik dihitung untuk semua pertanyaan.
- LLM judge dijalankan pada subset stratifikasi (unanswerable + hard lebih dulu).
- Generator dan judge sama-sama memakai DeepSeek; ini self-judge bias yang perlu
  disadari. Untuk klaim lebih kuat, validasi manual subset atau pakai model judge
  dari provider berbeda.
- Mode `agent` dipakai untuk mengukur kualitas KB penuh. Untuk UI pelanggan
  (mode `public`), jalankan subset safety terpisah.
