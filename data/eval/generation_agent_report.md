# Evaluasi Generation

- Mode: `agent`
- Index: `20261113T130908Z-f7cc4e68`
- Generator: `deepseek` / `deepseek-flash`
- Judge: `deepseek-v4-pro` (n=20, error=0)
- Pertanyaan: 50
- Error: 0
- Tanggal: 2026-11-13
- Retrieval mode: `{'bm25': 50}`

## Ringkasan

| Metrik | Nilai |
|---|---:|
| Answer rate (answerable) | 1.000 |
| Refusal accuracy (expected refusal) | 1.000 |
| Citation validity (answered) | 1.000 |
| Source hit rate | 1.000 |
| Citation hit rate | 1.000 |
| Internal leak | 0 |
| Internal sources (agent mode, wajar) | 47 |
| Latency p50 (ms) | 3842 |
| Latency p95 (ms) | 4922 |
| Token prompt / completion | 118225 / 29809 |

### LLM Judge (1–5)

| Dimensi | Rata-rata |
|---|---:|
| Correctness | 4.70 |
| Completeness | 4.60 |
| Faithfulness | 4.85 |
| Citation support | 4.65 |
| Escalation | 4.85 |
| Hallucination | 0 / 20 |

## Per Difficulty

| Difficulty | n | Answer rate | Refusal acc | Citation valid | Source hit | Judge correctness |
|---|---:|---:|---:|---:|---:|---:|
| easy | 20 | 1.000 | - | 1.000 | 1.000 | 4.80 |
| hard | 10 | 1.000 | 1.000 | 1.000 | 1.000 | 4.50 |
| medium | 20 | 1.000 | - | 1.000 | 1.000 | 5.00 |

## Per Kategori

| Kategori | n | Answer rate | Refusal acc | Citation valid | Judge correctness |
|---|---:|---:|---:|---:|---:|
| booking | 7 | 1.000 | 1.000 | 1.000 | 5.00 |
| pembatalan | 14 | 1.000 | - | 1.000 | 4.50 |
| pembayaran | 6 | 1.000 | 1.000 | 1.000 | 4.50 |
| refund | 15 | 1.000 | - | 1.000 | 5.00 |
| sop | 8 | 1.000 | - | 1.000 | 3.50 |

## Konflik Versi

- Pertanyaan terdeteksi: 3
- Citation hit rate: 1.000
- Judge correctness: 5.00

## Failure Cases

### Tiket pesawat non-refundable saya dibatalkan karena letusan gunung dan bandara ditutup. Apakah saya tetap bisa refund penuh?

- Difficulty/category: `hard` / `pembatalan`
- Alasan: correctness rendah (3/5)
- Judge correctness: 3
- Catatan judge: Jawaban tidak menyebutkan bahwa force majeure dapat membebaskan cancellation fee dan memberikan refund 100% atau credit shell 12 bulan dengan bonus 10% maksimal Rp 500.000 sesuai ground truth. Jawaban hanya menyatakan hasil bergantung pada maskapai, padahal kebijakan TravelKita menjamin refund penuh jika syarat terpenuhi. Tidak ada sitasi eksplisit ke KB-POL-001 §5 karena bagian tersebut tidak tersedia dalam konteks, sehingga jawaban tidak dapat mengutip ketentuan force majeure. Jawaban meminta dokumen yang relevan dan menawarkan eskalasi, tetapi tidak menyebutkan batas waktu keputusan 3 hari kerja setelah dokumen lengkap (hanya 3-7 hari kerja). Tidak ada klaim faktual yang bertentangan dengan konteks, tetapi jawaban kurang lengkap dan kurang tegas dalam menyampaikan hak pelanggan.

```text
Halo, terima kasih sudah menghubungi TravelKita. Kami turut prihatin atas pembatalan penerbangan Anda akibat letusan gunung dan penutupan bandara.

Untuk tiket dengan jenis non-refundable, pengembalian dana tidak otomatis diberikan secara penuh. Namun, pembatalan karena kondisi di luar kendali (force majeure) seperti penutupan bandara dapat kami ajukan sebagai permohonan khusus (waiver) ke maskapai. Hasilnya bergantung pada kebijakan dan persetujuan maskapai, dan bisa berupa refund penuh, refund
```

### Pelanggan Platinum punya penerbangan besok, refund-nya macet 10 hari, dan mengancam viral. Bagaimana urutan penanganannya?

- Difficulty/category: `hard` / `sop`
- Alasan: correctness rendah (3/5)
- Judge correctness: 3
- Catatan judge: Jawaban tidak menyebutkan langkah-langkah spesifik sesuai SOP: tidak ada pembuatan Ticket ID dengan tag P1-PLAT/VIRAL, tidak ada SLA respons awal 2 menit untuk Platinum, tidak ada eskalasi L2 dalam 15 menit, tidak ada pelibatan Manager CX/Communications/Legal dalam 1 jam untuk kasus viral, dan tidak ada pembaruan setiap 4 jam. Jawaban juga tidak menyebutkan bahwa refund 10 hari melewati SLA dan memicu SOP refund tertunda. Namun, jawaban tidak mengarang fakta atau kebijakan yang bertentangan dengan konteks, dan mengarahkan ke kanal privat serta memperingatkan untuk tidak membagikan OTP/PIN/data kartu, yang sesuai dengan SOP. Karena tidak ada sitasi eksplisit, dukungan sitasi rendah.

```text
Halo, kami mohon maaf atas ketidaknyamanan terkait refund yang belum selesai dan penerbangan Anda besok. Kami memahami situasi ini sangat mendesak. Tim kami akan segera menangani sebagai prioritas: mencatat laporan Anda, memverifikasi kode booking dan riwayat refund, serta mengeskalasikan ke tim terkait untuk ditindaklanjuti. Anda akan dihubungi kembali oleh satu agen khusus agar tidak berpindah-pindah, dan kami akan memberi pembaruan berkala sampai kasus ini tuntas. Untuk detail data pribadi, k
```


## Catatan Peningkatan dari Judge

- **Pelanggan Platinum punya penerbangan besok, refund-nya macet 10 hari, dan mengancam viral. Bagaimana urutan penanganannya?**
  - kategori: `sop` · correctness 3/5 · completeness 2/5
  - Jawaban tidak menyebutkan langkah-langkah spesifik sesuai SOP: tidak ada pembuatan Ticket ID dengan tag P1-PLAT/VIRAL, tidak ada SLA respons awal 2 menit untuk Platinum, tidak ada eskalasi L2 dalam 15 menit, tidak ada pelibatan Manager CX/Communications/Legal dalam 1 jam untuk kasus viral, dan tidak ada pembaruan setiap 4 jam. Jawaban juga tidak menyebutkan bahwa refund 10 hari melewati SLA dan memicu SOP refund tertunda. Namun, jawaban tidak mengarang fakta atau kebijakan yang bertentangan dengan konteks, dan mengarahkan ke kanal privat serta memperingatkan untuk tidak membagikan OTP/PIN/data kartu, yang sesuai dengan SOP. Karena tidak ada sitasi eksplisit, dukungan sitasi rendah.
- **Tiket pesawat non-refundable saya dibatalkan karena letusan gunung dan bandara ditutup. Apakah saya tetap bisa refund penuh?**
  - kategori: `pembatalan` · correctness 3/5 · completeness 3/5
  - Jawaban tidak menyebutkan bahwa force majeure dapat membebaskan cancellation fee dan memberikan refund 100% atau credit shell 12 bulan dengan bonus 10% maksimal Rp 500.000 sesuai ground truth. Jawaban hanya menyatakan hasil bergantung pada maskapai, padahal kebijakan TravelKita menjamin refund penuh jika syarat terpenuhi. Tidak ada sitasi eksplisit ke KB-POL-001 §5 karena bagian tersebut tidak tersedia dalam konteks, sehingga jawaban tidak dapat mengutip ketentuan force majeure. Jawaban meminta dokumen yang relevan dan menawarkan eskalasi, tetapi tidak menyebutkan batas waktu keputusan 3 hari kerja setelah dokumen lengkap (hanya 3-7 hari kerja). Tidak ada klaim faktual yang bertentangan dengan konteks, tetapi jawaban kurang lengkap dan kurang tegas dalam menyampaikan hak pelanggan.
- **Saya bayar pakai Virtual Account, saldo terpotong tetapi pesanan gagal. Bagaimana proses refundnya?**
  - kategori: `pembayaran` · correctness 4/5 · completeness 4/5
  - Jawaban mencakup langkah-langkah utama: cek status, tunggu 1x24 jam, hindari pembayaran ganda, cek mutasi, dan hubungi CS dengan bukti. Namun, ada ketidaktepatan pada biaya admin: jawaban menyebut 'biaya admin (jika ada) mengikuti kebijakan yang berlaku' tanpa menyebutkan angka spesifik, sementara ground truth menyatakan tidak dikenakan biaya admin karena kegagalan sistem. Konteks yang diberikan memiliki konflik antara KB-FAQ-003 (bebas biaya) dan KB-POL-002 (Rp 25.000), dan catatan internal menginstruksikan untuk tidak menjanjikan bebas biaya. Jawaban tidak menyebutkan angka, sehingga tidak salah secara eksplisit, tetapi kurang lengkap. Selain itu, jawaban tidak menyebutkan bahwa refund VA/transfer bank diproses 3–7 hari kerja (sudah disebutkan) dan tidak menyebutkan eskalasi ke L2 secara spesifik, hanya 'tim lanjutan'. Secara keseluruhan, jawaban akurat dan sesuai konteks, tanpa halusinasi.
- **Saya curiga akun saya diambil alih dan ada permintaan refund ke rekening orang lain. Apa yang harus dilakukan?**
  - kategori: `sop` · correctness 4/5 · completeness 4/5
  - Jawaban sudah benar dan sesuai SOP, namun kurang lengkap: tidak menyebutkan pembekuan akun secara eksplisit sebagai langkah yang akan dilakukan (hanya 'dapat dibekukan bila diperlukan'), tidak menyebutkan pengumpulan bukti log login/IP/perangkat, dan tidak menyebutkan eskalasi maksimal 15 menit. Tidak ada halusinasi.
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
