# DocuShift AI — Format-Preserving PDF Translator

DocuShift AI is a powerful Streamlit web application that converts any uploaded PDF document in any foreign language into English (or other target languages) **without altering the original format, layout, vector graphics, logos, colors, or page structure**.

---

## 🌟 Key Features

1. **100% Format & Layout Preservation:**
   - Detects precise vector bounding boxes (`bbox`), font styles, weights (bold/italic), colors, and alignments for every text block in the PDF.
   - Clears original text glyphs via vector redaction while leaving background art, raster images, table lines, logos, and custom graphics intact.
   - Dynamically scales translated text font size so it fits inside the exact original bounding boxes without clipping.

2. **Multi-Engine Translation Backends:**
   - **Google Neural MT (Free & Instant):** Pre-configured, zero setup, rate-limit protected.
   - **Google Gemini AI (LLM Contextual):** Optional integration using your Gemini API key for high-precision context-aware translations.

3. **Rich Streamlit Web Interface:**
   - **Built-in Sample PDF Generator:** Click one button to instantly test translation on a multi-element PDF document.
   - **Side-by-Side Visual Inspection:** High-resolution page image viewer comparing the original PDF vs the translated PDF page by page.
   - **Data Inspection Tab:** View original vs translated text blocks along with font attributes.
   - **Instant Download:** One-click download of converted PDF.

---

## 🚀 Quick Start Guide

### 1. Installation

Ensure you have Python 3.9+ installed, then run:

```bash
pip install -r requirements.txt
```

### 2. Launch the Application

Run the Streamlit application:

```bash
streamlit run app.py
```

The web interface will automatically open in your browser at `http://localhost:8501`.

---

## 🛠️ Architecture Overview

- `app.py`: Streamlit user interface, custom CSS styling, session state management, sample PDF generation, and side-by-side visual comparison previewer.
- `pdf_translator.py`: Core translation & PDF reconstruction engine powered by `PyMuPDF` (`fitz`), requests GTX API, and optional `google.generativeai`.
- `requirements.txt`: Python package dependencies.
