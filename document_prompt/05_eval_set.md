Berdasarkan SEMUA dokumen yang sudah dibuat di atas, buat 50 pasangan
evaluasi dalam format JSON:

{
  "question": "<pertanyaan customer, bahasa natural>",
  "ground_truth_answer": "<jawaban benar & lengkap>",
  "source_doc_ids": ["KB-POL-002", "KB-FAQ-007"],
  "difficulty": "easy|medium|hard",
  "category": "<refund|pembatalan|booking|pembayaran|sop>",
  "notes": "<kenapa sulit, misal: butuh gabung 2 dokumen / ada konflik versi>"
}

Distribusi:
- 20 easy   (jawaban ada di 1 dokumen)
- 20 medium (butuh gabung 2 dokumen)
- 10 hard   (butuh reasoning, konflik versi, atau force majeure)

Pastikan minimal 3 pertanyaan menguji kasus dokumen konflik (versi lama vs baru)
dan 2 pertanyaan yang jawabannya TIDAK ada di KB (uji "I don't know").