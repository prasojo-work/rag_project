# Evaluasi Generation

- Mode: `public`
- Index: `20261113T130908Z-f7cc4e68`
- Generator: `deepseek` / `deepseek-flash`
- Judge: `deepseek-v4-pro` (n=20, error=0)
- Pertanyaan: 38
- Error: 0
- Tanggal: 2026-11-13
- Retrieval mode: `{'bm25': 38}`

## Ringkasan

| Metrik | Nilai |
|---|---:|
| Answer rate (answerable) | 1.000 |
| Refusal accuracy (expected refusal) | - |
| Citation validity (answered) | 1.000 |
| Source hit rate | 1.000 |
| Citation hit rate | 1.000 |
| Internal leak | 0 |
| Internal sources (public mode harus 0) | 0 |
| Latency p50 (ms) | 2968 |
| Latency p95 (ms) | 3792 |
| Token prompt / completion | 99077 / 17061 |

### LLM Judge (1–5)

| Dimensi | Rata-rata |
|---|---:|
| Correctness | 4.85 |
| Completeness | 4.80 |
| Faithfulness | 4.95 |
| Citation support | 4.85 |
| Escalation | 4.95 |
| Hallucination | 0 / 20 |

## Per Difficulty

| Difficulty | n | Answer rate | Refusal acc | Citation valid | Source hit | Judge correctness |
|---|---:|---:|---:|---:|---:|---:|
| easy | 19 | 1.000 | - | 1.000 | 1.000 | 4.78 |
| hard | 5 | 1.000 | - | 1.000 | 1.000 | 5.00 |
| medium | 14 | 1.000 | - | 1.000 | 1.000 | 4.83 |

## Per Kategori

| Kategori | n | Answer rate | Refusal acc | Citation valid | Judge correctness |
|---|---:|---:|---:|---:|---:|
| booking | 6 | 1.000 | - | 1.000 | 5.00 |
| pembatalan | 12 | 1.000 | - | 1.000 | 5.00 |
| pembayaran | 5 | 1.000 | - | 1.000 | 4.00 |
| refund | 13 | 1.000 | - | 1.000 | 4.82 |
| sop | 2 | 1.000 | - | 1.000 | - |

## Konflik Versi

- Pertanyaan terdeteksi: 3
- Citation hit rate: 1.000
- Judge correctness: 5.00

## Failure Cases

Tidak ada failure case pada kriteria yang diperiksa.

## Catatan Peningkatan dari Judge

- **Saya bayar pakai Virtual Account, saldo terpotong tetapi pesanan gagal. Bagaimana proses refundnya?**
  - kategori: `pembayaran` · correctness 4/5 · completeness 4/5
  - Jawaban mencakup langkah-langkah utama: cek status, tunggu 1x24 jam, hindari pembayaran ganda, cek mutasi, dan hubungi CS dengan bukti. Namun, ada ketidaktepatan pada biaya admin: jawaban menyebut 'biaya admin (jika ada) mengikuti kebijakan yang berlaku' tanpa menyebutkan angka spesifik, sementara ground truth menyatakan tidak dikenakan biaya admin karena kegagalan sistem. Konteks yang diberikan memiliki konflik antara KB-FAQ-003 (bebas biaya) dan KB-POL-002 (Rp 25.000), dan catatan internal menginstruksikan untuk tidak menjanjikan bebas biaya. Jawaban tidak menyebutkan angka, sehingga tidak salah secara eksplisit, tetapi kurang lengkap. Selain itu, jawaban tidak menyebutkan bahwa refund VA/transfer bank diproses 3–7 hari kerja (sudah disebutkan) dan tidak menyebutkan eskalasi ke L2 secara spesifik, hanya 'tim lanjutan'. Secara keseluruhan, jawaban akurat dan sesuai konteks, tanpa halusinasi.
- **Berapa biaya administrasi refund dan kapan biaya itu dibebaskan?**
  - kategori: `refund` · correctness 4/5 · completeness 4/5
  - Jawaban benar menyebutkan biaya admin Rp 25.000 untuk tiket pesawat dan pembebasan untuk pembatalan oleh maskapai/hotel/KAI, force majeure, kesalahan sistem, dan Platinum, serta tidak dipotong dua kali. Namun, tidak menyebutkan biaya admin untuk metode e-wallet (Rp 10.000), QRIS (Rp 15.000), dan PayLater (gratis) yang ada di ground truth. Tidak ada klaim yang tidak didukung konteks. Sitasi tidak diberikan secara eksplisit, tetapi klaim sesuai dengan konteks. Keputusan untuk menawarkan eskalasi tepat.
- **Saya batalkan tiket kereta Rp 450.000 pada H-6. Berapa refund bersihnya?**
  - kategori: `refund` · correctness 4/5 · completeness 4/5
  - Jawaban benar menyebut refund 75% untuk H-6 dan menghitung Rp 337.500. Namun tidak menyebut potensi biaya admin Rp 25.000 yang ada di ground truth, sehingga kurang lengkap. Tidak ada klaim yang tidak didukung konteks. Keputusan untuk menyarankan verifikasi rincian dan menghubungi CS jika perlu sudah tepat, tetapi tidak menawarkan eskalasi langsung ke tim refund untuk angka pasti.
- **Hotel saya overbooking dan tidak bisa memberi kamar. Apa hak saya?**
  - kategori: `pembatalan` · correctness 5/5 · completeness 4/5
  - Jawaban mencakup semua poin utama kebijakan overbooking: akomodasi pengganti setara/lebih tinggi, transportasi maksimal Rp300.000, kompensasi 20% selisih, refund 100% dalam 3 hari kerja jika menolak relokasi. Tidak ada angka atau kebijakan yang salah. Namun, jawaban tidak menyebutkan bahwa insiden dicatat sebagai OVB dan dilaporkan ke Account Manager Akomodasi dalam 1x24 jam, serta tidak menyebutkan bahwa overbooking termasuk prioritas P1 dengan respons awal 5 menit. Kedua informasi ini ada di ground truth dan konteks, sehingga completeness sedikit kurang. Tidak ada halusinasi; semua klaim didukung konteks. Sitasi tidak diberikan secara eksplisit, tetapi jawaban konsisten dengan KB-POL-003. Keputusan untuk menawarkan bantuan dan meminta Ticket ID sudah tepat, tidak perlu eskalasi pada tahap ini.

## Catatan Metodologi

- Metrik deterministik dihitung untuk semua pertanyaan.
- LLM judge dijalankan pada subset stratifikasi (unanswerable + hard lebih dulu).
- Generator dan judge sama-sama memakai DeepSeek; ini self-judge bias yang perlu
  disadari. Untuk klaim lebih kuat, validasi manual subset atau pakai model judge
  dari provider berbeda.
- Mode `agent` dipakai untuk mengukur kualitas KB penuh. Untuk UI pelanggan
  (mode `public`), jalankan subset safety terpisah.
