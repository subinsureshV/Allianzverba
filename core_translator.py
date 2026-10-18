"""Core translation services for AllianzVerba.
Provides robust text translation via Google Free (GTX/deep-translator) and Google Gemini AI.
"""

import time
import urllib.parse
from typing import List, Dict, Optional
import requests

try:
    from deep_translator import GoogleTranslator
    HAS_DEEP_TRANSLATOR = True
except ImportError:
    HAS_DEEP_TRANSLATOR = False

try:
    import google.generativeai as genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

LANGUAGE_MAP: Dict[str, str] = {
    "English": "en",
    "Spanish": "es",
    "French": "fr",
    "German": "de",
    "Chinese (Simplified)": "zh-CN",
    "Japanese": "ja",
    "Italian": "it",
    "Portuguese": "pt",
    "Russian": "ru",
    "Arabic": "ar",
    "Hindi": "hi",
    "Korean": "ko",
    "Dutch": "nl",
    "Turkish": "tr",
    "Polish": "pl",
    "Swedish": "sv",
}

DELIMITER = "\n[===DIV===]\n"


def translate_gtx_single(text: str, target_lang: str = "en") -> str:
    """Translates a single text string using Google Translate GTX endpoint with retry & backoff."""
    if not text or not text.strip():
        return text

    url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl={target_lang}&dt=t&q={urllib.parse.quote(text)}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
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
            return GoogleTranslator(source="auto", target=target_lang).translate(text)
        except Exception:
            pass

    return text


def translate_gemini_batch(
    texts: List[str],
    api_key: str,
    target_lang: str = "en"
) -> List[str]:
    """Translates a batch of texts using Google Gemini API."""
    if not HAS_GEMINI or not api_key:
        return [translate_gtx_single(t, target_lang=target_lang) for t in texts]

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        # Map language code to full language name if known
        target_name = target_lang
        for name, code in LANGUAGE_MAP.items():
            if code == target_lang:
                target_name = name
                break

        prompt = (
            f"You are a professional document translator. Translate the following text segments into {target_name}. "
            f"Maintain exact order, capitalization, numbers, and meaning. "
            f"Return the translations separated by the exact delimiter string '{DELIMITER.strip()}'. "
            f"Do not add any commentary, extra markdown fences, or notes.\n\n"
        )
        prompt += DELIMITER.join(texts)

        response = model.generate_content(prompt)
        translated_raw = response.text.strip()
        parts = translated_raw.split(DELIMITER.strip())

        if len(parts) == len(texts):
            return [p.strip() for p in parts]
        else:
            return [translate_gtx_single(t, target_lang=target_lang) for t in texts]
    except Exception as e:
        print(f"Gemini translation failed: {e}")
        return [translate_gtx_single(t, target_lang=target_lang) for t in texts]


def translate_batch(
    texts: List[str],
    target_lang: str = "en",
    method: str = "google_free",
    api_key: Optional[str] = None,
    batch_size: int = 25
) -> List[str]:
    """
    Translates a list of strings efficiently in batches.
    Maintains 1-to-1 correspondence with the input list.
    """
    if not texts:
        return []

    # Map empty strings to preserve index
    results: List[str] = [""] * len(texts)
    non_empty_indices = [i for i, t in enumerate(texts) if t and t.strip()]

    if not non_empty_indices:
        return results

    if method == "gemini" and api_key:
        # Process in batches with Gemini
        for i in range(0, len(non_empty_indices), batch_size):
            chunk_indices = non_empty_indices[i : i + batch_size]
            chunk_texts = [texts[idx] for idx in chunk_indices]
            trans_chunk = translate_gemini_batch(chunk_texts, api_key, target_lang=target_lang)
            for idx, trans in zip(chunk_indices, trans_chunk):
                results[idx] = trans
        return results

    # Free Google Translate batching using DELIMITER
    for i in range(0, len(non_empty_indices), batch_size):
        chunk_indices = non_empty_indices[i : i + batch_size]
        chunk_texts = [texts[idx] for idx in chunk_indices]

        # Combine into batch with delimiter
        combined_payload = DELIMITER.join(chunk_texts)
        translated_payload = translate_gtx_single(combined_payload, target_lang=target_lang)
        segments = translated_payload.split(DELIMITER.strip())

        if len(segments) == len(chunk_texts):
            for idx, seg in zip(chunk_indices, segments):
                results[idx] = seg.strip()
        else:
            # Fallback to single translations if delimiter was eaten or mangled
            for idx, orig in zip(chunk_indices, chunk_texts):
                results[idx] = translate_gtx_single(orig, target_lang=target_lang)

    return results
