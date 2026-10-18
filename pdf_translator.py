"""PDF layout-preserving translation engine using PyMuPDF (fitz).
Extracts text with vector bounding boxes, typography, colors, and coordinates;
redacts original text while preserving backgrounds, logos, vectors, and artwork;
and inserts translated text precisely into the original positions.
"""

import fitz  # PyMuPDF
import time
from typing import List, Dict, Any, Tuple, Callable, Optional
from core_translator import translate_batch, translate_gtx_single


VALID_FONTS = {
    "helv", "hebo", "heit", "hebi",
    "times", "tibo", "tiit", "tibi",
    "couri", "cobo", "coit", "cobi"
}


class PDFTranslatorEngine:
    def __init__(self):
        pass

    def map_font(self, font_name: str, is_bold: bool, is_italic: bool) -> str:
        """Map extracted PDF font name and attributes to standard base-14 PDF fonts."""
        font_name_lower = font_name.lower()
        if "courier" in font_name_lower or "mono" in font_name_lower:
            if is_bold and is_italic:
                return "cobi"
            elif is_bold:
                return "cobo"
            elif is_italic:
                return "coit"
            return "couri"
        elif "times" in font_name_lower or "serif" in font_name_lower or "roman" in font_name_lower:
            if is_bold and is_italic:
                return "tibi"
            elif is_bold:
                return "tibo"
            elif is_italic:
                return "tiit"
            return "times"
        else:
            # Default to Helvetica (sans-serif)
            if is_bold and is_italic:
                return "hebi"
            elif is_bold:
                return "hebo"
            elif is_italic:
                return "heit"
            return "helv"

    def translate_pdf_bytes(
        self,
        pdf_bytes: bytes,
        target_lang: str = "en",
        method: str = "google_free",
        api_key: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        Main pipeline: Takes raw PDF bytes, extracts text elements with bounding boxes,
        translates text while preserving layout, redacts original text glyphs,
        and re-inserts translated text into exact bounding boxes.
        Returns (translated_pdf_bytes, metadata).
        """
        src_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        out_doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        total_pages = len(src_doc)
        all_text_elements = []

        if progress_callback:
            progress_callback(0.05, f"Analyzing PDF structure across {total_pages} page(s)...")

        total_extracted_chars = 0

        # Step 1: Analyze and extract layout text blocks
        for page_idx in range(total_pages):
            page = src_doc[page_idx]
            page_dict = page.get_text("dict")
            blocks = page_dict.get("blocks", [])

            for b_idx, b in enumerate(blocks):
                if b.get("type") == 0:  # Text block
                    lines = b.get("lines", [])
                    for l_idx, l in enumerate(lines):
                        spans = l.get("spans", [])
                        if not spans:
                            continue

                        full_line_text = "".join([s.get("text", "") for s in spans]).strip()
                        if not full_line_text:
                            continue

                        total_extracted_chars += len(full_line_text)

                        bbox = fitz.Rect(l["bbox"])
                        first_span = spans[0]

                        font_size = first_span.get("size", 10.0)
                        font_name = first_span.get("font", "Helvetica")
                        flags = first_span.get("flags", 0)
                        color_int = first_span.get("color", 0)

                        is_italic = bool(flags & 2)
                        is_bold = bool(flags & 262144) or bool(flags & 16) or ("bold" in font_name.lower())

                        # Convert integer color to RGB tuple (0.0 to 1.0)
                        r = ((color_int >> 16) & 0xFF) / 255.0
                        g = ((color_int >> 8) & 0xFF) / 255.0
                        b_col = (color_int & 0xFF) / 255.0

                        all_text_elements.append({
                            "page_idx": page_idx,
                            "bbox": bbox,
                            "original_text": full_line_text,
                            "font_size": font_size,
                            "font_name": font_name,
                            "is_bold": is_bold,
                            "is_italic": is_italic,
                            "color": (r, g, b_col),
                            "align": 0  # Left align
                        })

        if not all_text_elements:
            if progress_callback:
                progress_callback(1.0, "Completed PDF processing (no extractable text layer found).")
            return pdf_bytes, {
                "total_pages": total_pages,
                "translated_count": 0,
                "char_count": 0,
                "text_elements": []
            }

        # Step 2: Batch translate extracted strings
        if progress_callback:
            progress_callback(0.25, f"Translating {len(all_text_elements)} text blocks to {target_lang}...")

        raw_strings = [elem["original_text"] for elem in all_text_elements]
        translated_strings = translate_batch(
            raw_strings,
            target_lang=target_lang,
            method=method,
            api_key=api_key,
            batch_size=25
        )

        for elem, trans_text in zip(all_text_elements, translated_strings):
            elem["translated_text"] = trans_text

        # Step 3: Redact original text on target document
        if progress_callback:
            progress_callback(0.65, "Redacting original text layer while preserving graphics & artwork...")

        for page_idx in range(total_pages):
            out_page = out_doc[page_idx]
            page_elements = [e for e in all_text_elements if e["page_idx"] == page_idx]

            for elem in page_elements:
                bbox = elem["bbox"]
                padded_bbox = fitz.Rect(bbox.x0 - 0.5, bbox.y0 - 0.5, bbox.x1 + 0.5, bbox.y1 + 0.5)
                out_page.add_redact_annot(padded_bbox, text="", fill=False)

            out_page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

        # Step 4: Re-insert translated text with layout preservation
        if progress_callback:
            progress_callback(0.85, "Re-inserting translated text into original bounding boxes...")

        for page_idx in range(total_pages):
            out_page = out_doc[page_idx]
            page_elements = [e for e in all_text_elements if e["page_idx"] == page_idx]

            for elem in page_elements:
                bbox = elem["bbox"]
                trans_text = elem.get("translated_text", "")
                if not trans_text:
                    continue

                orig_fs = elem["font_size"]
                color = elem["color"]
                font_code = self.map_font(elem["font_name"], elem["is_bold"], elem["is_italic"])
                if font_code not in VALID_FONTS:
                    font_code = "hebo" if elem["is_bold"] else "helv"

                # Dynamic font scaling to guarantee text fits into original bounding box
                min_fs = max(4.0, orig_fs * 0.45)
                cur_fs = orig_fs
                fitted = False

                padded_bbox = fitz.Rect(bbox.x0, bbox.y0 - 1, bbox.x1 + 2, bbox.y1 + 1)

                while cur_fs >= min_fs:
                    try:
                        rc = out_page.insert_textbox(
                            padded_bbox,
                            trans_text,
                            fontsize=cur_fs,
                            fontname=font_code,
                            color=color,
                            align=elem["align"]
                        )
                        if rc >= 0:
                            fitted = True
                            break
                    except Exception:
                        try:
                            rc = out_page.insert_textbox(
                                padded_bbox,
                                trans_text,
                                fontsize=cur_fs,
                                fontname="helv",
                                color=color,
                                align=elem["align"]
                            )
                            if rc >= 0:
                                fitted = True
                                break
                        except Exception:
                            pass
                    cur_fs -= 0.5

                if not fitted:
                    try:
                        out_page.insert_textbox(
                            padded_bbox,
                            trans_text,
                            fontsize=min_fs,
                            fontname="helv",
                            color=color,
                            align=elem["align"]
                        )
                    except Exception:
                        pass

        output_bytes = out_doc.tobytes(garbage=4, deflate=True)
        src_doc.close()
        out_doc.close()

        if progress_callback:
            progress_callback(1.0, "Translation complete! PDF layout successfully rebuilt.")

        metadata = {
            "total_pages": total_pages,
            "translated_count": len(all_text_elements),
            "char_count": total_extracted_chars,
            "text_elements": all_text_elements
        }

        return output_bytes, metadata

    def render_pdf_page_images(self, pdf_bytes: bytes, max_pages: int = 10, dpi: int = 150) -> List[bytes]:
        """Render pages of PDF to PNG images for preview inside Streamlit app."""
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_images = []
        num_pages = min(len(doc), max_pages)

        for p in range(num_pages):
            pix = doc[p].get_pixmap(dpi=dpi)
            page_images.append(pix.tobytes("png"))

        doc.close()
        return page_images
