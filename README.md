# Agentic RAG Pipeline (WIP)

Experimental Retrieval-Augmented Generation (RAG) pipeline focusing on structured indexing of heterogeneous enterprise documents.

**Current Status:** Only the Phase 1 metadata extraction module (`tagger.py`) is implemented.

## 1. System Requirements & Setup

* **Python:** >= 3.10
* **Local LLM:** Ollama running `nemotron-3-super` (default)
* **Dependencies:**
  ```bash
  pip install langchain-ollama langchain-core python-docx openpyxl
  ```

## 2. Architecture: Phase 1 Tagger (`tagger.py`)

The `tagger.py` module implements a deterministic/probabilistic hybrid approach to generate a structured `file_catalog.json`. It includes state management for process resume capability.

### 2.1. Supported File Types
The parser handles target extensions via `rglob`. Temporary files (prefixed with `~$`) are automatically filtered.

| Category | Extensions | Parsing Method | Fallback |
| :--- | :--- | :--- | :--- |
| Text | `.txt`, `.md`, `.csv` | UTF-8 read (ignore errors) | Filename only |
| Office | `.docx`, `.xlsx` | `python-docx`, `openpyxl` (data_only) | Filename only |
| Media/Binary | `.pdf`, `.pptx`, `.jpg`, `.png`| Not implemented (Metadata only) | Filename only |

### 2.2. Metadata Extraction Logic (2-Track)

#### Track 1: Regex-based Deterministic Extraction
Performs heuristic matching on space-stripped paths and filenames.

1.  **Document Type Classification:** Maps substrings to defined categories:
    * `일일정비일지`, `정비실적보고`, `주간업무보고`, `MSDS`, `장비이력`, `정기검사`, `기술매뉴얼`, `일반`
2.  **Temporal Extraction:** Parses year and month using multiple patterns:
    * YYYY년, /YYYY/, 'YY년, (YYMMDD), YY_MM_DD

#### Track 2: LLM-based Probabilistic Fallback
Triggered if Track 1 fails to resolve `doc_type` or `year`.

* **Input:** Full text extraction (or filename fallback).
* **Model:** Ollama (`nemotron-3-super`), Temp 0.0.
* **Prompt Structure:** Instructs the LLM as a classification agent to output strict JSON containing `doc_type`, `year`, and `month` based on a predefined schema.

### 2.3. Schema & State Management

Output is serialized to `file_catalog.json`. The system loads existing catalogs on startup to skip already processed files, using relative paths as keys.

```json
// file_catalog.json schema example
{
    "relative/path/to/file.docx": {
        "filename": "file.docx",
        "directory": "parent_dir",
        "doc_type": "주간업무보고",
        "year": 2024,
        "month": 5
    }
}
```

## 3. Directory Structure

```text
enterprise-rag/
├── data/                  # Source directory for raw documents (supports nesting)
├── tagger.py              # Implemented: Metadata extraction & cataloging
├── file_catalog.json      # Generated: State file and structured metadata
└── requirements.txt
```

## 4. Usage

```bash
# Execute the tagging pipeline
python tagger.py
```

## 5. Technical Notes & Known Issues

* **OOM Prevention (`.xlsx`):** The Excel parser utilizes `read_only=True` and explicit `wb.close()` to mitigate Out-Of-Memory issues and file descriptor leaks during large batch processing.
* **LLM Context Window:** If processing dense documents, the local LLM may hit context limits. Monitor Ollama resources during Track 2 execution.
* **OCR:** No OCR capability is implemented for image files or image-based PDFs; classification relies solely on the filename for these types.