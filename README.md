# DocuMind — RAG Chatbot

Upload any PDF, DOCX, TXT, MD, XLSX, or CSV file and chat with it using
Retrieval-Augmented Generation powered by **Groq LLaMA** and **ChromaDB**.

---

## Quick Start (Windows)

```bat
setup.bat
venv\Scripts\activate
python app.py
```

Then open **http://localhost:5000**

---

## Quick Start (Linux / macOS)

```bash
chmod +x setup.sh
./setup.sh
source venv/bin/activate
python app.py
```

---

## Project Structure

```
documind/
├── app.py                  ← Flask app (all routes)
├── config.py               ← Typed settings loaded from .env
├── .env                    ← Your secrets (never commit this)
├── .env.example            ← Template
├── requirements.txt
├── setup.bat               ← Windows one-click setup
├── setup.sh                ← Linux/macOS one-click setup
├── utils/
│   ├── __init__.py         ← Exports all public functions
│   ├── security.py         ← File validation, path safety, API key check
│   ├── document_processor.py  ← Text extraction + chunking (main fn: process())
│   └── rag_engine.py       ← ChromaDB embed/store/retrieve
├── templates/
│   └── index.html
└── static/
    ├── css/style.css
    └── js/app.js
```

---

## Supported File Types

| Format | Notes |
|--------|-------|
| PDF    | Text extraction via PyPDF2 |
| DOCX   | Paragraph extraction via python-docx |
| TXT / MD | Plain text |
| XLSX   | All sheets via openpyxl |
| CSV    | Tab-separated rows |

Any filename is accepted — no naming restrictions.

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `GROQ_API_KEY` | Your Groq API key |
| `GROQ_MODEL` | Model to use (default: llama-3.3-70b-versatile) |
| `SECRET_KEY` | Flask session secret |
| `API_KEYS` | Comma-separated API keys |
| `SKIP_CONFIG_VALIDATION` | Set to `true` in development |
| `DAILY_TOKEN_BUDGET` | Max tokens per day |

---

## Key Design Decisions

- **No model download on file upload** — the embedding model is loaded once
  at startup (pre-downloaded by setup script).
- **No API token leak** — the Groq key stays on the server; the frontend
  never sees it.
- **ChromaDB collection names** — always `doc_` + 12-char MD5 hash = 16 chars
  (safely within ChromaDB's 3–63 char limit).
- **Duplicate detection** — re-uploading the same file skips re-embedding.
- **Server-side sessions** — Flask-Session writes session data to disk so
  large document lists never overflow the cookie.
