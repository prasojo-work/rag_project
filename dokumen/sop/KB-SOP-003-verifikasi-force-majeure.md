---
doc_id: KB-SOP-003
title: SOP Verifikasi Klaim Force Majeure
category: sop
subcategory: handling
version: 1.6
owner: Tim Tiket Pesawat & Airline Relations
last_updated: 2025-07-18
---

# SOP Verifikasi Klaim Force Majeure

## 1. Ruang Lingkup
SOP ini digunakan untuk klaim pembatalan atau perubahan akibat bencana alam, pemogokan maskapai, penutupan bandara, kerusuhan, atau kebijakan pemerintah. Ketentuan kompensasi mengacu pada KB-POL-001 §5 dan KB-POL-002 §4.

## 2. Dokumen Wajib
1. Bukti pemesanan dan Ticket ID `TK-YYYYMMDD-XXXX`.
2. Surat pembatalan/perubahan resmi dari maskapai, hotel, atau KAI.
3. Bukti peristiwa: rilis BMKG/BNPB, pengumuman otoritas bandara, atau pemberitaan media kredibel.
4. Identitas pemesan dan bukti pembayaran.
5. Surat keterangan medis bila klaim terkait kondisi kesehatan.

## 3. Langkah Verifikasi
1. Cocokkan tanggal, rute, dan lokasi peristiwa dengan jadwal pemesanan.
2. Pastikan peristiwa terjadi sebelum atau pada saat keberangkatan dan bukan akibat kelalaian pelanggan.
3. Klasifikasikan: `FULL_WAIVER`, `PARTIAL_WAIVER`, atau `REJECT`.
4. Untuk `FULL_WAIVER`, refund 100% tanpa biaya admin atau *credit shell* +10% (maksimal Rp 500.000).
5. Untuk `PARTIAL_WAIVER`, refund komponen yang tidak terpakai dan jelaskan potongannya tertulis.
6. Minta persetujuan supervisor untuk nilai di atas Rp 5.000.000.
7. Perbarui tiket dan kirim keputusan maksimal 3 hari kerja setelah dokumen lengkap.

## 4. Decision Tree
```
Dokumen lengkap?
├─ Tidak → minta kelengkapan (1x24 jam)
└─ Ya → peristiwa valid & overlap jadwal?
   ├─ Tidak → REJECT + alasan tertulis
   └─ Ya → nilai klaim > Rp 5 juta?
      ├─ Ya → approval supervisor → proses refund
      └─ Tidak → proses refund/credit shell
```

## 5. Contoh Skrip
"Kak [Nama], klaim force majeure untuk Ticket ID [TK-...] sudah kami verifikasi berdasarkan surat maskapai dan informasi BMKG. Pembatalan memenuhi ketentuan KB-POL-001, sehingga refund diproses 100% tanpa biaya admin. Estimasi dana masuk [tanggal] sesuai KB-POL-002."

## 6. Catatan
Jangan menyetujui klaim tanpa bukti resmi. Simpan seluruh dokumen pada tiket minimal 5 tahun untuk keperluan audit.
