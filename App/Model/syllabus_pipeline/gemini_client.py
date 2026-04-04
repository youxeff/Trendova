import base64
import json
import re
import time
from pathlib import Path
from typing import List

import pdfplumber
import requests

from .gemini_prompts import build_pdf_prompt, build_text_prompt


def extract_pdf_text(pdf_path: str, max_chars: int = 140000) -> str:
    chunks: List[str] = []
    total = 0

    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages, start=1):
            page_text = (page.extract_text() or "").strip()
            if not page_text:
                continue

            labeled = f"\n\n=== PAGE {page_idx} ===\n{page_text}"
            total += len(labeled)
            if total > max_chars:
                remaining = max(0, max_chars - (total - len(labeled)))
                chunks.append(labeled[:remaining])
                break
            chunks.append(labeled)

    return "".join(chunks).strip()


def _extract_json_array_from_text(text: str) -> List[List[str]]:
    content = text.strip()

    fenced = re.search(r"```(?:json)?\\s*(\\[.*\\])\\s*```", content, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        content = fenced.group(1).strip()

    if not content.startswith("["):
        bracketed = re.search(r"\\[.*\\]", content, flags=re.DOTALL)
        if bracketed:
            content = bracketed.group(0)

    parsed = json.loads(content)
    if not isinstance(parsed, list):
        return []

    normalized_rows: List[List[str]] = []
    for item in parsed:
        if isinstance(item, list):
            row = ["" if value is None else str(value) for value in item]
        elif isinstance(item, dict):
            row = [
                str(item.get("Subject", item.get("subject", ""))),
                str(item.get("Date", item.get("date", ""))),
                str(item.get("Time", item.get("time", ""))),
                str(item.get("Type", item.get("type", item.get("assignment_type", "")))),
                str(item.get("TimeGiven", item.get("time_given", ""))),
                str(item.get("Location", item.get("location", ""))),
                str(item.get("Page", item.get("page", ""))),
                str(item.get("SourceText", item.get("source_text", ""))),
            ]
        else:
            continue

        if len(row) < 8:
            row.extend([""] * (8 - len(row)))
        elif len(row) > 8:
            row = row[:8]

        normalized_rows.append(row)

    return normalized_rows


def extract_deadlines_with_gemini(
    pdf_path: str,
    api_key: str,
    model: str = "gemini-3-flash-preview",
    max_chars: int = 140000,
    retries: int = 3,
) -> List[List[str]]:
    if not api_key:
        raise ValueError("Gemini API key is required")

    pdf_file = Path(pdf_path)
    if not pdf_file.exists() or not pdf_file.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_file}")

    text = extract_pdf_text(str(pdf_file), max_chars=max_chars)

    if text:
        payload = {
            "contents": [{"parts": [{"text": build_text_prompt(text)}]}],
            "generationConfig": {"temperature": 0.1},
        }
    else:
        with open(pdf_file, "rb") as file_handle:
            pdf_b64 = base64.b64encode(file_handle.read()).decode("utf-8")

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": build_pdf_prompt()},
                        {
                            "inline_data": {
                                "mime_type": "application/pdf",
                                "data": pdf_b64,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {"temperature": 0.1},
        }

    data = None
    last_error = None

    for api_version in ["v1beta", "v1"]:
        url = (
            f"https://generativelanguage.googleapis.com/{api_version}/models/"
            f"{model}:generateContent?key={api_key}"
        )
        try:
            for attempt in range(retries):
                response = requests.post(url, json=payload, timeout=180)
                if response.status_code == 503 and attempt < retries - 1:
                    time.sleep(2 + attempt)
                    continue

                if response.status_code == 404:
                    last_error = f"404 for model '{model}' on {api_version}"
                    break

                if response.status_code >= 400:
                    try:
                        err = response.json()
                    except Exception:
                        err = response.text
                    last_error = f"HTTP {response.status_code} on {api_version}/{model}: {err}"
                    break

                data = response.json()
                break

            if data is not None:
                break
        except requests.RequestException as exc:
            last_error = str(exc)
            continue

    if data is None:
        raise RuntimeError(f"Gemini request failed. Last error: {last_error}")

    candidates = data.get("candidates", [])
    if not candidates:
        return []

    parts = candidates[0].get("content", {}).get("parts", [])
    combined = "\n".join(part.get("text", "") for part in parts if isinstance(part, dict))
    if not combined.strip():
        return []

    return _extract_json_array_from_text(combined)


def extract_deadlines_from_text_with_gemini(
    text: str,
    api_key: str,
    model: str = "gemini-3-flash-preview",
    retries: int = 3,
) -> List[List[str]]:
    if not api_key:
        raise ValueError("Gemini API key is required")

    if not text or not text.strip():
        return []

    payload = {
        "contents": [{"parts": [{"text": build_text_prompt(text)}]}],
        "generationConfig": {"temperature": 0.1},
    }

    data = None
    last_error = None

    for api_version in ["v1beta", "v1"]:
        url = (
            f"https://generativelanguage.googleapis.com/{api_version}/models/"
            f"{model}:generateContent?key={api_key}"
        )
        try:
            for attempt in range(retries):
                response = requests.post(url, json=payload, timeout=180)
                if response.status_code == 503 and attempt < retries - 1:
                    time.sleep(2 + attempt)
                    continue

                if response.status_code == 404:
                    last_error = f"404 for model '{model}' on {api_version}"
                    break

                if response.status_code >= 400:
                    try:
                        err = response.json()
                    except Exception:
                        err = response.text
                    last_error = f"HTTP {response.status_code} on {api_version}/{model}: {err}"
                    break

                data = response.json()
                break

            if data is not None:
                break
        except requests.RequestException as exc:
            last_error = str(exc)
            continue

    if data is None:
        raise RuntimeError(f"Gemini request failed. Last error: {last_error}")

    candidates = data.get("candidates", [])
    if not candidates:
        return []

    parts = candidates[0].get("content", {}).get("parts", [])
    combined = "\n".join(part.get("text", "") for part in parts if isinstance(part, dict))
    if not combined.strip():
        return []

    return _extract_json_array_from_text(combined)
