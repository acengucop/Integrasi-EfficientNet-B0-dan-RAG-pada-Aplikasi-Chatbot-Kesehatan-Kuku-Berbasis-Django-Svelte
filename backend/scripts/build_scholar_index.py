# scripts/build_scholar_index.py
import os, time, json, re, urllib.parse, xml.etree.ElementTree as ET
from pathlib import Path
import requests, chromadb
from sentence_transformers import SentenceTransformer

BASE_DIR   = Path(__file__).resolve().parents[1]
INDEX_DIR  = BASE_DIR / "rag_index"
COLL_NAME  = "nail_kb_scholar"
EMB_MODEL  = os.getenv("EMB_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")

# mapping query PubMed per label (bisa kamu revisi)
LABEL_QUERIES = {
    "pitting": "nail pitting[Title/Abstract]",
    "clubbing": "nail clubbing[Title/Abstract]",
    "Onychogryphosis": "onychogryphosis[Title/Abstract]",
    "Acral_Lentiginous_Melanoma": "acral lentiginous melanoma nail[Title/Abstract]",
    "blue_finger": "blue finger cyanosis nail[Title/Abstract]",
    "Healthy_Nail": "normal nail anatomy plate[Title/Abstract]",
}

def pubmed_search(query, retmax=20):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db":"pubmed","term":query,"retmode":"json","retmax":str(retmax)}
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data.get("esearchresult", {}).get("idlist", [])

def pubmed_fetch(pmids):
    if not pmids: return []
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {"db":"pubmed","id":",".join(pmids),"retmode":"xml"}
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    root = ET.fromstring(r.text)
    out = []
    for art in root.findall(".//PubmedArticle"):
        try:
            art_info = art.find(".//Article")
            title = (art_info.findtext("ArticleTitle") or "").strip()
            abstr = " ".join([t.text or "" for t in art_info.findall(".//Abstract/AbstractText")]).strip()
            journal = art_info.findtext(".//Journal/Title") or ""
            year    = art.findtext(".//PubDate/Year") or ""
            doi = ""
            for idn in art.findall(".//ArticleIdList/ArticleId"):
                if idn.attrib.get("IdType") == "doi":
                    doi = idn.text or ""
            pmid = art.findtext(".//PMID") or ""
            url  = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""
            if title and (abstr or doi):
                out.append({
                    "pmid": pmid, "title": title, "abstract": abstr,
                    "journal": journal, "year": year, "doi": doi, "url": url
                })
        except Exception:
            continue
    return out

def make_citation(p):
    parts = []
    if p.get("title"): parts.append(p["title"])
    jyear = " ".join(x for x in [p.get("journal"), p.get("year")] if x)
    if jyear: parts.append(jyear)
    if p.get("doi"): parts.append(f"doi:{p['doi']}")
    elif p.get("url"): parts.append(p["url"])
    return " — ".join(parts)

def main():
    client = chromadb.PersistentClient(path=str(INDEX_DIR))
    try: client.delete_collection(COLL_NAME)
    except Exception: pass
    col = client.create_collection(COLL_NAME)

    model = SentenceTransformer(EMB_MODEL)

    docs, ids, metas = [], [], []
    for label, q in LABEL_QUERIES.items():
        pmids = pubmed_search(q, retmax=20)
        # supaya santun ke API
        time.sleep(0.4)
        papers = pubmed_fetch(pmids)
        time.sleep(0.4)

        for p in papers:
            text = f"{p['title']}\n\n{p['abstract']}"
            cid  = f"pmid:{p.get('pmid','')}-{label}"
            meta = {
                "source": p.get("url") or (f"https://doi.org/{p['doi']}" if p.get("doi") else "pubmed"),
                "label": label,
                "citation": make_citation(p)
            }
            docs.append(text)
            ids.append(cid)
            metas.append(meta)

    if not docs:
        raise SystemExit("Tidak ada paper yang berhasil diambil. Cek koneksi/query.")

    embs = model.encode(docs, batch_size=32, normalize_embeddings=True).tolist()
    col.upsert(documents=docs, embeddings=embs, metadatas=metas, ids=ids)
    print(f"Scholar index built: {len(docs)} chunks → {COLL_NAME} @ {INDEX_DIR}")

if __name__ == "__main__":
    main()
