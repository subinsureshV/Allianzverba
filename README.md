# AllianzVerba — Universal Layout-Preserving Translator

**AllianzVerba** is an advanced AI-powered web application that translates documents and images across multiple languages **while preserving 100% of the original visual layout, typography, formatting, table structures, and graphics**.

Developed by **Subin Suresh**.

---

## 🌟 Supported File Formats

| Format | Extensions | Engine & Technology | Key Capabilities |
| :--- | :--- | :--- | :--- |
| **PDF Documents** | `.pdf` | PyMuPDF (`fitz`) | Vector bounding box detection, glyph redaction, dynamic font autoscaling & layout fitting. |
| **Word Documents** | `.docx`, `.doc` | `python-docx` & Word Automation | Preserves paragraph typography, bold/italic, font colors, bullet lists, headers/footers, and table grids. |
| **Images** | `.png`, `.jpg`, `.jpeg` | EasyOCR & Pillow | Neural text detection, local background color sampling & synthesis, typography contrast calculation, and text inlay. |

---

## 🚀 Key Features

1. **100% Layout & Visual Fidelity Preservation:**
   - **PDFs:** Clears source text glyphs via vector redaction without disturbing logos, vectors, background art, or table borders. Dynamically fits translated text into exact bounding boxes.
   - **Word (`.docx` & `.doc`):** Modifies text directly inside document runs and table cells, keeping table column widths, line spacing, alignments, and styling intact.
   - **Images (`.png`, `.jpg`, `.jpeg`):** Detects text bounding boxes, clears original text by synthesizing sampled background hues, and inlays translated text with optimal contrast and font sizing. Also supports direct export as PDF!

2. **Dual Translation Backends:**
   - **Google Neural MT (Free & Instant):** Pre-configured, zero setup required, batch-optimized with retry & exponential backoff.
   - **Google Gemini AI (LLM Contextual):** High-precision contextual translation powered by `gemini-1.5-flash` using your API key.

3. **Modern Streamlit Web Interface:**
   - Dark glassmorphism aesthetics with curated color palettes and modern typography.
   - Side-by-side visual comparison (Original vs Converted) for PDFs and Images.
   - Line-by-line / block-by-block text inspection tables.
   - Real-time progress updates with step indicators.
   - Instant one-click downloads in original format or converted PDF.

---

## 🛠️ Project Structure

```
Translator upgraded/
├── app.py                 # Streamlit web application & user interface
├── core_translator.py     # Unified translation service (Google Free & Gemini)
├── pdf_translator.py      # PDF format-preserving translation engine
├── docx_translator.py     # Word (.docx & .doc) translation engine
├── image_translator.py    # Image (.png, .jpg, .jpeg) neural OCR & inlay engine
├── requirements.txt       # Python dependencies
└── README.md              # Project documentation
```

---

## ⚡ Quick Start Guide

### 1. Installation

Ensure Python 3.9+ is installed, then install dependencies:

```bash
pip install -r requirements.txt
```

### 2. Launch the Application

Run the Streamlit app:

```bash
streamlit run app.py
```

The web interface will open in your browser at `http://localhost:8501`.
