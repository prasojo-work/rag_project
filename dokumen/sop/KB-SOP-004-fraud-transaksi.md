---
doc_id: KB-SOP-004
title: SOP Penanganan Indikasi Fraud Transaksi
category: sop
subcategory: fraud
version: 2.0
owner: Tim Risk & Fraud
last_updated: 2025-07-19
---

# SOP Penanganan Indikasi Fraud Transaksi

## 1. Indikator Fraud
Aktivitas mencurigakan meliputi pembayaran dari banyak kartu untuk satu akun, nama pemesan tidak sesuai identitas penumpang, permintaan refund ke rekening pihak ketiga, OTP yang dibagikan, akun diakses dari lokasi tidak wajar, serta pola promo berulang.

## 2. Langkah Penanganan
1. Hentikan sementara pemrosesan pesanan dan tandai tiket `FRAUD-REVIEW` dengan Ticket ID `TK-YYYYMMDD-XXXX`.
2. Jangan menuduh pelanggan. Gunakan bahasa netral dan minta verifikasi identitas.
3. Hubungi pelanggan hanya melalui kontak terdaftar, bukan nomor baru yang diberikan dalam percakapan.
4. Kumpulkan bukti: log login, IP, perangkat, riwayat pembayaran, dan rekaman komunikasi.
5. Eskalasi ke Tim Risk & Fraud maksimal 15 menit melalui kanal internal.
6. Jika ada indikasi *account takeover*, bekukan akun dan minta pelanggan mengganti password.
7. Untuk *chargeback*, siapkan bukti transaksi dan tanggapan maksimal 3 hari kerja.
8. Refund hanya ke instrumen pembayaran asal sesuai KB-POL-002. Permintaan ke rekening lain ditolak.

## 3. Decision Tree
```
Indikasi fraud?
├─ Tidak → proses normal
└─ Ya → hentikan transaksi → verifikasi identitas
   ├─ Identitas valid → aktifkan kembali, pantau
   ├─ Tidak valid → eskalasi Risk & Fraud → bekukan akun
   └─ Chargeback → siapkan bukti → tanggapi ≤3 hari kerja
```

## 4. Contoh Skrip
"Kak [Nama], demi keamanan akun, pesanan [TK-...] kami tahan sementara untuk verifikasi. Mohon konfirmasi melalui email terdaftar dan jangan membagikan OTP kepada siapa pun. Tim kami akan menghubungi maksimal 1x24 jam."

## 5. Batas Wewenang
Agent tidak boleh membuka data kartu lengkap, menyetujui refund ke pihak ketiga, atau menghapus log. Jika transaksi melibatkan PayLater, koordinasikan penangguhan tagihan dengan tim PayLater. Seluruh bukti disimpan minimal 90 hari dan hanya dapat diakses Tim Risk & Fraud.
