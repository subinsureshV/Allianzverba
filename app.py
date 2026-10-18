import io
import os
import time
import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from core_translator import LANGUAGE_MAP
from pdf_translator import PDFTranslatorEngine
from docx_translator import WordTranslatorEngine
from image_translator import ImageTranslatorEngine

# -----------------------------------------------------------------------------
# Streamlit Page Config & Custom Glassmorphic Styling
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="AllianzVerba — Universal Layout-Preserving Translator",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }
    
    /* Main Background */
    .stApp {
        background: radial-gradient(circle at 10% 20%, rgba(30, 41, 59, 0.95) 0%, rgba(15, 23, 42, 1) 90%);
        color: #f8fafc;
    }

    /* Streamlit widgets font & color adjustments */
    .stApp p,
    .stApp label,
    .stApp [data-testid="stWidgetLabel"] p,
    .stApp [data-testid="stMarkdownContainer"] p,
    .stApp [data-testid="stMarkdownContainer"] li,
    .stApp [data-testid="stCaptionContainer"] {
        color: #e2e8f0 !important;
    }

    .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6 {
        color: #ffffff !important;
        font-weight: 700;
        letter-spacing: -0.02em;
    }

    .stApp input, .stApp textarea, .stApp [data-baseweb="select"] > div {
        color: #f8fafc !important;
        background-color: rgba(15, 23, 42, 0.8) !important;
        border-color: #334155 !important;
        border-radius: 10px !important;
    }

    .stApp [data-testid="stFileUploader"] > label,
    .stApp [data-testid="stFileUploader"] small {
        color: #94a3b8 !important;
    }
    
    /* Glassmorphism Cards */
    .glass-card {
        background: rgba(30, 41, 59, 0.65);
        backdrop-filter: blur(16px);
        -webkit-backdrop-filter: blur(16px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 18px;
        padding: 24px;
        box-shadow: 0 12px 36px 0 rgba(0, 0, 0, 0.45);
        margin-bottom: 24px;
        transition: border-color 0.3s ease;
    }
    
    .glass-card:hover {
        border-color: rgba(59, 130, 246, 0.3);
    }
    
    .hero-container {
        text-align: center;
        padding: 30px 10px 15px 10px;
    }

    .hero-title {
        background: linear-gradient(135deg, #60a5fa 0%, #a855f7 50%, #ec4899 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 800;
        font-size: 3rem;
        margin-bottom: 8px;
        letter-spacing: -0.03em;
    }
    
    .hero-subtitle {
        color: #94a3b8;
        font-size: 1.15rem;
        max-width: 820px;
        margin: 0 auto 20px auto;
        line-height: 1.6;
    }
    
    /* Format Badges */
    .format-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: rgba(59, 130, 246, 0.12);
        color: #60a5fa;
        border: 1px solid rgba(59, 130, 246, 0.25);
        padding: 6px 14px;
        border-radius: 9999px;
        font-size: 0.82rem;
        font-weight: 600;
        margin: 4px;
        letter-spacing: 0.02em;
    }
    
    .format-badge.highlight {
        background: rgba(168, 85, 247, 0.15);
        color: #c084fc;
        border-color: rgba(168, 85, 247, 0.35);
    }

    /* File Uploader styling */
    [data-testid="stFileUploader"] {
        border: 2px dashed rgba(99, 102, 241, 0.35);
        background: rgba(15, 23, 42, 0.4);
        border-radius: 18px;
        padding: 24px;
        transition: all 0.3s ease;
    }
    
    [data-testid="stFileUploader"]:hover {
        border-color: rgba(168, 85, 247, 0.6);
        background: rgba(15, 23, 42, 0.6);
    }
    
    /* Sidebar Styling */
    [data-testid="stSidebar"] {
        background-color: rgba(15, 23, 42, 0.96);
        border-right: 1px solid rgba(255, 255, 255, 0.06);
    }
    
    /* Metric Card */
    [data-testid="stMetric"] {
        background: rgba(30, 41, 59, 0.5);
        border: 1px solid rgba(255, 255, 255, 0.06);
        border-radius: 14px;
        padding: 14px 18px;
    }
    
    [data-testid="stMetricValue"] {
        color: #38bdf8 !important;
        font-weight: 700;
        font-size: 1.8rem !important;
    }
    
    [data-testid="stMetricLabel"] p {
        color: #94a3b8 !important;
        font-weight: 500;
    }
    
    /* Primary buttons */
    .stButton>button {
        background: linear-gradient(135deg, #3b82f6 0%, #6366f1 50%, #8b5cf6 100%);
        color: white;
        border: none;
        border-radius: 12px;
        padding: 12px 28px;
        font-weight: 600;
        font-size: 1rem;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        box-shadow: 0 4px 18px 0 rgba(99, 102, 241, 0.35);
    }
    
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 25px 0 rgba(99, 102, 241, 0.55);
        background: linear-gradient(135deg, #2563eb 0%, #4f46e5 50%, #7c3aed 100%);
    }

    button[data-testid="stBaseButton-secondary"],
    button[data-testid="stBaseButton-primary"] {
        color: #ffffff !important;
        background: linear-gradient(135deg, #2563eb 0%, #4f46e5 100%) !important;
        border: 1px solid rgba(96, 165, 250, 0.4) !important;
        border-radius: 12px !important;
    }
    
    /* Download Buttons */
    .stDownloadButton>button {
        background: linear-gradient(135deg, #10b981 0%, #059669 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 12px !important;
        padding: 14px 28px !important;
        font-weight: 700 !important;
        font-size: 1.05rem !important;
        box-shadow: 0 6px 20px 0 rgba(16, 185, 129, 0.35) !important;
        transition: all 0.3s ease !important;
    }
    
    .stDownloadButton>button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 8px 28px 0 rgba(16, 185, 129, 0.55) !important;
    }

    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        padding-bottom: 4px;
    }

    .stTabs [data-baseweb="tab"] {
        border-radius: 10px 10px 0 0;
        padding: 10px 20px;
        color: #94a3b8;
        font-weight: 600;
    }

    .stTabs [aria-selected="true"] {
        color: #38bdf8 !important;
        border-bottom: 2px solid #38bdf8 !important;
    }
</style>
""", unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# Initialize Translation Engines
# -----------------------------------------------------------------------------
@st.cache_resource
def get_pdf_engine() -> PDFTranslatorEngine:
    return PDFTranslatorEngine()

@st.cache_resource
def get_word_engine() -> WordTranslatorEngine:
    return WordTranslatorEngine()

@st.cache_resource
def get_image_engine() -> ImageTranslatorEngine:
    return ImageTranslatorEngine()

pdf_engine = get_pdf_engine()
word_engine = get_word_engine()
image_engine = get_image_engine()


# -----------------------------------------------------------------------------
# App Header
# -----------------------------------------------------------------------------
st.markdown("""
<div class="hero-container">
    <div class="hero-title">AllianzVerba</div>
    <div class="hero-subtitle">
        Universal layout-preserving document & image translator. Seamlessly translates text while keeping 
        original visual layout, vector graphics, typography, tables, and colors 100% intact.
    </div>
    <div style="margin-bottom: 16px;">
        <span class="format-badge highlight">📄 PDF Documents</span>
        <span class="format-badge">📝 DOCX & DOC Files</span>
        <span class="format-badge">🖼️ PNG Images</span>
        <span class="format-badge">📷 JPG / JPEG Images</span>
        <span class="format-badge highlight">⚡ 100% Layout Preserved</span>
    </div>
</div>
""", unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# Translation Engine Configuration (Default: Google Neural MT)
# -----------------------------------------------------------------------------
translation_method = os.getenv("TRANSLATION_BACKEND", "google_free")
gemini_api_key = os.getenv("GEMINI_API_KEY", "")

# -----------------------------------------------------------------------------
# Sidebar Configuration
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🎯 Target Language")
    
    language_names = list(LANGUAGE_MAP.keys())
    target_lang_name = st.selectbox(
        "Convert document to:",
        options=language_names,
        index=0  # Default: English
    )
    selected_lang_code = LANGUAGE_MAP.get(target_lang_name, "en")
    
    st.markdown("---")
    st.markdown("### 👁️ Rendering & Quality")
    preview_dpi = st.slider("PDF Preview Quality (DPI):", min_value=72, max_value=200, value=130, step=10)
    max_preview_pages = st.slider("Max PDF Preview Pages:", min_value=1, max_value=15, value=5)
    
    st.markdown("---")
    st.markdown(
        '<div style="color: #64748b; font-size: 0.8rem; line-height: 1.4;">'
        'Supported formats:<br>'
        '• <b>PDF</b>: Vector redaction & textbox fitting<br>'
        '• <b>DOCX / DOC</b>: Typography & table layout<br>'
        '• <b>PNG / JPG</b>: Neural OCR & background inlay'
        '</div>',
        unsafe_allow_html=True
    )


# -----------------------------------------------------------------------------
# Main Content Area: Universal File Upload
# -----------------------------------------------------------------------------
uploaded_file = st.file_uploader(
    "Upload a document or image to translate (PDF, DOCX, DOC, PNG, JPG, JPEG):",
    type=["pdf", "docx", "doc", "png", "jpg", "jpeg"]
)

# Helper to determine document category
def get_file_type(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "pdf":
        return "pdf"
    elif ext in ("docx", "doc"):
        return ext
    elif ext in ("png", "jpg", "jpeg"):
        return "image"
    return "unknown"


# Handle file upload state
if uploaded_file is not None:
    current_name = uploaded_file.name
    # Reset if user uploads a different file
    if st.session_state.get("file_name") != current_name:
        st.session_state["file_bytes"] = uploaded_file.read()
        st.session_state["file_name"] = current_name
        st.session_state["file_type"] = get_file_type(current_name)
        st.session_state.pop("translation_result", None)


# -----------------------------------------------------------------------------
# Document Translation Execution & Rendering
# -----------------------------------------------------------------------------
if "file_bytes" in st.session_state and st.session_state["file_bytes"]:
    file_bytes = st.session_state["file_bytes"]
    file_name = st.session_state["file_name"]
    file_type = st.session_state["file_type"]
    
    # Visual Header for Uploaded File
    icon_map = {
        "pdf": "📄 PDF Document",
        "docx": "📝 Word Document (DOCX)",
        "doc": "📝 Word Legacy Document (DOC)",
        "image": "🖼️ High-Res Image"
    }
    file_label = icon_map.get(file_type, "Document")
    file_size_kb = len(file_bytes) / 1024
    
    st.markdown(f"""
    <div style="display: flex; justify-content: space-between; align-items: center; 
                background: rgba(30, 41, 59, 0.4); padding: 14px 20px; border-radius: 12px; 
                border: 1px solid rgba(255, 255, 255, 0.05); margin-top: 10px; margin-bottom: 18px;">
        <div style="font-weight: 600; font-size: 1.05rem;">
            {file_label}: <span style="color: #38bdf8;">{file_name}</span>
        </div>
        <div style="color: #94a3b8; font-size: 0.9rem;">
            Size: {file_size_kb:.1f} KB
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Translation Action Button
    action_labels = {
        "pdf": "🚀 Translate PDF Document Now",
        "docx": "🚀 Translate Word Document (DOCX) Now",
        "doc": "🚀 Translate Word Document (DOC) Now",
        "image": "🚀 Translate Image & Inlay Typography Now"
    }
    button_label = action_labels.get(file_type, "🚀 Translate Now")
    
    if st.button(button_label, type="primary", use_container_width=True):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        def update_progress(pct: float, msg: str):
            progress_bar.progress(int(pct * 100))
            status_text.markdown(f"**Status:** {msg}")
            
        start_time = time.time()
        
        try:
            if file_type == "pdf":
                translated_bytes, metadata = pdf_engine.translate_pdf_bytes(
                    file_bytes,
                    target_lang=selected_lang_code,
                    method=translation_method,
                    api_key=gemini_api_key,
                    progress_callback=update_progress
                )
                orig_preview = None
                trans_preview = None

            elif file_type == "docx":
                translated_bytes, metadata = word_engine.translate_docx_bytes(
                    file_bytes,
                    target_lang=selected_lang_code,
                    method=translation_method,
                    api_key=gemini_api_key,
                    progress_callback=update_progress
                )
                orig_preview = None
                trans_preview = None

            elif file_type == "doc":
                translated_bytes, metadata = word_engine.translate_doc_bytes(
                    file_bytes,
                    target_lang=selected_lang_code,
                    method=translation_method,
                    api_key=gemini_api_key,
                    progress_callback=update_progress
                )
                orig_preview = None
                trans_preview = None

            elif file_type == "image":
                translated_bytes, metadata, orig_preview, trans_preview = image_engine.translate_image_bytes(
                    file_bytes,
                    target_lang=selected_lang_code,
                    method=translation_method,
                    api_key=gemini_api_key,
                    progress_callback=update_progress
                )
            else:
                raise ValueError(f"Unsupported file type: {file_type}")

            elapsed = time.time() - start_time
            
            st.session_state["translation_result"] = {
                "translated_bytes": translated_bytes,
                "metadata": metadata,
                "elapsed": elapsed,
                "file_type": file_type,
                "orig_preview": orig_preview,
                "trans_preview": trans_preview,
                "target_lang_name": target_lang_name,
                "target_lang_code": selected_lang_code
            }
            
            progress_bar.progress(100)
            status_text.success(f"🎉 Translation finished successfully in {elapsed:.2f} seconds!")
            
        except Exception as e:
            st.error(f"Translation encountered an issue: {str(e)}")
            st.exception(e)

    # -------------------------------------------------------------------------
    # Render Translation Results
    # -------------------------------------------------------------------------
    if "translation_result" in st.session_state:
        res = st.session_state["translation_result"]
        translated_bytes = res["translated_bytes"]
        metadata = res["metadata"]
        elapsed = res["elapsed"]
        res_file_type = res["file_type"]
        res_lang_name = res["target_lang_name"]
        res_lang_code = res["target_lang_code"]
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # 1. Metrics Display
        m1, m2, m3, m4 = st.columns(4)
        if res_file_type == "pdf":
            m1.metric("Total Pages", metadata.get("total_pages", 0))
            m2.metric("Text Blocks Translated", metadata.get("translated_count", 0))
            m3.metric("Characters Processed", metadata.get("char_count", 0))
            m4.metric("Processing Time", f"{elapsed:.2f}s")
        elif res_file_type in ("docx", "doc"):
            m1.metric("Paragraphs", metadata.get("total_paragraphs", 0))
            m2.metric("Tables / Cells", f"{metadata.get('total_tables', 0)} / {metadata.get('total_cells', 0)}")
            m3.metric("Elements Translated", metadata.get("translated_count", 0))
            m4.metric("Processing Time", f"{elapsed:.2f}s")
        elif res_file_type == "image":
            m1.metric("Dimensions", metadata.get("dimensions", "N/A"))
            m2.metric("Text Regions Translated", metadata.get("translated_count", 0))
            m3.metric("Characters Processed", metadata.get("char_count", 0))
            m4.metric("Processing Time", f"{elapsed:.2f}s")

        st.markdown("<br>", unsafe_allow_html=True)

        # 2. Download Options
        name_root = file_name.rsplit(".", 1)[0]
        
        if res_file_type == "pdf":
            out_filename = f"{name_root}_translated_{res_lang_code.upper()}.pdf"
            d_col1, d_col2 = st.columns([2, 1])
            with d_col1:
                st.download_button(
                    label=f"📥 Download Converted PDF ({res_lang_name})",
                    data=translated_bytes,
                    file_name=out_filename,
                    mime="application/pdf",
                    use_container_width=True
                )
            with d_col2:
                st.info("🔒 Format, vector artwork, logos, and images are fully preserved.")

        elif res_file_type in ("docx", "doc"):
            out_filename = f"{name_root}_translated_{res_lang_code.upper()}.docx"
            d_col1, d_col2 = st.columns([2, 1])
            with d_col1:
                st.download_button(
                    label=f"📥 Download Converted Word Document ({res_lang_name})",
                    data=translated_bytes,
                    file_name=out_filename,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True
                )
            with d_col2:
                st.info("🔒 Paragraph styles, runs, colors, and table grids are fully preserved.")

        elif res_file_type == "image":
            img_ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else "png"
            if img_ext in ("jpg", "jpeg"):
                mime_type = "image/jpeg"
                out_filename = f"{name_root}_translated_{res_lang_code.upper()}.jpg"
            else:
                mime_type = "image/png"
                out_filename = f"{name_root}_translated_{res_lang_code.upper()}.png"

            d_col1, d_col2 = st.columns([1, 1])
            with d_col1:
                st.download_button(
                    label=f"📥 Download Converted Image ({res_lang_name})",
                    data=translated_bytes,
                    file_name=out_filename,
                    mime=mime_type,
                    use_container_width=True
                )
            with d_col2:
                # Option to also download image converted to PDF
                try:
                    img_pdf_bytes = image_engine.convert_image_to_pdf_bytes(translated_bytes)
                    pdf_out_name = f"{name_root}_translated_{res_lang_code.upper()}.pdf"
                    st.download_button(
                        label=f"📄 Download Converted Image as PDF ({res_lang_name})",
                        data=img_pdf_bytes,
                        file_name=pdf_out_name,
                        mime="application/pdf",
                        use_container_width=True
                    )
                except Exception:
                    st.info("🔒 Background synthesis and font contrast applied seamlessly.")

        # 3. Visual & Data Inspection Tabs
        st.markdown("---")
        st.markdown("### 📊 Document Inspection & Comparison")
        
        if res_file_type == "pdf":
            tab_visual, tab_text = st.tabs([
                "🖼️ Side-by-Side Visual Comparison",
                "📝 Extracted Text Elements & Typography"
            ])
            
            with tab_visual:
                orig_images = pdf_engine.render_pdf_page_images(file_bytes, max_pages=max_preview_pages, dpi=preview_dpi)
                trans_images = pdf_engine.render_pdf_page_images(translated_bytes, max_pages=max_preview_pages, dpi=preview_dpi)
                
                num_pages = len(orig_images)
                if num_pages > 0:
                    page_select = st.selectbox(
                        "Select Page to View:",
                        [f"Page {i + 1}" for i in range(num_pages)],
                        index=0
                    )
                    page_idx = int(page_select.split(" ")[1]) - 1
                    
                    c_orig, c_trans = st.columns(2)
                    with c_orig:
                        st.markdown("#### 📄 Original PDF (Original Language)")
                        if page_idx < len(orig_images):
                            st.image(orig_images[page_idx], use_container_width=True)
                    with c_trans:
                        st.markdown(f"#### 🌐 Converted PDF ({res_lang_name})")
                        if page_idx < len(trans_images):
                            st.image(trans_images[page_idx], use_container_width=True)
                else:
                    st.info("Could not render page previews.")

            with tab_text:
                st.markdown("#### Line-by-Line Translation Data")
                elements = metadata.get("text_elements", [])
                if elements:
                    data_table = []
                    for elem in elements[:150]:
                        data_table.append({
                            "Page": elem.get("page_idx", 0) + 1,
                            "Original Text": elem.get("original_text", ""),
                            "Translated Text": elem.get("translated_text", ""),
                            "Font Size": f"{elem.get('font_size', 10.0):.1f} pt",
                            "Font Style": elem.get("font_name", "Helvetica")
                        })
                    st.dataframe(data_table, use_container_width=True)
                else:
                    st.info("No text elements extracted.")

        elif res_file_type == "image":
            tab_visual, tab_text = st.tabs([
                "🖼️ Side-by-Side Visual Inspection",
                "📝 Neural OCR Detected Regions"
            ])
            
            with tab_visual:
                c_orig, c_trans = st.columns(2)
                with c_orig:
                    st.markdown("#### 📷 Original Image")
                    if res.get("orig_preview"):
                        st.image(res["orig_preview"], use_container_width=True)
                with c_trans:
                    st.markdown(f"#### 🌐 Translated Inlay ({res_lang_name})")
                    if res.get("trans_preview"):
                        st.image(res["trans_preview"], use_container_width=True)

            with tab_text:
                st.markdown("#### Detected Regions & Typography Inlay")
                elements = metadata.get("text_elements", [])
                if elements:
                    data_table = []
                    for elem in elements:
                        data_table.append({
                            "Location / Box": elem.get("location", ""),
                            "Original Text": elem.get("original_text", ""),
                            "Translated Text": elem.get("translated_text", ""),
                            "OCR Confidence": elem.get("confidence", "N/A")
                        })
                    st.dataframe(data_table, use_container_width=True)
                else:
                    st.info("No text regions detected.")

        elif res_file_type in ("docx", "doc"):
            st.markdown("#### 📝 Paragraph & Table Translation Inspection")
            elements = metadata.get("text_elements", [])
            if elements:
                data_table = []
                for elem in elements[:150]:
                    data_table.append({
                        "Location": elem.get("location", ""),
                        "Type": elem.get("type", "paragraph").capitalize(),
                        "Original Text": elem.get("original_text", ""),
                        "Translated Text": elem.get("translated_text", "")
                    })
                st.dataframe(data_table, use_container_width=True)
            else:
                st.info("No text elements found in Word document.")


# -----------------------------------------------------------------------------
# Footer
# -----------------------------------------------------------------------------
st.markdown("---")
st.markdown(
    '<div style="text-align: center; color: #64748b; font-size: 0.9rem; padding: 10px 0;">'
    'AllianzVerba • Universal Document & Image Translator • Developed by Subin Suresh • Preserves Layout & Design'
    '</div>', 
    unsafe_allow_html=True
)
