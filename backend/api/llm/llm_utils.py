# api/llm/llm_utils.py
from __future__ import annotations
import os, logging
from typing import List, Dict, Tuple, Optional
from django.conf import settings
from google import genai  # pip install google-genai

log = logging.getLogger(__name__)

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

def _detect_intent(user_prompt: str) -> str:
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

def _percent_id(conf: float) -> str:
    try:
        s = f"{conf * 100:.1f}%"
        return s.replace(".", ",")
    except Exception:
        return f"{conf:.3f}".replace(".", ",")

# -------------------------
#  Deteksi domain "kuku"
# -------------------------
NAIL_KEYWORDS = {
    # Indonesia
    "kuku", "ujung jari", "pelat kuku", "lempeng kuku", "lunula", "matriks kuku",
    "kutikula", "kulit kuku", "punggung kuku", "dasar kuku",
    "clubbing", "pitting", "melanonychia", "paronychia", "subungual",
    "hiperkeratosis", "onikolisis", "onychodystrophy", "koilonychia",
    # Inggris
    "nail", "fingertip", "nail bed", "nail plate", "nail matrix", "cuticle",
    "onycholysis", "onycho", "onychauxis", "onychosis",
}

def _is_nail_domain(user_prompt: Optional[str], extra_labels: Optional[List[str]] = None) -> bool:
    """
    True jika prompt mengandung istilah domain kuku / label terkait.
    Prompt kosong dianggap relevan (True).
    """
    if not user_prompt:
        return True
    t = user_prompt.lower()
    if any(kw in t for kw in NAIL_KEYWORDS):
        return True
    for lbl in (extra_labels or []):
        if lbl and lbl.lower() in t:
            return True
    return False

def _normalize_sections(md: str) -> str:
    if not md:
        return md
    if "# Penjelasan" not in md:
        md = "# Penjelasan\n\n" + md
    md = md.replace("\n7. Sumber", "\n## Sumber").replace("\n**7. Sumber**", "\n## Sumber")

    lines = md.splitlines()
    out: List[str] = []
    seen_sumber = False
    for ln in lines:
        if ln.strip().lower() in {"## sumber", "### sumber"}:
            if seen_sumber:
                continue
            seen_sumber = True
        out.append(ln)

    text = "\n".join(out)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.strip()

__all__ = [
    "_extract_text_safe",
    "_client",
    "_format_context_dual",
    "_detect_intent",
    "_has_user_question",
    "_percent_id",
    "_normalize_sections",
    "_is_nail_domain",
    "NAIL_KEYWORDS",
]
