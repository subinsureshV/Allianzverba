import fitz  # PyMuPDF
import requests
import urllib.parse
import time
import re
import os
import json
from typing import List, Dict, Any, Tuple, Callable, Optional

try:
    from huggingface_hub import InferenceClient
    HAS_HF = True
except ImportError:
    HAS_HF = False

# Optional AI imports
try:
    import google.generativeai as genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

try:
    from deep_translator import GoogleTranslator
    HAS_DEEP_TRANSLATOR = True
except ImportError:
    HAS_DEEP_TRANSLATOR = False


class PDFTranslatorEngine:
    def __init__(self):
        self.delimiter = "\n[===DIV===]\n"

    def translate_gtx(self, text: str, target_lang: str = "en") -> str:
        """Free Google Translate GTX endpoint with retry and backoff."""
        if not text or not text.strip():
            return text
            
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl={target_lang}&dt=t&q={urllib.parse.quote(text)}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        }
        
        for attempt in range(3):
            try:
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    translated_segments = []
                    if data and isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
                        for seg in data[0]:
                            if seg and isinstance(seg, list) and len(seg) > 0 and isinstance(seg[0], str):
                                translated_segments.append(seg[0])
                    res_str = "".join(translated_segments)
                    if res_str:
                        return res_str
                elif resp.status_code == 429:
                    time.sleep(0.5 * (attempt + 1))
            except Exception:
                time.sleep(0.3)

        # Fallback to deep-translator if available
        if HAS_DEEP_TRANSLATOR:
            try:
                return GoogleTranslator(source='auto', target=target_lang).translate(text)
            except Exception:
                pass
                
        return text

    def translate_gemini(self, texts: List[str], api_key: str, target_lang: str = "English") -> List[str]:
        """Translate a batch of texts using Google Gemini API."""
        if not HAS_GEMINI or not api_key:
            return [self.translate_gtx(t, target_lang="en") for t in texts]
            
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            prompt = f"You are a professional document translator. Translate the following text segments into {target_lang}. Maintain exact order and format. Return the translations separated by the exact string '[===DIV===]'. Do not add commentary or extra markdown formatting.\n\n"
            prompt += self.delimiter.join(texts)
            
            response = model.generate_content(prompt)
            translated_raw = response.text.strip()
            parts = translated_raw.split("[===DIV===]")
            
            if len(parts) == len(texts):
                return [p.strip() for p in parts]
            else:
                # Fallback if split mismatch
                return [self.translate_gtx(t, target_lang="en") for t in texts]
        except Exception as e:
            print(f"Gemini translation failed: {e}")
            return [self.translate_gtx(t, target_lang="en") for t in texts]

    def translate_batch(
        self, 
        texts: List[str], 
        target_lang: str = "en", 
        method: str = "google_free", 
        api_key: str = None,
        progress_callback: Callable[[float, str], None] = None
    ) -> List[str]:
        """Batch translate a list of text segments with rate limit avoidance and progress tracking."""
        if not texts:
            return []

        translated_results = []
        total_items = len(texts)
        
        # If Gemini requested
        if method == "gemini" and api_key:
            chunk_size = 20
            for i in range(0, total_items, chunk_size):
                chunk = texts[i:i + chunk_size]
                if progress_callback:
                    progress_callback(min(i / total_items, 0.99), f"Translating items {i+1} to {min(i+chunk_size, total_items)} with Gemini AI...")
                res = self.translate_gemini(chunk, api_key, target_lang="English")
                translated_results.extend(res)
            return translated_results

        # Default Google Free with smart chunking
        current_chunk = []
        current_len = 0
        chunk_max_chars = 1200

        chunks_to_translate = []
        chunk_indices = []

        for idx, text in enumerate(texts):
            clean_text = text.strip()
            if not clean_text:
                translated_results.append("")
                continue
                
            if current_len + len(clean_text) > chunk_max_chars and current_chunk:
                chunks_to_translate.append((current_chunk, chunk_indices))
                current_chunk = []
                chunk_indices = []
                current_len = 0

            current_chunk.append(clean_text)
            chunk_indices.append(idx)
            current_len += len(clean_text) + len(self.delimiter)

        if current_chunk:
            chunks_to_translate.append((current_chunk, chunk_indices))

        translated_map = {}
        total_chunks = len(chunks_to_translate)

        for c_idx, (chunk, indices) in enumerate(chunks_to_translate):
            if progress_callback:
                pct = (c_idx / total_chunks) if total_chunks > 0 else 1.0
                progress_callback(pct, f"Translating text batch {c_idx + 1}/{total_chunks}...")

            combined = self.delimiter.join(chunk)
            translated_combined = self.translate_gtx(combined, target_lang=target_lang)
            
            # Split back
            parts = translated_combined.split("[===DIV===]")
            if len(parts) == len(chunk):
                for original_i, trans_p in zip(indices, parts):
                    translated_map[original_i] = trans_p.strip()
            else:
                # Fallback to single translate if delimiter got lost
                for original_i, item in zip(indices, chunk):
                    translated_map[original_i] = self.translate_gtx(item, target_lang=target_lang)
                    time.sleep(0.1)

            time.sleep(0.15)

        # Reconstruct final ordered list
        final_list = []
        for i in range(total_items):
            if i in translated_map:
                final_list.append(translated_map[i])
            else:
                final_list.append(texts[i])

        return final_list

    def map_font(self, font_name: str, is_bold: bool, is_italic: bool) -> str:
        """Map original PDF font family to standard PDF built-in fonts (helv/hebo/heit/hebi, times/tibo, couri/cobo)."""
        font_name_lower = font_name.lower() if font_name else ""
        
        if "courier" in font_name_lower or "code" in font_name_lower or "mono" in font_name_lower:
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
        api_key: str = None,
        progress_callback: Callable[[float, str], None] = None
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
                if b.get("type") == 0: # Text block
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
                        
                        # Extract flags
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
                            "align": 0 # Left align
                        })

        is_scanned = total_extracted_chars < 30
        
        if not all_text_elements:
            if progress_callback:
                progress_callback(1.0, "Completed PDF processing (no extractable text layer found).")
            return pdf_bytes, {
                "total_pages": total_pages,
                "translated_count": 0,
                "is_scanned": True,
                "char_count": total_extracted_chars,
                "text_elements": []
            }

        # Step 2: Translate all extracted text items
        if progress_callback:
            progress_callback(0.20, f"Translating {len(all_text_elements)} text elements into English...")

        raw_texts = [elem["original_text"] for elem in all_text_elements]
        
        def sub_progress(pct, msg):
            if progress_callback:
                overall_pct = 0.20 + (pct * 0.60)
                progress_callback(overall_pct, msg)

        translated_texts = self.translate_batch(
            raw_texts, 
            target_lang=target_lang, 
            method=method, 
            api_key=api_key,
            progress_callback=sub_progress
        )

        for idx, elem in enumerate(all_text_elements):
            elem["translated_text"] = translated_texts[idx]

        # Step 3: Redact original text & Insert translated text with dynamic font fitting
        if progress_callback:
            progress_callback(0.85, "Rebuilding PDF layout with exact element positioning...")

        for page_idx in range(total_pages):
            out_page = out_doc[page_idx]
            page_elements = [elem for elem in all_text_elements if elem["page_idx"] == page_idx]
            
            # Add redaction annotations to clear original text glyphs without destroying background art/images
            for elem in page_elements:
                r = elem["bbox"]
                out_page.add_redact_annot(r, fill=None)
                
            out_page.apply_redactions()
            
            # Insert translated text into exact bounding boxes
            VALID_FONTS = {"helv", "hebo", "heit", "hebi", "times", "tibo", "tiit", "tibi", "couri", "cobo", "coit", "cobi"}
            
            for elem in page_elements:
                bbox = elem["bbox"]
                trans_text = elem["translated_text"]
                if not trans_text or not trans_text.strip():
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
                        # Fallback to standard Helvetica if specific font variant fails
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
            "is_scanned": is_scanned,
            "char_count": total_extracted_chars,
            "text_elements": all_text_elements
        }
        
        return output_bytes, metadata

    # -----------------------------------------------------------------
    # Sanction & ESG Screening — Entity Name Extraction
    # -----------------------------------------------------------------

    # Keywords that signal each entity category. Order matters: first match wins per line.
    ENTITY_KEYWORDS: Dict[str, List[str]] = {
        "Additional Insured(s)": [
            r"additional\s+(?:named\s+)?insured", r"add(?:'|')l\s+insured",
            r"mitversicherte(?:r|n|s)?",
        ],
        "Insured / Named Insured": [
            r"(?:named\s+)?insured\b", r"policy\s*holder\b", r"assured\b",
            r"hauptversicherungsnehmer\b", r"versicherungsnehmer\b", r"versicherte(?:r|n|s)?\b",
        ],
        "Broker / Intermediary": [
            r"\bversicherungsmakler\b", r"\bmakler\b", r"broker\b", r"intermediary\b", r"producing\s+agent",
        ],
        "Insurer / Carrier": [
            r"insurer\b", r"carrier\b", r"underwriter\b", r"insurance\s+company",
            r"\berstversicherer\b", r"\bversicherer\b",
        ],
        "Reinsured": [
            r"reinsured\b", r"cedant\b", r"ceding\s+company", r"rückversicherte(?:r|n|s)?\b", r"zessionar\b",
        ],
        "Reinsurer": [
            r"reinsurer\b", r"reinsurance\s+company\b", r"reinsurance\b", r"rückversicherer\b",
        ],
        "Company / Organization": [
            r"company\s*name\b", r"corporation\b", r"organization\b",
            r"firm\s*name\b", r"entity\s*name\b", r"employer\b",
        ],
    }

    def _extract_full_text(self, pdf_bytes: bytes) -> str:
        """Return the full plain-text content of a PDF."""
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text_parts = []
        for page in doc:
            text_parts.append(page.get_text("text"))
        doc.close()
        return "\n".join(text_parts)

    def _clean_value(self, raw: str) -> str:
        """Strip common punctuation / label noise from an extracted value."""
        val = raw.strip()
        # Remove leading colon, dash, pipe, hash
        val = re.sub(r"^[\s:;\-–—|#]+", "", val)
        # Remove trailing punctuation except ()
        val = re.sub(r"[\s,;:]+$", "", val)
        val = val.strip()
        return val

    def _looks_like_entity_name(self, value: str) -> bool:
        """Reject policy prose and labels that were mistaken for organization names."""
        value = value.strip()
        if not value or len(value) > 120 or len(value.split()) > 10:
            return False
        normalized = re.sub(r"\s+", " ", value.lower()).strip(" .:-")
        # Headings and policy phrases commonly follow German party labels but
        # are not names. Reject them before applying the more general checks.
        german_non_names = {
            "risiken", "umfang", "personen/unternehmen", "unternehmen",
            "zusatzdeckungen", "versicherte risiken", "mitversicherte unternehmen",
        }
        if normalized in german_non_names or re.search(
            r"\b(?:ist|wahrgenommen|anweist|gewährt|sowie|allen|nachstehend|"
            r"aufgeführten|gegen|versicherungsschutz|dem|den|der|die|das)\b",
            normalized,
        ):
            return False
        if value.isupper() and len(value.split()) <= 3:
            return False
        # These words strongly indicate that the match came from explanatory
        # policy language (for example, "and everyone listed below") rather
        # than a name or an explicitly entered organization value.
        prose_words = {
            "and", "everyone", "listed", "below", "companies", "company's",
            "insurance", "protection", "against", "property", "damage",
            "coverage", "provide", "provides", "shall", "will", "under",
            "this", "the", "are", "is", "insured", "risks", "limit",
            "main", "insuranceee", "insurance", "additional", "named",
            "und", "sowie", "allen", "nachstehend", "aufgeführten",
            "unternehmen", "versicherungsschutz", "gegen", "sachschäden",
            "feuer", "explosion", "sturm", "hagel", "überschwemmung",
            "versicherungsnehmer", "jeweiligen", "umfang", "personen",
            "zusatzdeckungen", "entgegennahme", "seine", "gültigkeit", "gewährt",
        }
        tokens = {re.sub(r"[^a-z']", "", word.lower()) for word in value.split()}
        generic_values = {
            "insured", "named insured", "additional insured", "risks", "limit",
            "main insurance", "main insuranceee", "insurance", "company",
            "companies", "broker", "carrier", "insurer", "underwriter",
        }
        if normalized in generic_values:
            return False
        if re.search(r"\b(?:referenz|versicherungsschein|seite|nr\.?|nummer)\b", value, re.IGNORECASE):
            return False
        if len(tokens & prose_words) >= 2:
            return False
        # Ignore sentence-like extracts even when they happen to be short.
        if re.search(r"[.!?].+\S", value):
            return False
        return True

    def extract_policy_entities(self, pdf_bytes: bytes) -> Dict[str, List[str]]:
        """
        Scan the full text of a PDF and return a dict mapping each entity
        category (e.g. "Insured / Named Insured") to a deduplicated list
        of names / values found near the corresponding keywords.
        """
        full_text = self._extract_full_text(pdf_bytes)
        lines = full_text.splitlines()

        results: Dict[str, List[str]] = {cat: [] for cat in self.ENTITY_KEYWORDS}
        seen: Dict[str, set] = {cat: set() for cat in self.ENTITY_KEYWORDS}

        for idx, line in enumerate(lines):
            line_stripped = line.strip()
            if not line_stripped:
                continue

            for category, patterns in self.ENTITY_KEYWORDS.items():
                for pat in patterns:
                    match = re.search(pat, line_stripped, re.IGNORECASE)
                    if not match:
                        continue

                    # --- Strategy 1: grab text AFTER the keyword on the same line ---
                    after = line_stripped[match.end():]
                    value = self._clean_value(after)

                    # --- Strategy 2: if nothing useful after keyword, try the NEXT non-empty line ---
                    if len(value) < 3 and idx + 1 < len(lines):
                        next_line = lines[idx + 1].strip()
                        # Only use next line if it doesn't look like another label
                        if next_line and not re.search(r":\s*$", next_line):
                            value = self._clean_value(next_line)

                    if len(value) < 2 or not self._looks_like_entity_name(value):
                        continue

                    # Skip if value is just a number / date / generic word
                    if re.match(r"^[\d\s/\-\.]+$", value):
                        continue

                    norm = value.lower()
                    if norm not in seen[category]:
                        seen[category].add(norm)
                        results[category].append(value)

                    break  # first pattern match per line per category is enough

        return results

    # Display keys for Sanction & ESG Screening (Hugging Face extraction)
    SCREENING_FIELD_LABELS: Dict[str, str] = {
        "insured_names": "Insured Names",
        "additional_insured_names": "Additional Insured Names",
        "reinsured_names": "Reinsured Names",
        "broker_details": "Broker Details",
        "insurer_carrier": "Insurer / Carrier",
        "reinsurer_names": "Reinsurer Names",
    }

    def _truncate_for_llm(self, text: str, max_chars: int = 12_000) -> Tuple[str, bool]:
        text = text.strip()
        if len(text) <= max_chars:
            return text, False
        head = max_chars // 2
        tail = max_chars - head - 80
        return (
            text[:head]
            + "\n\n[... middle of document omitted for length ...]\n\n"
            + text[-tail:],
            True,
        )

    def _parse_json_from_llm(self, raw: str) -> Optional[Dict[str, Any]]:
        if not raw:
            return None
        raw = raw.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
        if fence:
            try:
                return json.loads(fence.group(1).strip())
            except json.JSONDecodeError:
                pass
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                pass
        return None

    BART_CNN_MODEL = "facebook/bart-large-cnn"

    def _is_bart_summarization_model(self, model_id: str) -> bool:
        mid = (model_id or "").lower()
        return "bart-large-cnn" in mid or mid == self.BART_CNN_MODEL

    def _summarization_text_from_response(self, response: Any) -> str:
        if response is None:
            return ""
        if isinstance(response, str):
            return response.strip()
        if isinstance(response, dict):
            return str(response.get("summary_text") or response.get("generated_text") or "").strip()
        if isinstance(response, list) and response:
            return self._summarization_text_from_response(response[0])
        summary_text = getattr(response, "summary_text", None)
        if summary_text:
            return str(summary_text).strip()
        return str(response).strip()

    def _summarize_with_bart_cnn(self, client: "InferenceClient", text: str) -> Tuple[str, bool]:
        """Summarize document text with facebook/bart-large-cnn (1024-token input limit)."""
        chunk_size = 3500
        max_chunks = 4
        chunks = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)][:max_chunks]
        truncated = len(text) > chunk_size * max_chunks

        summaries: List[str] = []
        for chunk in chunks:
            if not chunk.strip():
                continue
            response = client.summarization(
                chunk,
                parameters={
                    "max_length": 160,
                    "min_length": 30,
                    "do_sample": False,
                },
            )
            part = self._summarization_text_from_response(response)
            if part:
                summaries.append(part)

        if not summaries:
            return "", truncated
        if len(summaries) == 1:
            return summaries[0], truncated
        return " ".join(summaries), truncated

    def _entities_to_screening_fields(self, entities: Dict[str, List[str]]) -> Dict[str, List[str]]:
        category_map = {
            "Insured / Named Insured": "insured_names",
            "Additional Insured(s)": "additional_insured_names",
            "Broker / Intermediary": "broker_details",
            "Insurer / Carrier": "insurer_carrier",
            "Reinsured": "reinsured_names",
            "Reinsurer": "reinsurer_names",
        }
        out: Dict[str, List[str]] = {key: [] for key in self.SCREENING_FIELD_LABELS}
        seen: Dict[str, set] = {key: set() for key in self.SCREENING_FIELD_LABELS}

        for category, names in entities.items():
            field = category_map.get(category)
            if not field:
                continue
            for name in names:
                norm = name.lower()
                if norm in seen[field]:
                    continue
                seen[field].add(norm)
                out[field].append(name)

        return out

    def _normalize_screening_result(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure all screening keys exist as string lists plus optional summary."""
        out: Dict[str, Any] = {"summary": ""}
        for key in self.SCREENING_FIELD_LABELS:
            val = data.get(key, [])
            if val is None:
                val = []
            if isinstance(val, str):
                val = [val.strip()] if val.strip() else []
            elif isinstance(val, dict):
                parts = [f"{k}: {v}" for k, v in val.items() if v]
                val = parts
            elif not isinstance(val, list):
                val = [str(val)]
            cleaned: List[str] = []
            seen = set()
            for item in val:
                s = str(item).strip()
                if not s or s.lower() in seen:
                    continue
                seen.add(s.lower())
                cleaned.append(s)
            out[key] = cleaned
        summary = data.get("summary") or data.get("document_summary") or ""
        out["summary"] = str(summary).strip()
        return out

    def extract_policy_screening_hf(
        self,
        pdf_bytes: bytes,
        hf_token: str,
        model_id: str = "facebook/bart-large-cnn",
    ) -> Dict[str, Any]:
        from policy_screening import extract_policy_screening_hf as run_screening

        return run_screening(self, pdf_bytes, hf_token, model_id)

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
