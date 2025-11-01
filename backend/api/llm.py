from __future__ import annotations
import os, json, logging
from typing import List, Dict, Tuple, Optional
from django.conf import settings
from google import genai  # pip install google-genai
from .rag import retrieve_multi_smart  # smart retriever (lokal + scholar, multi-query)

log = logging.getLogger(__name__)

# Instruksi ketat: non-diagnostik & wajib gunakan konteks
SYS_PROMPT = (
    "You are a helpful assistant for nail health imagery. "
    "Answer in Bahasa Indonesia, concise, non-diagnostic, empathetic. "
    "Use ONLY the provided context blocks; if info is missing, say you don't know. "
    "Always include a brief disclaimer. Cite sources with bracketed indices like [L1], [S1] matching the provided context."
)

# ========= Utilities =========
def _extract_text_safe(resp) -> str:
    if not resp:
        return ""
    t = getattr(resp, "text", None)
    if t:
        return t
    try:
        for c in (getattr(resp, "candidates", None) or []):
            content = getattr(c, "content", None)
            parts = getattr(content, "parts", []) if content else []
            buf: List[str] = []
            for p in parts:
                txt = getattr(p, "text", None)
                if txt:
                    buf.append(txt)
            if buf:
                return "".join(buf)
    except Exception:
        pass
    return ""

def _client():
    api_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    return genai.Client(api_key=api_key)

def _format_context_dual(passages: List[Dict], max_chars: int = 3600) -> Tuple[str, List[str]]:
    """
    Dua blok konteks:
      - === KONTEN LOKAL ===     → tag [L1], [L2], ...
      - === LITERATUR AKADEMIK === → tag [S1], [S2], ... + kumpulkan citation untuk daftar referensi (klik-able)
    Return: (context_md, ref_list)
    """
    L_blocks: List[str] = []
    S_blocks: List[str] = []
    refs: List[str] = []
    used = 0
    l_idx = s_idx = 0

    def _add_block(target_list: List[str], text: str) -> bool:
        nonlocal used
        if used + len(text) + 2 > max_chars:
            remain = max_chars - used - 2
            if remain > 50:
                target_list.append(text[:remain].rstrip() + "…")
                used = max_chars
                return False
            return False
        target_list.append(text)
        used += len(text) + 2
        return True

    for p in passages:
        txt = (p.get("text") or "").strip()
        if not txt:
            continue
        src = (p.get("source") or "unknown").strip()
        bucket = p.get("bucket", "L")

        if bucket == "S":
            s_idx += 1
            tag = f"[S{s_idx}]"
            short = txt if len(txt) <= 1200 else (txt[:1200].rstrip() + "…")
            block = f"{tag} {short}\n(Sumber: {src})"
            # entri referensi klik-able (Markdown)
            cit = (p.get("citation") or "").strip()
            if src and cit:
                refs.append(f"{tag} [{cit}]({src})")
            elif cit:
                refs.append(f"{tag} {cit}")
            else:
                refs.append(f"{tag} {src}")
            if not _add_block(S_blocks, block):
                break
        else:
            l_idx += 1
            tag = f"[L{l_idx}]"
            block = f"{tag} {txt}\n(Sumber: {src})"
            if not _add_block(L_blocks, block):
                break

        if used >= max_chars:
            break

    ctx_parts: List[str] = []
    if L_blocks:
        ctx_parts.append("=== KONTEN LOKAL ===")
        ctx_parts.extend(L_blocks)
    if S_blocks:
        if ctx_parts:
            ctx_parts.append("")
        ctx_parts.append("=== LITERATUR AKADEMIK ===")
        ctx_parts.extend(S_blocks)

    context_md = "\n".join(ctx_parts).strip() if ctx_parts else "Tidak ada konteks yang relevan."
    return context_md, refs

# ========= Intent ringan (boleh dipakai untuk nada/penekanan) =========
def _detect_intent(user_prompt: str) -> str:
    """
    Intent sederhana berbasis kata kunci ID/EN.
    Returns: danger | care | cause | diagnosis_request | other
    """
    p = (user_prompt or "").lower()
    danger_kw = ["bahaya", "berbahaya", "parah", "gawat", "darurat", "urgent", "emergency", "danger", "severe"]
    care_kw   = ["obat", "rawat", "perawatan", "obati", "tindakan", "apa yang harus", "home care", "treatment"]
    cause_kw  = ["penyebab", "kenapa", "mengapa", "sebab", "etiologi", "cause", "trigger"]
    diag_kw   = ["diagnosa", "diagnosis", "apakah ini penyakit", "apa penyakit", "ini apa", "penyakit apa", "hasilnya apa"]

    def _has_any(words): return any(w in p for w in words)
    if _has_any(danger_kw): return "danger"
    if _has_any(care_kw): return "care"
    if _has_any(cause_kw): return "cause"
    if _has_any(diag_kw): return "diagnosis_request"
    return "other"

def _has_user_question(user_prompt: Optional[str]) -> bool:
    return bool((user_prompt or "").strip())

# ========= Main API =========
def explain_prediction(pred_label: str, conf: float, probs: dict, user_prompt: str) -> str:
    """
    Penjelasan berbasis RAG (lokal + literatur akademik) + Gemini Flash.
    - Smart retriever (multi-query + sinonim).
    - Sitasi [Lx] (lokal) & [Sx] (literatur, klik-able di Referensi).
    - Struktur output FIX sesuai permintaan (bagian 1 opsional).
    """
    # 1) Retrieval (smart, gabungan)
    base_query = (user_prompt or "Jelaskan secara non-diagnostik") + f" | label: {pred_label}"
    passages = retrieve_multi_smart(
        prompt=base_query,
        prefer_label=pred_label,
        k_local_each=2,
        k_sch_each=3,
        max_total=8,
    )
    context_md, ref_list = _format_context_dual(passages, max_chars=3600)

    # 2) Build prompt
    user_struct = {
        "label": pred_label,
        "confidence": f"{conf:.3f}",
        "question": user_prompt or "",
        "top_probs": sorted(
            [{"label": k, "p": float(v)} for k, v in probs.items()],
            key=lambda x: x["p"], reverse=True
        )[:6]
    }
    intent = _detect_intent(user_prompt or "")
    include_user_q = _has_user_question(user_prompt)

    section_rules = (
        "- Tulis **judul seksi persis** seperti di bawah, dalam bahasa Indonesia.\n"
        "- Ikuti urutan. Jangan menambah atau mengubah nama seksi.\n"
        "- Jika seksi pertama ditandai *(opsional)* dan prompt kosong/tidak relevan, **jangan tampilkan** seksi itu.\n"
        "- Gunakan kalimat ringkas; hindari diagnosis pasti; beri sitasi [Lx]/[Sx] pada pernyataan berbasis fakta.\n"
        "- Batasan: 3–5 kalimat per seksi (kecuali 'Sumber').\n"
    )

    fixed_outline = [
        "1. (opsional) Tanggapan atas pertanyaan pengguna" if include_user_q else None,
        "2. Hasil prediksi dan deskripsi",
        "3. Mengapa model memperkirakan kategori ini",
        "4. Penyebab",
        "5. Pencegahan",
        "6. Disclaimer",
        "7. Sumber",
    ]
    fixed_outline_md = "\n".join([f"- {s}" for s in fixed_outline if s])

    final_prompt = (
        SYS_PROMPT.strip()
        + "\n\n=== KONTEN ===\n" + context_md
        + "\n\n=== USER ===\n" + json.dumps(user_struct, ensure_ascii=False)
        + "\n\n=== INTENT TERDETEKSI ===\n"
          f"- intent: {intent}\n"
          "- Jika intent=danger: tekankan tingkat risiko & red flags dari KONTEN.\n"
          "- Jika intent=care: fokus pada perawatan non-diagnostik & kapan perlu evaluasi tenaga kesehatan.\n"
          "- Jika intent=cause: paparkan kemungkinan penyebab umum, non-diagnostik.\n"
          "- Jika intent=diagnosis_request: tekankan ini bukan diagnosis; jelaskan apa yang model lihat.\n"
        + "\n=== ATURAN FORMAT ===\n" + section_rules
        + "\n=== DAFTAR SEKSI (WAJIB DIIKUTI) ===\n" + fixed_outline_md
        + "\n\n=== PETUNJUK ISI PER SEKSI ===\n"
          "- 2. Hasil prediksi dan deskripsi: sebut label prediksi dan keyakinan (persen), lalu deskripsi visual ringkas [Lx].\n"
          "- 3. Mengapa model memperkirakan kategori ini: jelaskan pola/fitur yang cocok menurut KONTEN [Lx]/[Sx].\n"
          "- 4. Penyebab: kemungkinan penyebab **umum** terkait temuan (non-diagnostik) [Sx] bila tersedia.\n"
          "- 5. Pencegahan: kebiasaan/perawatan umum & kapan perlu evaluasi; sebut red flags bila ada [Lx]/[Sx].\n"
          "- 6. Disclaimer: tekankan edukasi, bukan diagnosis medis.\n"
          "- 7. Sumber: cantumkan [Lx]/[Sx] yang benar-benar dipakai.\n"
    )

    # 3) Call Gemini (single user message; text/plain agar lolos validasi)
    model_name = (settings.GEMINI_MODEL or os.getenv("GEMINI_MODEL") or "gemini-2.5-flash").strip()
    cli = _client()
    if cli is None:
        # fallback lokal jika API key kosong
        fallback = []
        if include_user_q:
            fallback.append("**1. (opsional) Tanggapan atas pertanyaan pengguna**\nPertanyaan Anda telah dicatat. Lihat bagian di bawah untuk konteks dan langkah aman.")
        fallback.append(f"**2. Hasil prediksi dan deskripsi**\nModel memperkirakan *{pred_label}* (keyakinan {conf*100:.1f}%).\n")
        fallback.append("**3. Mengapa model memperkirakan kategori ini**\nLihat ringkasan pada konteks yang ditemukan di bawah.")
        fallback.append("**4. Penyebab**\nKemungkinan bervariasi; butuh konteks klinis tambahan.")
        fallback.append("**5. Pencegahan**\nJaga kebersihan, hindari trauma berulang, pantau perubahan.")
        fallback.append("**6. Disclaimer**\nInformasi ini bersifat edukasi dan bukan diagnosis medis.")
        if ref_list:
            fallback.append("**7. Sumber**\n" + "\n".join(f"- {r}" for r in ref_list))
        fallback.append("\n**Konteks yang ditemukan:**\n" + context_md)
        return "\n\n".join(fallback)

    try:
        resp = cli.models.generate_content(
            model=model_name,
            contents=[{"role": "user", "parts": [{"text": final_prompt}]}],
            config={"response_mime_type": "text/plain"},
        )
        text = (_extract_text_safe(resp) or "").strip()
        if not text:
            log.warning("Gemini return empty text; using fallback template.")
            text = (
                "**2. Hasil prediksi dan deskripsi**\n"
                f"Model memperkirakan *{pred_label}* (keyakinan {conf*100:.1f}%).\n\n"
                "**3. Mengapa model memperkirakan kategori ini**\n"
                "Tidak ada respons dari LLM, gunakan konteks di bawah.\n\n"
                "**6. Disclaimer**\n"
                "Informasi ini bersifat edukasi dan bukan diagnosis medis.\n\n"
                f"**Konteks yang ditemukan:**\n{context_md}"
            )
        # Tambahkan daftar referensi ilmiah (klik-able)
        if ref_list:
            text = text.rstrip() + "\n\n**7. Sumber**\n" + "\n".join(f"- {r}" for r in ref_list)
        return text
    except Exception as e:
        # Log & fallback (tanpa 500)
        log.exception("Gemini generate_content error: %s", e)
        fb = (
            "**2. Hasil prediksi dan deskripsi**\n"
            f"Model memperkirakan *{pred_label}* (keyakinan {conf*100:.1f}%).\n\n"
            "**3. Mengapa model memperkirakan kategori ini**\n"
            "Terjadi kendala RAG/LLM — gunakan konteks di bawah.\n\n"
            "**6. Disclaimer**\n"
            "Informasi ini bersifat edukasi dan bukan diagnosis medis.\n\n"
            f"**Konteks yang ditemukan:**\n{context_md}"
        )
        if ref_list:
            fb += "\n\n**7. Sumber**\n" + "\n".join(f"- {r}" for r in ref_list)
        return fb
