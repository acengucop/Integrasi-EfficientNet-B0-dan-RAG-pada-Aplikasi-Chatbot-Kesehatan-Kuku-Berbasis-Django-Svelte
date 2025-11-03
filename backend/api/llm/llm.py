# api/llm/llm.py
from __future__ import annotations
import os, json, logging
from typing import List, Dict, Tuple, Optional
from django.conf import settings

from ..rag import retrieve_multi_smart  # naik satu level krn sekarang di dalam paket api/llm/

from .llm_utils import (
    _extract_text_safe,
    _client,
    _format_context_dual,
    _detect_intent,
    _has_user_question,
    _percent_id,
    _normalize_sections,
    _is_nail_domain,        # <— NEW: deteksi relevansi domain kuku
)
from .prompts import SYSTEM_PROMPT

log = logging.getLogger(__name__)

def explain_prediction(pred_label: str, conf: float, probs: dict, user_prompt: str) -> str:
    """
    Penjelasan berbasis RAG (lokal + literatur akademik) + Gemini.
    - Struktur output FIX (heading markdown).
    - Sitasi [Lx]/[Sx] sesuai konteks yang disediakan retriever.
    - Ambang ketidakpastian: 0.70 (ditekankan di Ringkasan & Saran bila < 0.70).
    - Deteksi relevansi prompt: jika di luar domain kuku → beri catatan mismatch di Ringkasan & abaikan bagian tak relevan.
    """
    # 1) Retrieval
    base_query = (user_prompt or "Jelaskan secara non-diagnostik") + f" | label: {pred_label}"
    passages = retrieve_multi_smart(
        prompt=base_query,
        prefer_label=pred_label,
        k_local_each=2,
        k_sch_each=3,
        max_total=8,
    )
    context_md, ref_list = _format_context_dual(passages, max_chars=3600)

    # 2) Build prompt → user payload
    top_probs = sorted(
        [{"label": k, "p": float(v)} for k, v in probs.items()],
        key=lambda x: x["p"], reverse=True
    )[:6]

    # Deteksi relevansi domain kuku berdasar keyword & nama label
    labels_for_check = list(probs.keys())
    on_domain = _is_nail_domain(user_prompt, labels_for_check)

    user_struct = {
        "label": pred_label,
        "confidence_num": float(conf),
        "confidence_str": _percent_id(conf),
        "question": user_prompt or "",
        "top_probs": top_probs,
        "prompt_on_domain": bool(on_domain),  # info ke LLM
    }

    intent = _detect_intent(user_prompt or "")

    # Aturan tambahan untuk mismatch/out-of-domain
    mismatch_rules = (
        "- PROMPT PENGGUNA TERDETEKSI TIDAK RELEVAN DENGAN DOMAIN KUKU.\n"
        "- Tambahkan SATU kalimat di bagian **Ringkasan** yang menyatakan ketidak-sesuaian prompt "
        "dan bahwa jawaban difokuskan pada hasil analisis kuku.\n"
        "- Abaikan bagian prompt yang tidak relevan di seksi-seksi berikutnya.\n"
    ) if not on_domain else ""

    rules = (
        "- Ikuti JUDUL & URUTAN seksi persis seperti di templat.\n"
        "- Gunakan Bahasa Indonesia yang padat & empatik.\n"
        "- Jika confidence < 0.70, tekankan ketidakpastian di Ringkasan & Saran.\n"
        "- Wajib gunakan konteks [L]/[S]; jika info tidak tersedia, nyatakan tidak ada di konteks.\n"
        "- Hindari diagnosis atau instruksi medis definitif.\n"
        "- Maksimum 3–5 kalimat per seksi, kecuali '## Sumber'.\n"
    ) + ("\n" + mismatch_rules if mismatch_rules else "")

    final_prompt = (
        SYSTEM_PROMPT.strip()
        + "\n\n=== KONTEN ===\n" + context_md
        + "\n\n=== USER ===\n" + json.dumps(user_struct, ensure_ascii=False)
        + "\n\n=== INTENT TERDETEKSI ===\n"
          f"- intent: {intent}\n"
          "- Jika intent=danger: tekankan risiko & red flags dari KONTEN.\n"
          "- Jika intent=care: fokus pada perawatan non-diagnostik & kapan perlu evaluasi tenaga kesehatan.\n"
          "- Jika intent=cause: paparkan kemungkinan penyebab umum, non-diagnostik.\n"
          "- Jika intent=diagnosis_request: tekankan ini bukan diagnosis; jelaskan apa yang model lihat.\n"
        + "\n=== ATURAN TAMBAHAN ===\n" + rules
        + "\n\n# KELUARKAN HASIL SESUAI TEMPLATE DI ATAS"
    )

    # 3) Panggil Gemini
    model_name = (settings.GEMINI_MODEL or os.getenv("GEMINI_MODEL") or "gemini-2.5-flash").strip()
    cli = _client()
    if cli is None:
        # Fallback lokal dengan catatan mismatch bila perlu
        mismatch_note = ""
        if not on_domain and user_prompt:
            mismatch_note = ("Catatan: prompt yang Anda masukkan tampaknya tidak terkait dengan domain kuku; "
                             "jawaban berikut difokuskan pada hasil analisis kuku. ")

        parts: List[str] = []
        parts.append("# Penjelasan\n")
        parts.append("## Ringkasan\n"
                     + mismatch_note
                     + "Berdasarkan analisis citra, hasil mengarah ke kategori yang sesuai dengan temuan visual. "
                     "Ini **bukan diagnosis**; konteks klinis tetap diperlukan.")
        parts.append("## Hasil Prediksi\n"
                     f"- **Label:** *{pred_label}*\n"
                     f"- **Keyakinan model:** **{_percent_id(conf)}**\n"
                     "- **Deskripsi singkat:** (lihat ringkasan dari konteks).")
        parts.append("## Mengapa Model Memperkirakan Ini\n"
                     "- Pola visual konsisten dengan karakteristik pada konteks.\n- Lihat butir pada referensi lokal/ilmiah.")
        parts.append("## Catatan Kemungkinan Terkait (*bukan diagnosis*)\n"
                     "- Kemungkinan bervariasi; rujuk literatur terkait bila tersedia.")
        parts.append("## Saran Pemantauan & Perawatan Umum\n"
                     "- Dokumentasikan dengan foto berkala.\n- Jaga kebersihan, hindari trauma.\n- Konsultasi jika perubahan menetap/berkembang.")
        parts.append("## Disclaimer\n"
                     "Informasi ini untuk edukasi umum dan **bukan** diagnosis medis; penilaian tenaga kesehatan tetap diperlukan.")
        if ref_list:
            parts.append("## Sumber\n" + "\n".join(f"- {r}" for r in ref_list))
        parts.append("\n---\n**Konteks (ringkas):**\n" + context_md)
        return _normalize_sections("\n\n".join(parts))

    try:
        resp = cli.models.generate_content(
            model=model_name,
            contents=[{"role": "user", "parts": [{"text": final_prompt}]}],
            config={"response_mime_type": "text/plain"},
        )
        text = (_extract_text_safe(resp) or "").strip()
        if not text:
            log.warning("Gemini return empty text; using fallback minimal.")
            mismatch_note = ""
            if not on_domain and user_prompt:
                mismatch_note = ("Catatan: prompt yang Anda masukkan tampaknya tidak terkait dengan domain kuku; "
                                 "jawaban berikut difokuskan pada hasil analisis kuku.\n\n")

            text = (
                "# Penjelasan\n\n"
                "## Ringkasan\n" + mismatch_note +
                "Tidak ada respons dari model. Ini bukan diagnosis.\n\n"
                "## Hasil Prediksi\n"
                f"- **Label:** *{pred_label}*\n- **Keyakinan model:** **{_percent_id(conf)}**\n"
                "- **Deskripsi singkat:** (tidak tersedia)\n\n"
                "## Mengapa Model Memperkirakan Ini\n(tidak tersedia)\n\n"
                "## Catatan Kemungkinan Terkait (*bukan diagnosis*)\n(tidak tersedia)\n\n"
                "## Saran Pemantauan & Perawatan Umum\n"
                "- Dokumentasikan perubahan, jaga kebersihan, konsultasi bila perlu.\n\n"
                "## Disclaimer\nInformasi ini edukasi umum dan bukan diagnosis medis.\n"
            )
        if ref_list:
            if "## Sumber" not in text:
                text = text.rstrip() + "\n\n## Sumber\n"
            text = text.rstrip() + "\n" + "\n".join(f"- {r}" for r in ref_list)

        return _normalize_sections(text)

    except Exception as e:
        log.exception("Gemini generate_content error: %s", e)
        mismatch_note = ""
        if not on_domain and user_prompt:
            mismatch_note = ("Catatan: prompt yang Anda masukkan tampaknya tidak terkait dengan domain kuku; "
                             "jawaban berikut difokuskan pada hasil analisis kuku. ")

        fb = (
            "# Penjelasan\n\n"
            "## Ringkasan\n" + mismatch_note +
            "Terjadi kendala RAG/LLM. Ini bukan diagnosis.\n\n"
            "## Hasil Prediksi\n"
            f"- **Label:** *{pred_label}*\n- **Keyakinan model:** **{_percent_id(conf)}**\n"
            "- **Deskripsi singkat:** (lihat konteks di bawah)\n\n"
            "## Mengapa Model Memperkirakan Ini\n(tidak tersedia)\n\n"
            "## Catatan Kemungkinan Terkait (*bukan diagnosis*)\n(tidak tersedia)\n\n"
            "## Saran Pemantauan & Perawatan Umum\n"
            "- Dokumentasikan perubahan, jaga kebersihan, konsultasi bila perlu.\n\n"
            "## Disclaimer\nInformasi ini edukasi umum dan bukan diagnosis medis.\n"
        )
        if ref_list:
            fb += "\n## Sumber\n" + "\n".join(f"- {r}" for r in ref_list)
        fb += "\n\n---\n**Konteks (ringkas):**\n" + context_md
        return _normalize_sections(fb)
