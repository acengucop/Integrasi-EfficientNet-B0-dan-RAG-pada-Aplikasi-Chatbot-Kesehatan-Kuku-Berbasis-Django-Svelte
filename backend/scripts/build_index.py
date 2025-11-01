# scripts/build_index.py
import os, glob, re, uuid
from pathlib import Path
import chromadb
from sentence_transformers import SentenceTransformer

BASE_DIR = Path(__file__).resolve().parents[1]
KB_DIR = BASE_DIR / "kb"
INDEX_DIR = BASE_DIR / "rag_index"
COLL_NAME = "nail_kb"
EMB_MODEL_NAME = os.getenv("EMB_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")

def read_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore")
    # normalisasi ringan
    text = re.sub(r'\s+\n', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def chunk_text(text: str, max_chars: int = 800, overlap: int = 120):
    """Chunk sederhana berbasis jumlah karakter + overlap (windowing)."""
    if len(text) <= max_chars:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + max_chars
        chunk = text[start:end]
        # pastikan potong di batas kalimat bila memungkinkan
        m = re.search(r'.*[.!?](\s|$)', chunk, flags=re.S)
        if m and (m.end() > max_chars * 0.6):
            end = start + m.end()
            chunk = text[start:end]
        chunks.append(chunk.strip())
        start = max(0, end - overlap)
    return [c for c in chunks if c]

def main():
    INDEX_DIR.mkdir(exist_ok=True)
    client = chromadb.PersistentClient(path=str(INDEX_DIR))
    try:
        client.delete_collection(COLL_NAME)
    except Exception:
        pass
    col = client.create_collection(COLL_NAME)

    model = SentenceTransformer(EMB_MODEL_NAME)

    docs, ids, metas = [], [], []
    files = [Path(p) for p in glob.glob(str(KB_DIR / "**/*.*"), recursive=True) if p.lower().endswith((".md", ".txt"))]
    if not files:
        raise SystemExit(f"Tidak ada file .md/.txt di {KB_DIR}")

    for path in files:
        raw = read_text(path)
        for i, chunk in enumerate(chunk_text(raw)):
            doc_id = f"{path.as_posix()}::{i}::{uuid.uuid4().hex[:8]}"
            docs.append(chunk)
            ids.append(doc_id)
            metas.append({"source": path.as_posix(), "chunk_index": i})

    # embed in batch
    embeddings = model.encode(docs, batch_size=64, normalize_embeddings=True).tolist()
    col.upsert(documents=docs, embeddings=embeddings, metadatas=metas, ids=ids)

    print(f"Index built: {len(docs)} chunks from {len(files)} files")
    print(f"Collection: {COLL_NAME} @ {INDEX_DIR}")

if __name__ == "__main__":
    main()
