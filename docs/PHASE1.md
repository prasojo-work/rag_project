# Fase 1 — Data Pipeline & Retrieval Baseline

Dokumen ini mencatat keputusan dan batasan implementasi Fase 1.

## Tujuan

1. Memastikan metadata dokumen konsisten sebelum di-index.
2. Memecah dokumen tanpa merusak tabel atau langkah prosedural.
3. Membuat index offline yang kecil, deterministik, dan cepat dimuat.
4. Menyediakan baseline retrieval dense/BM25/hybrid yang bisa dievaluasi.

## 1. Audit data

`scripts/audit_data.py` memeriksa:

- Front matter YAML valid.
- Field wajib: `doc_id`, `title`, `category`.
- Duplikasi `doc_id` pada dokumen aktif.
- Versi aktif lebih lama daripada versi superseded.
- `effective_date` eksplisit, fallback ke `last_updated`.
- Referensi `KB-XXX-NNN` yang tidak ditemukan.
- Body kosong.

Hasil pada corpus saat ini:

| Metrik | Nilai |
|---|---:|
| Total file | 31 |
| Dokumen aktif | 25 |
| Superseded | 3 |
| Noise | 3 |
| Error | 0 |
| Warning | 15 |

15 warning berasal dari FAQ tanpa field `version`. Ini bukan error karena FAQ
diperlakukan sebagai dokumen versi tunggal; tanggal berlaku diturunkan dari
`last_updated`.

Dokumen `uji_robustness/konflik` dan `uji_robustness/noise` tidak masuk index
produksi. Keduanya tetap diaudit agar konflik versi dan noise terdeteksi.

## 2. Chunking

Strategi:

- H1 dianggap judul dokumen; section dimulai dari H2/H3.
- FAQ (hanya H1 + body) menjadi satu chunk `Umum`.
- Setiap section policy/SOP menjadi chunk sendiri.
- **Tabel dideteksi dan tidak dipotong di tengah baris.** Jika tabel panjang,
  header + separator diulang di setiap potongan.
- Prose panjang dipecah per paragraf/kalimat dengan batas ~500 token estimasi.
- Metadata konteks (doc_id, judul, versi, tanggal berlaku, audience, section,
  tipe) disiapkan untuk embedding, sementara teks asli tetap dipakai untuk
  sitasi.

Hasil pada corpus saat ini: **85 chunk** untuk 25 dokumen, rata-rata ~117 token.
Distribusi tipe chunk:

| Tipe | Jumlah |
|---|---:|
| prose | 45 |
| steps | 15 |
| faq | 15 |
| table | 9 |
| changelog | 1 |

Chunk kecil (30–50 token) dipertahankan karena merupakan section bermakna
(mis. "Larangan", "Catatan"). Untuk corpus sekecil ini, granularitas section
lebih berguna daripada menggabungkan section yang berbeda.

## 3. Embedding

- Dokumen di-embed **offline** oleh `build_index.py`.
- Runtime nanti hanya meng-embed query.
- Model default: `nvidia/nemotron-3.5-embed-8b:free` (multilingual, 32k context).
  Model `...-1b:free` diuji dan gagal untuk batch >1 (HTTP 502), jadi 8B dipakai.
- Vektor disimpan sebagai `float32`, L2-normalized, di `embeddings.npy`.
- `manifest.json` mencatat model, dimensi, versi chunker, hash dokumen, dan
  `index_version`.
- Provider `hash` hanya untuk smoke test; manifest menandainya
  `embedding_synthetic: true`.

OpenRouter free tier dengan <10 kredit memiliki batas sekitar 20 RPM / 50
request/hari. Build index 85 chunk dengan batch 16 hanya membutuhkan ~6
request. Evaluasi 50 pertanyaan juga di-batch, bukan 50 request terpisah.

## 4. Index & retrieval

`app/rag/index.py`:

- Memuat `chunks.jsonl`, `embeddings.npy`, dan `manifest.json`.
- Menormalisasi ulang vektor (idempoten).
- Dense: matrix-vector dot product.
- BM25: `rank_bm25.BM25Okapi` dengan tokenizer sederhana Bahasa Indonesia.
- Hybrid: RRF `1/(k + rank)` dengan `k=60`.
- Filter: `status`, `audience`, `effective_date <= as_of`.
- BM25 hanya memasukkan skor > 0 agar dokumen tanpa kecocokan tidak
  mengotori fusion.

## 5. Evaluasi

`scripts/evaluate_retrieval.py` menghitung pada level dokumen:

- Recall@5
- Hit@5
- Precision@5
- MRR@10
- nDCG@5

Pertanyaan tanpa `source_doc_ids` (2 pertanyaan) tidak dihitung dalam metrik
retrieval; pertanyaan itu disiapkan untuk evaluasi refusal di fase generation.

Baseline nyata (embedding 8B, 4096 dimensi, 48 pertanyaan answerable):

| Mode | Recall@5 | Hit@5 | Precision@5 | MRR@10 | nDCG@5 |
|---|---:|---:|---:|---:|---:|
| Dense | 0.955 | 1.000 | 0.358 | 0.990 | 0.937 |
| BM25 | 0.941 | 1.000 | 0.304 | 0.929 | 0.886 |
| Hybrid RRF | 0.976 | 1.000 | 0.338 | 0.958 | 0.925 |

Per difficulty (Recall@5):

| Mode | Easy | Medium | Hard |
|---|---:|---:|---:|
| Dense | 1.000 | 0.925 | 0.917 |
| BM25 | 1.000 | 0.925 | 0.833 |
| Hybrid | 1.000 | 0.975 | 0.917 |

Interpretasi:

- Hybrid paling tinggi Recall@5; dense paling tinggi MRR/nDCG.
- BM25 turun di pertanyaan hard, terutama yang butuh lebih dari satu dokumen.
- Sisa miss didominasi pertanyaan multi-dokumen (overbooking, force majeure,
  kasus viral). Ini bisa diperbaiki dengan top-k context lebih besar, query
  expansion, atau rerank — bukan dengan mengganti vector store.

Output:

- `data/eval/retrieval_results.json` — detail per pertanyaan.
- `data/eval/retrieval_report.md` — ringkasan per mode/difficulty.

## 6. Batasan yang diketahui

- Corpus sangat kecil; hasil retrieval bisa tinggi hanya karena istilah saling
  tumpang tindih. Jangan mengklaim generalisasi dari 50 pertanyaan.
- Baseline memakai satu model embedding free; model lain bisa berbeda.
  `nemotron-3.5-embed-1b:free` gagal untuk batch >1 (HTTP 502).
- Index nyata ada di `data/index/` (85 chunk, 4096 dimensi, ~1,4 MB).
- Belum ada evaluasi generation, faithfulness, sitasi, atau refusal.
- Belum ada evaluasi index yang menyertakan dokumen noise/konflik. Eksperimen
  robustness dapat dilakukan dengan `build_index.py --include-fixtures`.
- Chunk ID menggunakan nomor urut bagian; perubahan urutan section dapat
  mengubah ID. Ini tidak masalah untuk index yang dibangun ulang, tetapi perlu
  diingat untuk cache/eval.
