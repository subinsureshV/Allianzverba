"""Sanction & ESG screening — loaded separately so Streamlit picks up updates reliably."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

try:
    from huggingface_hub import InferenceClient
    HAS_HF = True
except ImportError:
    HAS_HF = False

if TYPE_CHECKING:
    from pdf_translator import PDFTranslatorEngine

BART_CNN_MODEL = "facebook/bart-large-cnn"

SCREENING_FIELD_LABELS: Dict[str, str] = {
    "insured_names": "Insured Names",
    "additional_insured_names": "Additional Insured Names",
    "reinsured_names": "Reinsured Names",
    "broker_details": "Broker Details",
    "insurer_carrier": "Insurer / Carrier",
    "reinsurer_names": "Reinsurer Names",
}


def _truncate_for_llm(text: str, max_chars: int = 12_000) -> Tuple[str, bool]:
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


def _parse_json_from_llm(raw: str) -> Optional[Dict[str, Any]]:
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


def _is_bart_summarization_model(model_id: str) -> bool:
    mid = (model_id or "").lower()
    return "bart-large-cnn" in mid or mid == BART_CNN_MODEL


def _summarization_text_from_response(response: Any) -> str:
    if response is None:
        return ""
    if isinstance(response, str):
        return response.strip()
    if isinstance(response, dict):
        return str(response.get("summary_text") or response.get("generated_text") or "").strip()
    if isinstance(response, list) and response:
        return _summarization_text_from_response(response[0])
    summary_text = getattr(response, "summary_text", None)
    if summary_text:
        return str(summary_text).strip()
    return str(response).strip()


def _summarize_with_bart_cnn(client: InferenceClient, text: str) -> Tuple[str, bool]:
    # BART's encoder accepts at most 1,024 tokens. Character-based chunks can
    # exceed that limit for PDFs with dense labels, codes, or unusual spacing.
    # Limit each request by words instead so it stays safely below the limit.
    # German compound words can expand to several BART tokens, so keep the
    # segment size conservative for multilingual policy documents.
    chunk_size = 100
    max_chunks = 12
    words = text.split()
    chunks = [" ".join(words[i : i + chunk_size]) for i in range(0, len(words), chunk_size)][:max_chunks]
    truncated = len(words) > chunk_size * max_chunks

    summaries: List[str] = []
    for chunk in chunks:
        if not chunk.strip():
            continue
        # The hosted BART endpoint rejects generation settings nested under
        # ``generate_parameters``. Its default summarization settings are used
        # here so the request remains compatible with the current API.
        response = client.summarization(chunk)
        part = _summarization_text_from_response(response)
        if part:
            summaries.append(part)

    if not summaries:
        return "", truncated
    if len(summaries) == 1:
        return summaries[0], truncated
    return " ".join(summaries), truncated


def _entities_to_screening_fields(entities: Dict[str, List[str]]) -> Dict[str, List[str]]:
    category_map = {
        "Insured / Named Insured": "insured_names",
        "Additional Insured(s)": "additional_insured_names",
        "Broker / Intermediary": "broker_details",
        "Insurer / Carrier": "insurer_carrier",
        "Reinsured": "reinsured_names",
        "Reinsurer": "reinsurer_names",
    }
    out: Dict[str, List[str]] = {key: [] for key in SCREENING_FIELD_LABELS}
    seen: Dict[str, set] = {key: set() for key in SCREENING_FIELD_LABELS}

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


def _normalize_screening_result(data: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"summary": ""}
    for key in SCREENING_FIELD_LABELS:
        val = data.get(key, [])
        if val is None:
            val = []
        if isinstance(val, str):
            val = [val.strip()] if val.strip() else []
        elif isinstance(val, dict):
            val = [f"{k}: {v}" for k, v in val.items() if v]
        elif not isinstance(val, list):
            val = [str(val)]
        cleaned: List[str] = []
        seen: set = set()
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
    engine: "PDFTranslatorEngine",
    pdf_bytes: bytes,
    hf_token: str,
    model_id: str = BART_CNN_MODEL,
) -> Dict[str, Any]:
    if not hf_token or not hf_token.strip():
        raise ValueError("Hugging Face token is required.")
    if not HAS_HF:
        raise RuntimeError("huggingface_hub is not installed. Run: pip install huggingface_hub")

    full_text = engine._extract_full_text(pdf_bytes)
    if not full_text.strip():
        empty = _normalize_screening_result({})
        empty["summary"] = "No extractable text found in this PDF."
        empty["truncated"] = False
        empty["model_id"] = model_id
        return empty

    client = InferenceClient(model=model_id, token=hf_token.strip(), provider="hf-inference")

    if _is_bart_summarization_model(model_id):
        summary, truncated = _summarize_with_bart_cnn(client, full_text)
        entities = engine.extract_policy_entities(pdf_bytes)
        screening_data = _entities_to_screening_fields(entities)
        screening_data["summary"] = summary or "Not found"
        result = _normalize_screening_result(screening_data)
        result["truncated"] = truncated
        result["model_id"] = model_id
        return result

    doc_text, truncated = _truncate_for_llm(full_text)
    field_lines = "\n".join(f'- "{key}": array of strings' for key in SCREENING_FIELD_LABELS)
    prompt = f"""You are an insurance document analyst. Read the PDF text below and respond with ONLY one JSON object (no markdown, no commentary).

Required JSON keys:
- "summary": string, 2-4 sentences describing the document (coverage type, parties, key dates if present)
{field_lines}

Rules:
- Extract exact organization/person names as written in the document.
- For broker_details include name and any email, phone, or address on the same line if present.
- Use an empty array [] when a category is not mentioned in the document.
- Do not invent names.

Document text:
{doc_text}
"""

    raw_response = ""
    chat = client.chat_completion(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1200,
        temperature=0.1,
    )
    raw_response = chat.choices[0].message.content or ""

    parsed = _parse_json_from_llm(raw_response)
    if not parsed:
        raise ValueError(
            "Could not parse structured response from the model. "
            "Try BART Large CNN or check your Hugging Face token permissions."
        )

    result = _normalize_screening_result(parsed)
    result["truncated"] = truncated
    result["model_id"] = model_id
    return result
