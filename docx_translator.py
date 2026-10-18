"""Word Document (DOCX & DOC) translation engine.
Preserves paragraph styling, typography, bold/italic/underline, headings,
bullet lists, headers/footers, and table layout.
Supports native DOCX processing and automatic DOC (legacy 97-2003) conversion.
"""

import io
import os
import tempfile
import re
from typing import List, Dict, Any, Tuple, Callable, Optional
import docx
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

from core_translator import translate_batch, translate_gtx_single

try:
    import win32com.client
    import pythoncom
    HAS_WIN32COM = True
except ImportError:
    HAS_WIN32COM = False


class WordTranslatorEngine:
    def __init__(self):
        pass

    def _convert_doc_to_docx_bytes(self, doc_bytes: bytes) -> bytes:
        """Converts legacy .doc binary bytes to .docx bytes using Word COM automation on Windows."""
        if not HAS_WIN32COM:
            raise RuntimeError("pywin32 is required to convert .doc files on Windows.")

        # Initialize COM library for the current thread (important for Streamlit threads)
        pythoncom.CoInitialize()
        word = None
        temp_dir = tempfile.mkdtemp()
        doc_path = os.path.join(temp_dir, "input_temp.doc")
        docx_path = os.path.join(temp_dir, "converted_temp.docx")

        try:
            with open(doc_path, "wb") as f:
                f.write(doc_bytes)

            word = win32com.client.Dispatch("Word.Application")
            word.Visible = False
            word.DisplayAlerts = False

            doc = word.Documents.Open(os.path.abspath(doc_path))
            # 16 = wdFormatXMLDocument (DOCX)
            doc.SaveAs2(os.path.abspath(docx_path), FileFormat=16)
            doc.Close(SaveChanges=False)

            with open(docx_path, "rb") as f:
                docx_bytes = f.read()

            return docx_bytes
        finally:
            if word:
                try:
                    word.Quit()
                except Exception:
                    pass
            pythoncom.CoUninitialize()
            # Clean up temp files
            for p in [doc_path, docx_path]:
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass
            try:
                os.rmdir(temp_dir)
            except Exception:
                pass

    def _fallback_parse_doc_text(self, doc_bytes: bytes) -> List[str]:
        """Fallback extractor for raw text chunks from .doc binary file."""
        # Extract ASCII and UTF-16 text runs from binary streams
        text = ""
        try:
            # Look for runs of printable characters
            strings = re.findall(rb"[\x20-\x7E]{4,}", doc_bytes)
            decoded = [s.decode("latin1", errors="ignore") for s in strings]
            # Filter out common binary artifacts and metadata
            clean = [s.strip() for s in decoded if len(s.strip()) > 3 and not s.startswith("Microsoft")]
            return clean
        except Exception:
            return []

    def translate_docx_bytes(
        self,
        docx_bytes: bytes,
        target_lang: str = "en",
        method: str = "google_free",
        api_key: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        Translates a DOCX document while preserving paragraph styles,
        run formats (bold, italic, font, color), tables, and structure.
        """
        doc = docx.Document(io.BytesIO(docx_bytes))

        # We will collect targets: (unit_type, container_ref, original_text)
        targets = []

        if progress_callback:
            progress_callback(0.1, "Analyzing Word document paragraphs, headers, and tables...")

        # 1. Main Document Paragraphs
        for p_idx, p in enumerate(doc.paragraphs):
            text = p.text.strip()
            if text:
                targets.append({
                    "type": "paragraph",
                    "obj": p,
                    "location": f"Paragraph {p_idx + 1}",
                    "original_text": text
                })

        # 2. Document Tables
        table_count = len(doc.tables)
        cell_count = 0
        for t_idx, table in enumerate(doc.tables):
            for r_idx, row in enumerate(table.rows):
                for c_idx, cell in enumerate(row.cells):
                    cell_count += 1
                    cell_text = cell.text.strip()
                    if cell_text:
                        targets.append({
                            "type": "table_cell",
                            "obj": cell,
                            "location": f"Table {t_idx + 1} (R{r_idx + 1}, C{c_idx + 1})",
                            "original_text": cell_text
                        })

        # 3. Headers and Footers
        for s_idx, section in enumerate(doc.sections):
            for p in section.header.paragraphs:
                text = p.text.strip()
                if text:
                    targets.append({
                        "type": "header",
                        "obj": p,
                        "location": f"Section {s_idx + 1} Header",
                        "original_text": text
                    })
            for p in section.footer.paragraphs:
                text = p.text.strip()
                if text:
                    targets.append({
                        "type": "footer",
                        "obj": p,
                        "location": f"Section {s_idx + 1} Footer",
                        "original_text": text
                    })

        total_extracted_chars = sum(len(t["original_text"]) for t in targets)

        if not targets:
            if progress_callback:
                progress_callback(1.0, "Word document processing finished (no text blocks found).")
            return docx_bytes, {
                "total_paragraphs": len(doc.paragraphs),
                "total_tables": table_count,
                "total_cells": cell_count,
                "char_count": 0,
                "text_elements": []
            }

        # Batch translate extracted text
        if progress_callback:
            progress_callback(0.3, f"Translating {len(targets)} Word text elements to {target_lang}...")

        raw_strings = [t["original_text"] for t in targets]
        translated_strings = translate_batch(
            raw_strings,
            target_lang=target_lang,
            method=method,
            api_key=api_key,
            batch_size=25
        )

        for t, trans_text in zip(targets, translated_strings):
            t["translated_text"] = trans_text

        # Re-apply translated text while preserving formatting
        if progress_callback:
            progress_callback(0.75, "Reconstructing document with formatting and table layout...")

        for t in targets:
            trans_text = t.get("translated_text", "")
            if not trans_text:
                continue

            obj = t["obj"]
            unit_type = t["type"]

            if unit_type in ("paragraph", "header", "footer"):
                p = obj
                # If paragraph has runs, preserve formatting of the first primary run
                if p.runs:
                    first_run = p.runs[0]
                    first_run.text = trans_text
                    # Clear any subsequent runs to avoid duplicated text
                    for subsequent_run in p.runs[1:]:
                        subsequent_run.text = ""
                else:
                    p.text = trans_text

            elif unit_type == "table_cell":
                cell = obj
                # Preserve formatting in cell paragraphs
                if cell.paragraphs:
                    p = cell.paragraphs[0]
                    if p.runs:
                        p.runs[0].text = trans_text
                        for subsequent_run in p.runs[1:]:
                            subsequent_run.text = ""
                    else:
                        p.text = trans_text
                    # Clear remaining paragraphs in the same cell if any
                    for extra_p in cell.paragraphs[1:]:
                        extra_p.text = ""
                else:
                    cell.text = trans_text

        # Save translated document to bytes
        output_stream = io.BytesIO()
        doc.save(output_stream)
        output_bytes = output_stream.getvalue()

        if progress_callback:
            progress_callback(1.0, "Translation complete! Word document formatting preserved.")

        metadata = {
            "total_paragraphs": len(doc.paragraphs),
            "total_tables": table_count,
            "total_cells": cell_count,
            "translated_count": len(targets),
            "char_count": total_extracted_chars,
            "text_elements": [
                {
                    "location": t["location"],
                    "original_text": t["original_text"],
                    "translated_text": t["translated_text"],
                    "type": t["type"]
                }
                for t in targets
            ]
        }

        return output_bytes, metadata

    def translate_doc_bytes(
        self,
        doc_bytes: bytes,
        target_lang: str = "en",
        method: str = "google_free",
        api_key: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        Translates a legacy Word .doc document by converting it to .docx via Word COM,
        or fallback text extraction if Word COM is unavailable.
        """
        if progress_callback:
            progress_callback(0.05, "Converting legacy .doc format to .docx structure...")

        try:
            docx_bytes = self._convert_doc_to_docx_bytes(doc_bytes)
            return self.translate_docx_bytes(
                docx_bytes,
                target_lang=target_lang,
                method=method,
                api_key=api_key,
                progress_callback=progress_callback
            )
        except Exception as e:
            # Fallback path if Word COM is unavailable
            if progress_callback:
                progress_callback(0.2, "Parsing document streams via binary fallback...")

            raw_chunks = self._fallback_parse_doc_text(doc_bytes)
            if not raw_chunks:
                raise RuntimeError(
                    f"Could not convert .doc document: {e}. Please ensure Microsoft Word or pywin32 is configured."
                )

            # Create a fresh docx from extracted text
            new_doc = docx.Document()
            translated_chunks = translate_batch(
                raw_chunks,
                target_lang=target_lang,
                method=method,
                api_key=api_key,
                batch_size=25
            )

            text_elements = []
            for orig, trans in zip(raw_chunks, translated_chunks):
                new_doc.add_paragraph(trans)
                text_elements.append({
                    "location": "Document Body",
                    "original_text": orig,
                    "translated_text": trans,
                    "type": "paragraph"
                })

            out_stream = io.BytesIO()
            new_doc.save(out_stream)

            return out_stream.getvalue(), {
                "total_paragraphs": len(raw_chunks),
                "total_tables": 0,
                "total_cells": 0,
                "translated_count": len(raw_chunks),
                "char_count": sum(len(c) for c in raw_chunks),
                "text_elements": text_elements
            }
