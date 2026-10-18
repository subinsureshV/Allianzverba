"""Image (PNG & JPEG/JPG) translation engine.
Extracts text via neural OCR (EasyOCR), translates text in batches,
and inlays translated text over the original image preserving background,
coordinates, typography, and visual layout.
"""

import io
import os
import sys
from typing import List, Dict, Any, Tuple, Callable, Optional
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from core_translator import translate_batch, translate_gtx_single

# Ensure Windows unicode prints do not crash
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Global cached EasyOCR reader
_GLOBAL_READER = None


def get_easyocr_reader(lang_codes: List[str] = None):
    """Lazy initialize and cache EasyOCR reader."""
    global _GLOBAL_READER
    if _GLOBAL_READER is None:
        import easyocr
        # Multilingual English reader handles Latin, German, French, Spanish, etc.
        _GLOBAL_READER = easyocr.Reader(["en"], gpu=False, verbose=False)
    return _GLOBAL_READER


def get_system_font(size: int = 14) -> ImageFont.FreeTypeFont:
    """Find a standard TrueType font on Windows, with fallback to default."""
    candidates = [
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\calibri.ttf",
        r"C:\Windows\Fonts\tahoma.ttf",
    ]
    for font_path in candidates:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size=size)
            except Exception:
                continue
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def sample_background_color(image: Image.Image, box: Tuple[int, int, int, int]) -> Tuple[int, int, int]:
    """Sample background color from pixels surrounding the bounding box."""
    x0, y0, x1, y1 = box
    w, h = image.size
    samples = []

    # Sample top edge
    if y0 > 2:
        for x in range(max(0, x0), min(w, x1), 4):
            samples.append(image.getpixel((x, max(0, y0 - 2))))
    # Sample bottom edge
    if y1 < h - 2:
        for x in range(max(0, x0), min(w, x1), 4):
            samples.append(image.getpixel((x, min(h - 1, y1 + 2))))
    # Sample left edge
    if x0 > 2:
        for y in range(max(0, y0), min(h, y1), 4):
            samples.append(image.getpixel((max(0, x0 - 2), y)))
    # Sample right edge
    if x1 < w - 2:
        for y in range(max(0, y0), min(h, y1), 4):
            samples.append(image.getpixel((min(w - 1, x1 + 2), y)))

    if not samples:
        # Fallback to white
        return (255, 255, 255)

    # Convert to RGB if RGBA
    rgb_samples = [s[:3] for s in samples]
    med_r = int(np.median([s[0] for s in rgb_samples]))
    med_g = int(np.median([s[1] for s in rgb_samples]))
    med_b = int(np.median([s[2] for s in rgb_samples]))
    return (med_r, med_g, med_b)


class ImageTranslatorEngine:
    def __init__(self):
        pass

    def translate_image_bytes(
        self,
        image_bytes: bytes,
        target_lang: str = "en",
        method: str = "google_free",
        api_key: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Tuple[bytes, Dict[str, Any], bytes, bytes]:
        """
        Translates a PNG or JPEG image.
        Detects text with EasyOCR, translates strings,
        cleans original text regions, inlays translated text,
        and returns (translated_image_bytes, metadata, orig_png_bytes, trans_png_bytes).
        """
        # Load image
        orig_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        width, height = orig_img.size

        # Buffer original image as PNG for preview
        orig_buf = io.BytesIO()
        orig_img.save(orig_buf, format="PNG")
        orig_preview_bytes = orig_buf.getvalue()

        if progress_callback:
            progress_callback(0.1, f"Scanning image ({width}x{height}) with neural OCR engine...")

        # Run OCR
        reader = get_easyocr_reader()
        img_np = np.array(orig_img)
        raw_ocr_results = reader.readtext(img_np)

        elements = []
        for item in raw_ocr_results:
            bbox_pts, text, conf = item
            text = text.strip()
            if not text or conf < 0.2:
                continue

            xs = [pt[0] for pt in bbox_pts]
            ys = [pt[1] for pt in bbox_pts]
            x_min = max(0, int(min(xs)))
            x_max = min(width, int(max(xs)))
            y_min = max(0, int(min(ys)))
            y_max = min(height, int(max(ys)))

            if (x_max - x_min) < 6 or (y_max - y_min) < 6:
                continue

            elements.append({
                "bbox": (x_min, y_min, x_max, y_max),
                "original_text": text,
                "confidence": float(conf)
            })

        total_extracted_chars = sum(len(e["original_text"]) for e in elements)

        if not elements:
            if progress_callback:
                progress_callback(1.0, "Completed image analysis (no text detected).")
            return image_bytes, {
                "dimensions": f"{width} x {height} px",
                "translated_count": 0,
                "char_count": 0,
                "text_elements": []
            }, orig_preview_bytes, orig_preview_bytes

        # Batch translate text
        if progress_callback:
            progress_callback(0.35, f"Translating {len(elements)} detected text blocks to {target_lang}...")

        raw_strings = [e["original_text"] for e in elements]
        translated_strings = translate_batch(
            raw_strings,
            target_lang=target_lang,
            method=method,
            api_key=api_key,
            batch_size=25
        )

        for e, trans in zip(elements, translated_strings):
            e["translated_text"] = trans

        # Inlay translated text into image
        if progress_callback:
            progress_callback(0.7, "Inlaying translated typography with background synthesis...")

        out_img = orig_img.copy()
        draw = ImageDraw.Draw(out_img)

        for e in elements:
            box = e["bbox"]
            trans_text = e.get("translated_text", "")
            if not trans_text:
                continue

            x0, y0, x1, y1 = box
            box_w = x1 - x0
            box_h = y1 - y0

            # 1. Background sampling and clearing
            bg_color = sample_background_color(orig_img, box)
            # Expand box slightly to clear anti-aliased font halos
            pad_x = min(3, max(1, box_w // 20))
            pad_y = min(3, max(1, box_h // 20))
            draw.rectangle(
                [max(0, x0 - pad_x), max(0, y0 - pad_y), min(width, x1 + pad_x), min(height, y1 + pad_y)],
                fill=bg_color
            )

            # 2. Text contrast calculation (Luminance)
            luminance = 0.299 * bg_color[0] + 0.587 * bg_color[1] + 0.114 * bg_color[2]
            text_color = (20, 20, 20) if luminance > 135 else (245, 245, 245)

            # 3. Dynamic font scaling
            target_font_size = max(10, int(box_h * 0.8))
            font = get_system_font(target_font_size)

            # Check if text fits inside box width; scale down if necessary
            cur_size = target_font_size
            min_size = max(8, int(target_font_size * 0.45))

            while cur_size >= min_size:
                font = get_system_font(cur_size)
                try:
                    text_bbox = draw.textbbox((x0, y0), trans_text, font=font)
                    text_w = text_bbox[2] - text_bbox[0]
                    text_h = text_bbox[3] - text_bbox[1]
                    if text_w <= box_w + 4 and text_h <= box_h + 4:
                        break
                except Exception:
                    break
                cur_size -= 1

            # Draw translated text centered vertically in box
            try:
                draw.text((x0, y0), trans_text, fill=text_color, font=font)
            except Exception:
                draw.text((x0, y0), trans_text, fill=text_color)

        # Save translated image
        trans_buf = io.BytesIO()
        out_img.save(trans_buf, format="PNG")
        trans_preview_bytes = trans_buf.getvalue()

        if progress_callback:
            progress_callback(1.0, "Translation complete! Image layout preserved.")

        metadata = {
            "dimensions": f"{width} x {height} px",
            "translated_count": len(elements),
            "char_count": total_extracted_chars,
            "text_elements": [
                {
                    "location": f"Box [{e['bbox'][0]}, {e['bbox'][1]}]",
                    "original_text": e["original_text"],
                    "translated_text": e["translated_text"],
                    "confidence": f"{int(e['confidence'] * 100)}%"
                }
                for e in elements
            ]
        }

        return trans_preview_bytes, metadata, orig_preview_bytes, trans_preview_bytes

    def convert_image_to_pdf_bytes(self, image_bytes: bytes) -> bytes:
        """Converts image bytes to a single-page PDF document bytes."""
        import fitz
        img = Image.open(io.BytesIO(image_bytes))
        doc = fitz.open()
        rect = fitz.Rect(0, 0, img.width, img.height)
        page = doc.new_page(width=img.width, height=img.height)
        page.insert_image(rect, stream=image_bytes)
        pdf_bytes = doc.tobytes(deflate=True)
        doc.close()
        return pdf_bytes
