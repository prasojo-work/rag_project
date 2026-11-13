---
doc_id: KB-SOP-001
title: SOP Penanganan Komplain Refund Tertunda (>7 Hari Kerja)
category: sop
subcategory: refund_processing
version: 2.2
owner: Tim Refund & Settlement
last_updated: 2025-07-17
---

# SOP Penanganan Komplain Refund Tertunda (>7 Hari Kerja)

## 1. Tujuan dan Pemicu
SOP ini dipakai ketika status refund tidak berubah setelah 7 hari kerja atau melewati SLA metode pembayaran pada KB-POL-002. Tujuannya memastikan setiap keterlambatan memiliki pemilik, penyebab, dan tanggal penyelesaian yang jelas.

## 2. Langkah Penanganan
1. Verifikasi Ticket ID `TK-YYYYMMDD-XXXX`, kode booking, dan identitas pemesan.
2. Tentukan SLA metode: e-wallet 1–3 hari kerja, VA/transfer bank dan QRIS 3–7, kartu kredit/debit maksimal 7, PayLater 3–5.
3. Buka dashboard refund dan catat status, tanggal pengajuan, nominal, serta nomor referensi.
4. Jika dokumen kurang, hubungi pelanggan maksimal 1x24 jam dan jelaskan dokumen yang diperlukan.
5. Jika menunggu mitra (maskapai/hotel/KAI), kirim follow-up melalui kanal resmi dan catat responsnya.
6. Jika status `DANA DIKIRIM`, minta bukti transfer atau nomor UTR, lalu ajukan *trace* ke bank/e-wallet.
7. Jika transfer gagal karena rekening salah, verifikasi ulang nama pemesan. Refund hanya ke instrumen asal, bukan rekening pihak ketiga.
8. Perbarui tiket setiap 3 hari kerja. Jika total melewati 7 hari kerja, eskalasi ke L2 dengan kronologi lengkap.

## 3. Decision Tree
```
Refund melewati SLA metode?
├─ Tidak → pantau, update pelanggan
└─ Ya → cek status internal
   ├─ Dokumen kurang → minta dokumen (1x24 jam)
   ├─ Menunggu mitra → follow-up (maks 3 hari kerja)
   ├─ Dana sudah dikirim → trace bank/e-wallet
   │  └─ Gagal transfer → verifikasi rekening, proses ulang
   └─ >7 hari kerja → eskalasi L2
```

## 4. Contoh Skrip Komunikasi
"Kak [Nama], kami sudah mengecek refund untuk Ticket ID [TK-...]. Status saat ini [DIPROSES] dan sedang menunggu konfirmasi [mitra]. Estimasi penyelesaian [tanggal] sesuai SLA. Kami akan mengabari lagi maksimal 3 hari kerja ke depan. Mohon maaf atas ketidaknyamanannya."

## 5. Larangan
Jangan menjanjikan tanggal di luar SLA, meminta data kartu lengkap, atau mengarahkan refund ke rekening orang lain.
