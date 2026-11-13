---
doc_id: KB-SOP-005
title: SOP Handover Shift Customer Service
category: sop
subcategory: handling
version: 1.3
owner: Tim Customer Experience
last_updated: 2025-07-19
---

# SOP Handover Shift Customer Service

## 1. Tujuan
Handover memastikan tidak ada tiket yang hilang, terlewat SLA, atau ditangani ganda saat pergantian shift. Shift CS berjalan 07.00–22.00 WIB, dibagi menjadi 07.00–12.00, 12.00–17.00, dan 17.00–22.00.

## 2. Yang Wajib Di-log
1. Tiket P1 dan Platinum yang masih terbuka, beserta status dan langkah berikutnya.
2. Refund yang melewati SLA atau menunggu dokumen pelanggan.
3. Kasus viral dan eskalasi L2/L3, termasuk nama approver.
4. Indikasi fraud atau akun yang dibekukan.
5. Kendala sistem: gangguan pembayaran, e-tiket, OTP, atau integrasi mitra.
6. Janji kepada pelanggan yang belum ditepati, lengkap dengan tenggat waktunya.
7. Perubahan kebijakan atau promo yang berlaku pada shift berikutnya.

## 3. Format Serah Terima
```
SHIFT: [Pagi/Siang/Malam] | TANGGAL: [YYYY-MM-DD]
AGENT: [Nama] → [Nama]
TIKET TERBUKA:
- TK-... | Tier | Status | Next action | Deadline
REFUND OVERDUE:
- TK-... | Metode | Hari ke- | Pending pada
ESKALASI: ...
FRAUD: ...
SISTEM: ...
CATATAN: ...
```

## 4. Langkah Handover
1. Siapkan ringkasan 15 menit sebelum shift berakhir.
2. Kirim ke kanal `#cs-handover` dan sistem tiket.
3. Lakukan *warm transfer* untuk P1 yang belum selesai; jangan hanya meninggalkan catatan.
4. Agent penerima mengonfirmasi dengan emoji atau balasan "ACK" dan menanyakan hal yang belum jelas.
5. Update status tiket dan pastikan tidak ada duplikasi.

## 5. Decision Tree
```
P1 masih terbuka?
├─ Ya → warm transfer + telepon/VC → ACK
└─ Tidak → kirim log tertulis → ACK
   └─ Ada item belum jelas? → tanyakan sebelum shift lama berakhir
```

## 6. Contoh Skrip
"Handover ke [Nama]: ada 2 P1, satu refund overdue H+9 menunggu trace bank, satu Platinum menunggu konfirmasi jadwal ulang. Log lengkap sudah di #cs-handover. Tolong ACK dan hubungi pelanggan sebelum pukul 18.00."
