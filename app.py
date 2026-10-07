import importlib
import streamlit as st
import time
import io
import os
import fitz # PyMuPDF
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import pdf_translator
importlib.reload(pdf_translator)
from pdf_translator import PDFTranslatorEngine

import policy_screening
importlib.reload(policy_screening)
from policy_screening import extract_policy_screening_hf, SCREENING_FIELD_LABELS

# -----------------------------------------------------------------------------
# Streamlit Page Config & Custom Styling
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="AllianzVerba",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for glassmorphism and modern UI aesthetics
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    /* Main Background */
    .stApp {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%);
        color: #f8fafc;
    }

    /* Streamlit widgets otherwise retain their light-theme text colors. */
    .stApp p,
    .stApp label,
    .stApp [data-testid="stWidgetLabel"] p,
    .stApp [data-testid="stMarkdownContainer"] p,
    .stApp [data-testid="stMarkdownContainer"] li,
    .stApp [data-testid="stCaptionContainer"] {
        color: #e2e8f0 !important;
    }

    .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6 {
        color: #f8fafc !important;
    }

    .stApp input, .stApp textarea, .stApp [data-baseweb="select"] > div {
        color: #f8fafc !important;
        background-color: #0f172a !important;
        border-color: #475569 !important;
    }

    .stApp [data-testid="stFileUploader"] > label,
    .stApp [data-testid="stFileUploader"] small {
        color: #cbd5e1 !important;
    }
    
    /* Custom Card Containers */
    .glass-card {
        background: rgba(30, 41, 59, 0.7);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 16px;
        padding: 24px;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
        margin-bottom: 20px;
    }
    
    .hero-header {
        text-align: center;
        padding: 30px 20px;
        background: linear-gradient(90deg, #3b82f6, #8b5cf6, #ec4899);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 800;
        font-size: 2.8rem;
        margin-bottom: 5px;
    }
    
    .hero-subtitle {
        text-align: center;
        color: #94a3b8;
        font-size: 1.15rem;
        margin-bottom: 30px;
    }
    
    /* Highlight Badges */
    .feature-badge {
        display: inline-block;
        background: rgba(59, 130, 246, 0.15);
        color: #60a5fa;
        border: 1px solid rgba(59, 130, 246, 0.3);
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 600;
        margin: 0 4px;
    }
    
    /* File Uploader styling */
    [data-testid="stFileUploader"] {
        border: 2px dashed rgba(139, 92, 246, 0.4);
        background: rgba(15, 23, 42, 0.5);
        border-radius: 16px;
        padding: 20px;
    }
    
    /* Sidebar Styling */
    [data-testid="stSidebar"] {
        background-color: rgba(15, 23, 42, 0.95);
        border-right: 1px solid rgba(255, 255, 255, 0.08);
    }
    
    /* Metrics box */
    [data-testid="stMetricValue"] {
        color: #38bdf8 !important;
        font-weight: 700;
    }
    
    /* Primary buttons */
    .stButton>button {
        background: linear-gradient(135deg, #3b82f6 0%, #6366f1 100%);
        color: white;
        border: none;
        border-radius: 10px;
        padding: 10px 24px;
        font-weight: 600;
        transition: all 0.3s ease;
        box-shadow: 0 4px 14px 0 rgba(59, 130, 246, 0.4);
    }
    
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px 0 rgba(59, 130, 246, 0.6);
    }

    button[data-testid="stBaseButton-secondary"],
    button[data-testid="stBaseButton-primary"] {
        color: #ffffff !important;
        background: linear-gradient(135deg, #2563eb 0%, #4f46e5 100%) !important;
        border: 1px solid #60a5fa !important;
    }
    
    .stDownloadButton>button {
        background: linear-gradient(135deg, #10b981 0%, #059669 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 12px 28px !important;
        font-weight: 700 !important;
        font-size: 1.1rem !important;
        box-shadow: 0 4px 14px 0 rgba(16, 185, 129, 0.4) !important;
    }
    
    .stDownloadButton>button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px 0 rgba(16, 185, 129, 0.6) !important;
    }
</style>
""", unsafe_allow_html=True)

# Fresh engine each run so code updates (e.g. screening methods) are picked up without stale cache.
engine = PDFTranslatorEngine()



# -----------------------------------------------------------------------------
# App Header
# -----------------------------------------------------------------------------
st.markdown('<div class="hero-header"> AllianzVerba </div>', unsafe_allow_html=True)
st.markdown(
    '<div class="hero-subtitle">'
    'Convert any PDF document to <span class="feature-badge">English</span> '
    'with <span class="feature-badge">Zero Layout Alteration</span>'
    'Developed by subin suresh'
    '</div>', 
    unsafe_allow_html=True
)

# -----------------------------------------------------------------------------
# Sidebar Configuration
# -----------------------------------------------------------------------------
with st.sidebar:
    translation_method = "google_free"
    gemini_api_key = ""

    st.markdown("---")
    st.markdown("### 🎯 Target Language")
    target_lang = st.selectbox(
        "Convert PDF to:",
        ["English", "Spanish", "French", "German", "Chinese", "Japanese", "Italian", "Portuguese"],
        index=0
    )
    
    lang_code_map = {
        "English": "en",
        "Spanish": "es",
        "French": "fr",
        "German": "de",
        "Chinese": "zh-CN",
        "Japanese": "ja",
        "Italian": "it",
        "Portuguese": "pt"
    }
    selected_lang_code = lang_code_map.get(target_lang, "en")
    
    st.markdown("---")
    st.markdown("### 👁️ Rendering Options")
    preview_dpi = st.slider("Preview Image Quality (DPI):", min_value=72, max_value=200, value=130, step=10)
    max_preview_pages = st.slider("Max Preview Pages:", min_value=1, max_value=15, value=5)
    
    hf_token = os.getenv("HF_TOKEN", "")
    hf_model = "Qwen/Qwen2.5-7B-Instruct"

# -----------------------------------------------------------------------------
# Main Content Area: File Upload & Controls
# -----------------------------------------------------------------------------
uploaded_file = st.file_uploader("Choose a PDF file to translate", type=["pdf"])

if uploaded_file is not None:
    st.session_state["pdf_bytes"] = uploaded_file.read()
    st.session_state["pdf_name"] = uploaded_file.name
    st.session_state.pop("screening_result", None)

# -----------------------------------------------------------------------------
# Process & Render PDF
# -----------------------------------------------------------------------------
if "pdf_bytes" in st.session_state and st.session_state["pdf_bytes"]:
    pdf_bytes = st.session_state["pdf_bytes"]
    pdf_name = st.session_state.get("pdf_name", "document.pdf")
    
    st.markdown("---")
    
    # Start Translation Trigger
    if st.button("🚀 Translate PDF Now", type="primary", use_container_width=True):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        def update_progress(pct, msg):
            progress_bar.progress(int(pct * 100))
            status_text.markdown(f"**Status:** {msg}")
            
        start_time = time.time()
        
        try:
            translated_pdf_bytes, metadata = engine.translate_pdf_bytes(
                pdf_bytes,
                target_lang=selected_lang_code,
                method=translation_method,
                api_key=gemini_api_key,
                progress_callback=update_progress
            )
            
            elapsed = time.time() - start_time
            
            st.session_state["translated_pdf_bytes"] = translated_pdf_bytes
            st.session_state["metadata"] = metadata
            st.session_state["elapsed"] = elapsed
            
            progress_bar.progress(100)
            status_text.success(f"🎉 Translation finished successfully in {elapsed:.2f} seconds!")
            
        except Exception as e:
            st.error(f"Translation failed: {str(e)}")
            st.exception(e)

    # If translated PDF exists in session, display results & visual comparison
    if "translated_pdf_bytes" in st.session_state:
        translated_bytes = st.session_state["translated_pdf_bytes"]
        metadata = st.session_state["metadata"]
        elapsed = st.session_state["elapsed"]
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Display Metrics
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Pages", metadata["total_pages"])
        m2.metric("Text Blocks Translated", metadata["translated_count"])
        m3.metric("Characters Processed", metadata["char_count"])
        m4.metric("Processing Time", f"{elapsed:.2f}s")
        
        # Download Section
        st.markdown("<br>", unsafe_allow_html=True)
        out_filename = pdf_name.rsplit(".", 1)[0] + f"_translated_{selected_lang_code.upper()}.pdf"
        
        d_col1, d_col2 = st.columns([2, 1])
        with d_col1:
            st.download_button(
                label=f"📥 Download Converted PDF ({target_lang})",
                data=translated_bytes,
                file_name=out_filename,
                mime="application/pdf",
                use_container_width=True
            )
        with d_col2:
            st.info("🔒 Format, vector artwork, logos, and images are fully preserved.")

        # Side-by-Side Visual Inspection Tabs
        st.markdown("---")
        st.markdown("### 📊 Side-by-Side Visual Comparison")
        
        tab_visual, tab_text, tab_screening = st.tabs([
            "🖼️ Visual Layout Comparison",
            "📝 Text Elements Inspection",
            "🛡️ Sanction & ESG Screening"
        ])
        
        with tab_visual:
            # Render Page Images
            orig_images = engine.render_pdf_page_images(pdf_bytes, max_pages=max_preview_pages, dpi=preview_dpi)
            trans_images = engine.render_pdf_page_images(translated_bytes, max_pages=max_preview_pages, dpi=preview_dpi)
            
            num_preview_pages = len(orig_images)
            page_select = st.selectbox("Select Page to View:", [f"Page {i+1}" for i in range(num_preview_pages)], index=0)
            selected_page_idx = int(page_select.split(" ")[1]) - 1
            
            col_orig, col_trans = st.columns(2)
            
            with col_orig:
                st.markdown("#### 📄 Original PDF (Original Language)")
                if selected_page_idx < len(orig_images):
                    st.image(orig_images[selected_page_idx], use_container_width=True)
                    
            with col_trans:
                st.markdown(f"#### 🌐 Converted PDF ({target_lang})")
                if selected_page_idx < len(trans_images):
                    st.image(trans_images[selected_page_idx], use_container_width=True)

        with tab_text:
            st.markdown("#### Line-by-Line Translation Data")
            elements = metadata.get("text_elements", [])
            if elements:
                data_table = []
                for elem in elements[:100]: # Show up to first 100 elements
                    data_table.append({
                        "Page": elem["page_idx"] + 1,
                        "Original Text": elem["original_text"],
                        "Translated Text": elem.get("translated_text", ""),
                        "Font Size": f"{elem['font_size']:.1f} pt",
                        "Font": elem["font_name"]
                    })
                st.dataframe(data_table, use_container_width=True)
            else:
                st.info("No text elements extracted.")

        with tab_screening:
            st.markdown("#### 🛡️ Sanction & ESG Screening")
            st.caption("Entity names are extracted from the original PDF to preserve their source spelling.")
            st.info("This view extracts names for review. It does not check sanctions lists or ESG databases.")

            run_screening = st.button("🔍 Summarize & Extract Parties (Hugging Face)", use_container_width=True)
            if run_screening:
                if not hf_token:
                    st.error("Add your Hugging Face token in the sidebar to run screening.")
                else:
                    with st.spinner("Analyzing PDF with Hugging Face..."):
                        try:
                            st.session_state["screening_result"] = extract_policy_screening_hf(
                                engine,
                                pdf_bytes,
                                hf_token=hf_token,
                                model_id=hf_model,
                            )
                        except Exception as ex:
                            st.session_state.pop("screening_result", None)
                            st.error(str(ex))

            screening = st.session_state.get("screening_result")
            if screening:
                if screening.get("truncated"):
                    st.warning("Document text was truncated for model limits; re-run on a shorter PDF if results look incomplete.")
                if screening.get("model_id"):
                    st.caption(f"Model: `{screening['model_id']}`")

                summary = screening.get("summary") or ""
                st.markdown("##### Document summary")
                if summary:
                    st.markdown(summary)
                else:
                    st.caption("_Not found_")

                st.markdown("##### Extracted parties")
                for field_key, label in SCREENING_FIELD_LABELS.items():
                    items = screening.get(field_key) or []
                    st.markdown(f"**{label}**")
                    if items:
                        for name in items:
                            st.markdown(f"- {name}")
                    else:
                        st.markdown("*Not found*")
                    st.markdown("")
            elif not run_screening:
                st.markdown(
                    "Enter a Hugging Face token in the sidebar, then click **Summarize & Extract Parties** "
                    "to populate insured names, additional insureds, reinsureds, brokers, and related fields."
                )

# -----------------------------------------------------------------------------
# Footer
# -----------------------------------------------------------------------------
st.markdown("---")
st.markdown(
    '<div style="text-align: center; color: #64748b; font-size: 0.9rem;">'
    'AllianzVerba Translator • Developed by SubinSuresh • Preserves PDF Structure & Design'
    '</div>', 
    unsafe_allow_html=True
)
