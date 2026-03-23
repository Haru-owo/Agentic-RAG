```markdown
# Enterprise Agentic RAG Pipeline

An air-gapped, multi-hop Agentic Retrieval-Augmented Generation (RAG) pipeline designed for parsing, indexing, and querying unstructured enterprise legacy documents (DOCX, XLSX, PDF, MD). 

This system mitigates the core limitations of naive RAG architectures—such as context truncation, failure in temporal reasoning, and inaccurate aggregation—by implementing hybrid retrieval (BM25 + Vector MMR) and a 2-track LLM-assisted metadata cataloging system.

## 1. System Requirements

* **Python:** Version 3.10 or higher is strictly required.
* **Ollama:** Must be installed locally for on-premise LLM inference.
* **Framework:** LangChain v0.2.x ecosystem.
* **Hardware:** CUDA-compatible GPU is highly recommended for local embedding and LLM inference.

## 2. Architecture & Core Features

### 2.1. 2-Track Auto-Tagging (Data Preprocessing)
Resolves metadata mapping for raw enterprise files with inconsistent naming conventions.
* **Track 1 (Regex Fast-track):** Heuristic extraction of year, month, and document category based on path and filename regular expressions. Handles the majority of the dataset at high throughput.
* **Track 2 (LLM Zero-shot Fallback):** For unclassified documents, extracts a 500-character snippet and routes it to a local LLM for zero-shot classification. 
* State management is handled via `file_catalog.json` with built-in auto-save and resume capabilities.

### 2.2. Hybrid Retrieval & Temporal Expansion
* **Ensemble Retriever:** Combines `BM25` (Sparse retrieval for exact keyword matching) with `BGE-M3` (Dense retrieval for semantic matching) at a 50:50 weight.
* **Maximal Marginal Relevance (MMR):** Applied to the dense retriever to ensure diversity in the fetched context and prevent duplicate information from monopolizing the context window.
* **Dynamic Temporal Injection:** Automatically injects the current system timestamp into the query. Forces the LLM to perform relative temporal reasoning (e.g., mapping "latest" or "last 5 years" to exact chronological context).

## 3. Directory Structure

Ensure your project directory matches the following structure before execution:

    enterprise-rag/
    ├── data/                  # Drop raw documents here (Nested folders supported)
    ├── smart_tagger.py        # Phase 1: Metadata extraction & cataloging
    ├── indexer.py             # Phase 2: Parent-Child chunking & ChromaDB embedding
    ├── rag_query_pipeline.py  # Phase 3: Gradio Web UI & LLM Inference
    ├── requirements.txt       # Dependencies list
    └── start.sh               # Automated entrypoint script

## 4. Setup & Execution

### Step 1: Initialize Local LLM
Ensure Ollama is running as a background service, then pull the required model.
```bash
ollama pull nemotron-3-super
```

### Step 2: Create start.sh
Create a `start.sh` file in your root directory and paste the following bash script. This script automates virtual environment creation, dependency installation, and the sequential execution of the RAG pipeline.

```bash
#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "[INFO] Initializing Enterprise Agentic RAG Pipeline..."

# 1. Virtual Environment Setup
if [ ! -d "venv" ]; then
    echo "[INFO] Creating Python virtual environment (venv)..."
    python3 -m venv venv
fi

echo "[INFO] Activating virtual environment..."
source venv/bin/activate

echo "[INFO] Installing required dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# 2. Data Preprocessing & Auto-Tagging
echo "[INFO] Executing Phase 1: Smart Tagger (Catalog Generation)..."
python smart_tagger.py

# 3. Vectorization & Embedding
echo "[INFO] Executing Phase 2: Indexer (ChromaDB & BM25 Setup)..."
python indexer.py

# 4. Web UI & Inference
echo "[INFO] Executing Phase 3: RAG Query Pipeline (Gradio UI)..."
python rag_query_pipeline.py

echo "[INFO] Pipeline terminated."
```

### Step 3: Run the Pipeline
Grant execution permissions to the script and run it. The Web UI will be exposed on `0.0.0.0:7860`.

```bash
chmod +x start.sh
./start.sh
```

## 5. Troubleshooting

* **CUDA Out of Memory (OOM):** If the LLM crashes during inference, decrease the context window limit in `rag_query_pipeline.py`. Update `num_ctx` in the `OllamaLLM` instantiation from `16384` to `8192` or `4096`.
* **Corrupted Office Files:** The parser automatically catches `Exception` during DOCX/XLSX binary reads. If a file is corrupted, it logs a parsing error and uses the filename as the text snippet fallback to prevent pipeline crashes.
```