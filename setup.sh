#!/usr/bin/env bash
# ── DocuMind Setup Script (Linux / macOS) ────────────────────
set -e

echo ""
echo "==========================================="
echo "  DocuMind RAG Chatbot — Setup"
echo "==========================================="
echo ""

# 1. Virtual environment
echo "[1/4] Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
echo ""
echo "[2/4] Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# 3. Download embedding model
echo ""
echo "[3/4] Downloading embedding model (paraphrase-MiniLM-L3-v2)..."
python -c "
from sentence_transformers import SentenceTransformer
print('Downloading model...')
SentenceTransformer('paraphrase-MiniLM-L3-v2')
print('Model ready!')
"

# 4. Done
echo ""
echo "[4/4] Setup complete!"
echo ""
echo "To start DocuMind:"
echo "  source venv/bin/activate"
echo "  python app.py"
echo ""
echo "Then open: http://localhost:5000"
