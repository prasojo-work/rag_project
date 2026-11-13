# Fase 3 — UI Customer-Facing (Jinja + HTMX)

## Tujuan

Menyediakan antarmuka **untuk pelanggan TravelKita**, bukan dashboard teknis
RAG. Pengguna hanya melihat satu pengalaman: chat customer service.

Prinsip tampilan:

- Menu hanya **Chat**.
- Tidak ada statistik retrieval, skor, model, latency, confidence, atau debug.
- Tidak ada panel internal notes/SOP.
- Default UI memakai mode **public**, sehingga SOP internal tidak dipakai.
- Sumber jawaban ditampilkan sebagai judul dokumen yang ramah, bukan doc_id.

## Stack

- **Jinja2** server-side rendering.
- **HTMX 2.0.4** untuk submit chat, swap partial, dan drawer sumber.
- **Vanilla JS** untuk theme toggle, copy, auto-scroll, dialog.
- **CSS manual** dengan light/dark theme dan responsive.
- HTMX di-vendor di `static/js/htmx.min.js` (bukan CDN).

Tidak ada Node, tidak ada `dist/`, tidak ada build frontend.

## Route publik

| Method | Path | Fungsi |
|---|---|---|
| GET | `/` | Halaman chat pelanggan |
| POST | `/chat` | HTMX partial jawaban |
| GET | `/partials/documents/{doc_id}` | Drawer sumber (hanya dokumen publik) |
| POST | `/feedback` | Feedback pelanggan (log-only) |

API JSON di `/api/v1/*` tetap tersedia untuk integrasi/evaluasi.

## Route internal (tidak ditautkan)

Untuk review portfolio:

| Path | Isi |
|---|---|
| `/internal/eval` | Dashboard retrieval |
| `/internal/documents` | Daftar dokumen |
| `/internal/documents/{doc_id}` | Detail dokumen + chunk |
| `/internal/about` | Arsitektur, keputusan, batasan |

Route ini tidak muncul di navigasi. UI pelanggan tidak menampilkan data teknis.

## UX chat

- Pertanyaan dikirim via HTMX dan di-append ke conversation.
- Loading indicator muncul selama retrieval + generation.
- Jawaban hanya menampilkan **balasan pelanggan**.
- Chip "Sumber" menampilkan judul dokumen (mis. “Kebijakan Refund Dana”),
  bukan `KB-POL-002`.
- Drawer sumber hanya menampilkan judul, section, dan teks; tanpa versi,
  audience, status, atau skor retrieval.
- Jika jawaban tidak answerable, pelanggan menerima permintaan maaf + arahan
  ke Customer Care.
- Jika sitasi tidak valid, UI menampilkan pesan aman, bukan jawaban mentah.
- Feedback thumbs up/down tetap tersedia.
- Tidak ada polling kesehatan otomatis (menghindari replica terbangun dan
  menghabiskan kuota compute FastAPI Cloud).

## Suggested questions

Contoh pertanyaan disesuaikan untuk pelanggan:

- Batalkan tiket pesawat.
- Refund GoPay.
- Reschedule hotel.
- E-tiket belum masuk email.
- Cara memakai voucher.

## Fallback BM25

OpenRouter free daily quota bisa habis; embedding query juga dihitung. Jika
embedding gagal karena 429, `ChatService` otomatis memakai BM25 dan tetap
memanggil LLM. Di UI pelanggan, detail teknis fallback tidak ditampilkan;
respons tetap berupa jawaban biasa.

## Hasil uji

- **59 test passed** (termasuk test Phase 4).
- Test UI mencakup: halaman chat, partial HTMX, error injection, drawer sumber,
  feedback, dan halaman internal.
- Smoke test nyata DeepSeek + BM25 fallback: jawaban pelanggan yang ramah,
  sitasi judul dokumen, **~3,3 detik**.

## Batasan

- Belum ada streaming token.
- Percakapan belum disimpan di server; setiap pertanyaan independen.
- Belum ada autentikasi. Data sintetis; drawer sumber dibatasi ke dokumen
  publik.
- Feedback hanya masuk log.
- Belum ada upload dokumen/admin.
- Validasi visual browser belum dilakukan (tidak ada browser headless di
  environment pengembangan); HTML dirender lewat TestClient.
