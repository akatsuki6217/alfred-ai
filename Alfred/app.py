import os
import requests
from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename

from memory import remember_from_message, build_memory_prompt, load_memory, save_memory

# ---------- Optional RAG imports ----------
try:
    import chromadb
    from pypdf import PdfReader
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    print("⚠️  RAG disabled — install with: pip install chromadb pypdf")

app = Flask(__name__)

@app.route("/ping")
def ping():
    return jsonify({"ok": True, "version": "alfred-2", "rag": RAG_AVAILABLE})

# ---------- Config ----------
OLLAMA_URL = "http://localhost:11434"
CHAT_MODEL = "llama3.2:3b"        # change to your pulled model
EMBED_MODEL = "nomic-embed-text"  # for document search

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

QUALITY_PRESETS = {
    "low":    {"temperature": 0.7, "num_predict": 256},
    "medium": {"temperature": 0.8, "num_predict": 512},
    "high":   {"temperature": 0.9, "num_predict": 1024},
}

# Session chat histories (RAM only)
sessions = {}

# ---------- ChromaDB ----------
if RAG_AVAILABLE:
    client = chromadb.PersistentClient(path="./chroma_db")
    collection = client.get_or_create_collection(
        name="documents",
        metadata={"hnsw:space": "cosine"}
    )

def get_embedding(text):
    resp = requests.post(f"{OLLAMA_URL}/api/embeddings",
                         json={"model": EMBED_MODEL, "prompt": text}, timeout=60)
    resp.raise_for_status()
    return resp.json()["embedding"]

def chunk_text(text, chunk_size=800, overlap=100):
    chunks, start = [], 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return [c.strip() for c in chunks if c.strip()]

# ---------- Routes ----------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    message = (data.get("message") or "").strip()
    quality = data.get("quality", "high")
    session_id = data.get("session_id", "default")

    if not message:
        return jsonify({"error": "Empty message"}), 400

    # 🧠 Learn the user's name if they say it
    remember_from_message(message)

    # 📚 RAG: find relevant document chunks
    sources, context = [], ""
    if RAG_AVAILABLE and collection.count() > 0:
        try:
            results = collection.query(
                query_embeddings=[get_embedding(message)], n_results=3)
            if results["documents"] and results["documents"][0]:
                docs, metas, dists = (results["documents"][0],
                                      results["metadatas"][0],
                                      results["distances"][0])
                context = "\n\n".join(docs)
                for doc, meta, dist in zip(docs, metas, dists):
                    sources.append({
                        "source": meta.get("source", "unknown"),
                        "chunk": meta.get("chunk", 0),
                        "score": round(max(0.0, 1 - dist), 2),
                    })
        except Exception as e:
            print("RAG error:", e)

    # 🎩 Build the system prompt: persona + memory + document context
    system_prompt = (
        "You are Alfred, a witty, loyal British butler AI. You are polite, "
        "dry-humored, and occasionally call the user 'sir'."
    ) + build_memory_prompt()
    if context:
        system_prompt += ("\n\nThe user has uploaded documents. Use these excerpts "
                          "if relevant, and mention they came from their documents:\n" + context)

    history = sessions.get(session_id, [])
    messages = ([{"role": "system", "content": system_prompt}]
                + history + [{"role": "user", "content": message}])

    try:
        resp = requests.post(f"{OLLAMA_URL}/api/chat", json={
            "model": CHAT_MODEL,
            "messages": messages,
            "stream": False,
            "options": QUALITY_PRESETS.get(quality, QUALITY_PRESETS["high"]),
        }, timeout=120)
        resp.raise_for_status()
        reply = resp.json()["message"]["content"]
    except requests.RequestException as e:
        return jsonify({"error": f"Ollama error: {e}"}), 500

    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": reply})
    sessions[session_id] = history[-20:]

    return jsonify({"reply": reply, "sources": sources})

@app.route("/upload", methods=["POST"])
def upload():
    if not RAG_AVAILABLE:
        return jsonify({"error": "RAG not installed — run: pip install chromadb pypdf"}), 500

    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "No file provided"}), 400

    filename = secure_filename(file.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in (".pdf", ".txt", ".md"):
        return jsonify({"error": "Only PDF, TXT, MD supported"}), 400

    try:
        # 1. Save + extract text
        path = os.path.join(UPLOAD_DIR, filename)
        file.save(path)

        if ext == ".pdf":
            text = "\n".join(p.extract_text() or "" for p in PdfReader(path).pages)
        else:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()

        if not text.strip():
            return jsonify({"error": "No text found in file — is it a scanned/image PDF?"}), 400

        # 2. Check Ollama is alive BEFORE doing expensive work
        try:
            requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        except requests.RequestException:
            return jsonify({"error": "Ollama is not running — start it, sir"}), 500

        # 3. Embed chunks
        chunks = chunk_text(text)
        embeddings = [get_embedding(c) for c in chunks]

        # 4. Remove any old version of this file first
        try:
            collection.delete(where={"source": filename})
        except Exception:
            pass

        # 5. Store — with fallback for older chromadb (no upsert)
        ids = [f"{filename}-{i}" for i in range(len(chunks))]
        metas = [{"source": filename, "chunk": i} for i in range(len(chunks))]
        try:
            collection.upsert(ids=ids, documents=chunks, metadatas=metas, embeddings=embeddings)
        except AttributeError:
            collection.add(ids=ids, documents=chunks, metadatas=metas, embeddings=embeddings)

        return jsonify({"file": filename, "chunks": len(chunks)})

    except requests.RequestException as e:
        return jsonify({"error": f"Embedding failed: {e} — try: ollama pull {EMBED_MODEL}"}), 500
    except Exception as e:
        import traceback
        traceback.print_exc()  # full detail in Flask terminal
        return jsonify({"error": f"Upload failed: {type(e).__name__}: {e}"}), 500

@app.route("/documents", methods=["GET"])
def documents():
    if not RAG_AVAILABLE or collection.count() == 0:
        return jsonify({"documents": []})
    docs = {m["source"] for m in collection.get()["metadatas"]}
    return jsonify({"documents": sorted(docs)})

@app.route("/memory", methods=["GET"])
def get_memory():
    return jsonify(load_memory())

@app.route("/memory", methods=["DELETE"])
def clear_memory():
    save_memory({"name": None, "facts": []})
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(debug=True)