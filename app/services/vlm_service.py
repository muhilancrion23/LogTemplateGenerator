"""
VLM Service — Google Gemini 2.0 Flash (free tier).

SDK     : google-genai >= 2.0   (pip install google-genai)
Model   : gemini-2.5-flash
Free tier: 10 RPM · 500 req/day (May 2026) — was 15 RPM · 1 500 req/day · 1 M TPM

NOTE: this uses the NEW 'google-genai' SDK (google.genai),
NOT the old 'google-generativeai' SDK (google.generativeai).
They are different packages with different APIs.

Setup:
  pip install google-genai pillow
  export GEMINI_API_KEY="your-key"   # https://aistudio.google.com/app/apikey
"""
import logging
import os
import time
from pathlib import Path

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

_MODEL      = "gemini-2.5-flash"
_MAX_RETRY  = 3
_RETRY_WAIT = 5   # seconds

_PROMPT = """\
You are an industrial parameter extraction AI.
Analyse this document and extract ALL measurable product/quality parameters.

Return ONLY this JSON — no markdown, no explanation, nothing else:
{"parameters":[{"asset":"","description":"<name + unit>","type":"number","required":true,"default_value":"","setpoints":{"min":<number or null>,"max":<number or null>}}]}

EXTRACT: pH, density, moisture, viscosity, temperature, pressure, concentration,
acidity, hardness, purity, fat/protein/sugar content, microbial counts, shelf life,
particle size, colour values, and any other measured quantity with a numeric spec.

IGNORE: company names, logos, addresses, dates, batch numbers, signatures,
revision numbers, barcodes, transport details, page numbers.

Rules:
1. Raw JSON only — no markdown fences, no preamble.
2. "asset" is always "".
3. boolean params (pass/fail, yes/no) -> "type":"boolean", setpoints null/null.
4. free-text params -> "type":"text", setpoints null/null.
5. Deduplicate across pages — include each parameter once.
6. No params found -> {"parameters":[]}
"""

# ── Client singleton ──────────────────────────────────────────────────────────

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. "
                "Get a free key at https://aistudio.google.com/app/apikey"
            )
        _client = genai.Client(api_key=api_key)
        logger.info("Gemini client ready (model: %s)", _MODEL)
    return _client


# ── Inference helpers ─────────────────────────────────────────────────────────

def _call_with_retry(contents) -> str:
    """Run generate_content with retry on transient errors."""
    client = _get_client()
    for attempt in range(1, _MAX_RETRY + 1):
        try:
            response = client.models.generate_content(
                model=_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=4096,
                ),
            )
            text = response.text.strip()
            logger.info("Gemini output (first 400 chars): %s", text[:400])
            return text
        except Exception as err:
            logger.warning("Gemini attempt %d/%d failed: %s", attempt, _MAX_RETRY, err)
            if attempt < _MAX_RETRY:
                time.sleep(_RETRY_WAIT)
            else:
                raise RuntimeError(
                    f"Gemini failed after {_MAX_RETRY} attempts: {err}"
                ) from err
    return '{"parameters":[]}'


def _run_images(image_paths: list[str]) -> str:
    """Send all page images in one request."""
    parts = []
    for path in image_paths:
        suffix = Path(path).suffix.lower()
        mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(suffix, "image/png")
        with open(path, "rb") as f:
            data = f.read()
        parts.append(types.Part.from_bytes(data=data, mime_type=mime))
    parts.append(_PROMPT)
    return _call_with_retry(parts)


def _run_pdf(pdf_path: str) -> str:
    """Upload PDF via File API and send in one request."""
    client = _get_client()
    logger.info("Uploading PDF to Gemini File API: %s", pdf_path)

    uploaded = client.files.upload(
        file=pdf_path,
        config=types.UploadFileConfig(mime_type="application/pdf"),
    )
    try:
        result = _call_with_retry([uploaded, _PROMPT])
    finally:
        try:
            client.files.delete(name=uploaded.name)
        except Exception:
            pass
    return result


# ── Public interface ──────────────────────────────────────────────────────────

class VLMService:
    """Drop-in replacement — same public contract as the original."""

    @staticmethod
    def extract_parameters(image_paths: list[str]) -> str:
        """Extract from a list of image paths (one per PDF page)."""
        if not image_paths:
            raise ValueError("No image paths provided.")
        logger.info("extract_parameters: %d image(s)", len(image_paths))
        return _run_images(image_paths)

    @staticmethod
    def extract_parameters_from_pdf(pdf_path: str) -> str:
        """Send the raw PDF directly to Gemini (preferred — 1 API call)."""
        return _run_pdf(pdf_path)