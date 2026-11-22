# Evaluasi Retrieval

- Index version: `20261113T130908Z-f7cc4e68`
- Embedding: `nvidia/nemotron-3.5-embed-8b`
- Pertanyaan: 50
- Top-k: 10 | as-of: 2026-11-22

## Ringkasan

| Mode | Recall@5 | Hit@5 | Precision@5 | MRR@10 | nDCG@5 | Answerable |
|---|---:|---:|---:|---:|---:|---:|
| dense | 0.955 | 1.000 | 0.358 | 0.990 | 0.937 | 48 |
| bm25 | 0.941 | 1.000 | 0.304 | 0.929 | 0.886 | 48 |
| hybrid | 0.976 | 1.000 | 0.338 | 0.958 | 0.925 | 48 |

## Per Difficulty

| Mode | Difficulty | Recall@5 | Hit@5 | MRR@10 | nDCG@5 | n |
|---|---|---:|---:|---:|---:|---:|
| dense | easy | 1.000 | 1.000 | 1.000 | 1.000 | 20 |
| dense | hard | 0.917 | 1.000 | 1.000 | 0.897 | 10 |
| dense | medium | 0.925 | 1.000 | 0.975 | 0.891 | 20 |
| bm25 | easy | 1.000 | 1.000 | 0.942 | 0.957 | 20 |
| bm25 | hard | 0.833 | 1.000 | 0.875 | 0.781 | 10 |
| bm25 | medium | 0.925 | 1.000 | 0.938 | 0.858 | 20 |
| hybrid | easy | 1.000 | 1.000 | 0.975 | 0.982 | 20 |
| hybrid | hard | 0.917 | 1.000 | 0.938 | 0.858 | 10 |
| hybrid | medium | 0.975 | 1.000 | 0.950 | 0.895 | 20 |

## Catatan

- Metrik dihitung pada level dokumen (dedupe chunk per doc_id).
- Pertanyaan tanpa `source_doc_ids` tidak dihitung dalam metrik retrieval;
  pertanyaan tersebut dipakai untuk evaluasi refusal di fase generation.
- Jika provider `hash`, angka ini hanya smoke test pipeline.
