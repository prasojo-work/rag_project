Buat 6 dokumen tambahan untuk menguji robustness sistem RAG:

A. 3 dokumen "noise" — relevan secara topik tapi tidak boleh jadi jawaban utama:
   - Memo internal rapat divisi marketing (menyebut refund sekilas).
   - Newsletter promo bulanan (menyebut kata "pembatalan" dalam konteks promo).
   - Dokumen onboarding karyawan baru (menyebut SOP secara umum).

B. 3 dokumen dengan INFORMASI BERTENTANGAN (versi lama vs baru):
   - KB-POL-002 versi 1.0 (2023) — refund 14 hari kerja.
   - KB-POL-002 versi 2.1 (2025) — refund 7 hari kerja. <- ini yang benar.
   - Dokumen FAQ lama yang masih menyebut "14 hari kerja".
   Beri metadata version & last_updated yang jelas agar sistem bisa
   memprioritaskan versi terbaru.

Setiap dokumen tetap pakai front-matter YAML standar.