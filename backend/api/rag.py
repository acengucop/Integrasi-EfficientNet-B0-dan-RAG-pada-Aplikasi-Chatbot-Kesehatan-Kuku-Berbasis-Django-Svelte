# api/rag.py
from __future__ import annotations
import os
from pathlib import Path
from typing import List, Dict, Optional, Tuple

import chromadb
import numpy as np
from sentence_transformers import SentenceTransformer

# ===== Konfigurasi dasar =====
BASE_DIR = Path(__file__).resolve().parents[1]

# Izinkan override lokasi index via ENV: RAG_INDEX_DIR
INDEX_DIR = Path(os.getenv("RAG_INDEX_DIR", str(BASE_DIR / "rag_index")))

# Nama koleksi
COLL_LOCAL   = os.getenv("RAG_COLL_LOCAL", "nail_kb")
COLL_SCHOLAR = os.getenv("RAG_COLL_SCHOLAR", "nail_kb_scholar")

# Model embedding lokal (harus sama saat build index)
EMB_MODEL_NAME = os.getenv("EMB_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")

# ===== Lazy singletons =====
_model: Optional[SentenceTransformer] = None
_client: Optional[chromadb.ClientAPI] = None
_col_local = None
_col_scholar = None


def _get_model() -> SentenceTransformer:
    """Lazy-load SentenceTransformer dengan konfigurasi default."""
    global _model
    if _model is None:
        _model = SentenceTransformer(EMB_MODEL_NAME)  # otomatis pilih CPU/GPU yang tersedia
    return _model


def _get_client() -> chromadb.ClientAPI:
    """Lazy-init Chroma PersistentClient pada INDEX_DIR."""
    global _client
    if _client is None:
        INDEX_DIR.mkdir(exist_ok=True, parents=True)
        _client = chromadb.PersistentClient(path=str(INDEX_DIR))
    return _client


def _get_collections():
    """Ambil (local, scholar) collection, dibuat jika belum ada."""
    global _col_local, _col_scholar
    client = _get_client()
    if _col_local is None:
        _col_local = client.get_or_create_collection(COLL_LOCAL)
    if _col_scholar is None:
        _col_scholar = client.get_or_create_collection(COLL_SCHOLAR)
    return _col_local, _col_scholar


def reset_index_cache() -> None:
    """Reset cache model/klien/collection (dipakai saat rebuild index)."""
    global _model, _client, _col_local, _col_scholar
    _model = None
    _client = None
    _col_local = None
    _col_scholar = None


# ===== Embedding & retrieval helpers =====
def embed(texts: List[str]) -> np.ndarray:
    """Return normalized embeddings (N, D)."""
    model = _get_model()
    vecs = model.encode(texts, batch_size=32, normalize_embeddings=True)
    return np.asarray(vecs)


def _pack_query_result(out: dict, bucket_tag: str) -> List[Dict]:
    """
    Normalisasi keluaran Chroma ke bentuk:
    {text, source, id, label?, citation?, bucket, score?}
    """
    docs = out.get("documents", [[]])[0]
    metas = out.get("metadatas", [[]])[0]
    ids   = out.get("ids", [[]])[0]
    dists = out.get("distances", [[]])[0] if "distances" in out else []

    results: List[Dict] = []
    for i, doc in enumerate(docs):
        meta = metas[i] if i < len(metas) else {} or {}
        item = {
            "text": doc,
            "source": meta.get("source", "unknown"),
            "id": ids[i] if i < len(ids) else "",
            "label": meta.get("label"),
            "citation": meta.get("citation"),  # hanya ada di scholar
            "bucket": bucket_tag,              # "L" lokal, "S" scholar
        }
        # Jika Chroma mengembalikan distance, simpan sebagai score (kecil = lebih mirip untuk cosine)
        if i < len(dists):
            item["score"] = dists[i]
        results.append(item)
    return results


# ===== API publik (kompatibel lama) =====
def retrieve(query: str, k: int = 4) -> List[Dict]:
    """
    Ambil top-k dari koleksi lokal saja (kompatibel dengan versi sebelumnya).
    Return: list[{text, source, id}]
    """
    client = _get_client()
    col = client.get_or_create_collection(COLL_LOCAL)

    qvec = embed([query])[0].tolist()
    out = col.query(query_embeddings=[qvec], n_results=k)
    docs = out.get("documents", [[]])[0]
    metas = out.get("metadatas", [[]])[0]
    ids   = out.get("ids", [[]])[0]

    results: List[Dict] = []
    for i, doc in enumerate(docs):
        meta = metas[i] if i < len(metas) else {} or {}
        src  = meta.get("source", "unknown")
        results.append({"text": doc, "source": src, "id": ids[i] if i < len(ids) else ""})
    return results


def retrieve_multi(
    query: str,
    k_local: int = 3,
    k_sch: int = 4,
    prefer_label: Optional[str] = None,
) -> List[Dict]:
    """
    Ambil gabungan hasil dari koleksi lokal (L) & scholar (S).
    - prefer_label: jika diisi, hasil scholar yang label-nya sama diprioritaskan.
    Return: list[{text, source, id, label?, citation?, bucket: 'L'|'S', score?}]
    """
    col_local, col_sch = _get_collections()
    qvec = embed([query])[0].tolist()

    out_local = col_local.query(query_embeddings=[qvec], n_results=k_local)
    out_schol = col_sch.query(query_embeddings=[qvec], n_results=k_sch)

    local_hits = _pack_query_result(out_local, "L")
    schol_hits = _pack_query_result(out_schol, "S")

    if prefer_label:
        # prioritas sederhana: taruh yang labelnya match di depan
        schol_hits.sort(key=lambda r: (r.get("label") == prefer_label), reverse=True)

    # Gabungkan (lokal dulu agar [Lx] konsisten)
    merged = local_hits + schol_hits
    return merged


# ==== SMART RETRIEVER (query expansion + multi-query) ====

# sinonim ringan & perluasan istilah (bisa ditambah terus sesuai kebutuhan)
_LABEL_ALIASES = {
    "pitting": ["pitting", "cekungan kuku", "cekungan kecil pada kuku", "nail pitting"],
    "clubbing": ["clubbing", "ujung jari membulat", "kuku membulat", "clubbing finger", "nail clubbing"],
    "Onychogryphosis": ["onychogryphosis", "kuku menebal melengkung", "ram's horn nail"],
    "Acral_Lentiginous_Melanoma": ["acral lentiginous melanoma", "ALM", "garis gelap pada kuku", "melanonychia"],
    "blue_finger": ["blue finger", "jari kebiruan", "sianosis jari", "kuku kebiruan"],
    "Healthy_Nail": ["kuku sehat", "healthy nail", "normal nail", "anatomy nail"],
}

_GENERAL_ALIASES = [
    "kuku", "kesehatan kuku", "perubahan kuku", "perawatan kuku",
    "nail", "nail plate", "nail bed", "nail color", "nail shape",
]


def _build_query_variants(prompt: str, prefer_label: Optional[str]) -> List[str]:
    """
    Buat beberapa varian query agar lebih peka terhadap istilah/pertanyaan user.
    """
    q = (prompt or "").strip()
    base: List[str] = []
    if q:
        base.extend([q, q.lower(), f"{q} kuku", f"{q} nail"])
    else:
        base.extend(["kuku", "nail"])

    # Label-aware expansion
    if prefer_label:
        for a in _LABEL_ALIASES.get(prefer_label, []):
            base.append(f"{q} | label: {prefer_label} | {a}" if q else a)

    # Perluasan umum
    for a in _GENERAL_ALIASES:
        base.append(f"{q} {a}" if q else a)

    # Uniq + batas 10 varian
    seen = set()
    variants: List[str] = []
    for s in base:
        s = (s or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        variants.append(s)
    return variants[:10]


def _merge_hits(*hit_lists: List[List[Dict]]) -> List[Dict]:
    """
    Gabungkan hasil dari banyak panggilan query. Dedup berdasarkan (id, bucket).
    Pilih entry dengan score (distance) terbaik (lebih kecil lebih baik untuk cosine).
    """
    best: Dict[Tuple[str, str], Dict] = {}
    for hits in hit_lists:
        for h in hits:
            key = (h.get("id") or "", h.get("bucket") or "L")
            score = h.get("score", None)
            if key not in best:
                best[key] = h
            else:
                prev = best[key]
                ps = prev.get("score", None)
                if score is not None and (ps is None or score < ps):
                    best[key] = h
    merged = list(best.values())

    # Urutkan: bucket L dulu, lalu score (kecil lebih mirip), lalu panjang teks (lebih informatif)
    def _rank_key(x: Dict):
        return (0 if x.get("bucket") == "L" else 1, x.get("score", 1e9), -len(x.get("text", "")))

    merged.sort(key=_rank_key)
    return merged


def retrieve_multi_smart(
    prompt: str,
    prefer_label: Optional[str] = None,
    k_local_each: int = 2,
    k_sch_each: int = 3,
    max_total: int = 8,
) -> List[Dict]:
    """
    Retrieval peka terhadap variasi pertanyaan user:
      - bikin beberapa varian query (ID/EN/sinonim/label-aware)
      - untuk tiap varian → ambil top-k lokal & scholar
      - gabungkan & dedup → ambil N teratas

    Return elemen: {text, source, id, label?, citation?, bucket 'L'|'S', score?}
    """
    variants = _build_query_variants(prompt, prefer_label)

    col_local, col_sch = _get_collections()
    all_hits: List[List[Dict]] = []

    for v in variants:
        qvec = embed([v])[0].tolist()
        outL = col_local.query(query_embeddings=[qvec], n_results=k_local_each)
        outS = col_sch.query(query_embeddings=[qvec], n_results=k_sch_each)
        all_hits.append(_pack_query_result(outL, "L"))
        all_hits.append(_pack_query_result(outS, "S"))

    merged = _merge_hits(*all_hits)
    return merged[:max_total]
