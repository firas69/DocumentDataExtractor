from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from .warnings import ExtractionWarning


CURRENCY_CODES = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "TND": "TND",
    "USD": "USD",
    "EUR": "EUR",
}

CURRENCY_SYMBOLS = {"$", "€", "£"}


def normalize_string(value: Any, collapse_spaces: bool = True, trim: bool = True) -> str:
    text = "" if value is None else str(value)
    if collapse_spaces:
        text = re.sub(r"\s+", " ", text)
    if trim:
        text = text.strip()
    text = re.sub(r"^#\s+", "", text)
    return text


def normalize_number(value: Any) -> int | float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return value
    text = str(value).strip()
    if not text:
        return None
    money_tokens = re.findall(r"[$€£]\s*\d[\d\s.,]*", text)
    if money_tokens:
        text = money_tokens[0]
    text = re.sub(r"(USD|EUR|TND|GBP)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[$€£]", "", text)
    text = re.sub(r"\b(lbs?|pounds?|kg|kgs)\b", "", text, flags=re.IGNORECASE)
    text = text.replace(" ", "")

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        parts = text.split(",")
        if len(parts[-1]) == 2:
            text = "".join(parts[:-1]).replace(",", "") + "." + parts[-1]
        else:
            text = text.replace(",", "")

    try:
        number = float(text)
    except ValueError:
        return None
    return int(number) if number.is_integer() else number


def normalize_date(value: Any) -> tuple[str | None, ExtractionWarning | None]:
    if value is None:
        return None, None
    text = normalize_string(value)
    if not text:
        return None, None
    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d-%m-%Y",
        "%B %d, %Y",
        "%b %d, %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date().isoformat(), None
        except ValueError:
            continue
    return text, ExtractionWarning(
        code="date_uncertain",
        message=f"Could not confidently normalize date value {text!r}",
    )


def detect_currency(value: Any) -> str | None:
    text = normalize_string(value).upper()
    for token, code in CURRENCY_CODES.items():
        if token.upper() in text:
            return code
    return None


def normalize_currency(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "amount": normalize_number(value),
        "currency": detect_currency(value),
    }


def normalize_currency_code(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("currency") or value.get("amount")
    detected = detect_currency(value)
    if detected:
        return detected
    text = normalize_string(value).upper()
    return CURRENCY_CODES.get(text)


def normalize_value(value: Any, data_type: str, options: dict[str, Any] | None = None) -> tuple[Any, list[ExtractionWarning]]:
    warnings: list[ExtractionWarning] = []
    options = options or {}
    normalized_type = data_type.casefold()
    if value is None:
        return None, warnings
    if normalized_type in {"number", "weight"}:
        return normalize_number(value), warnings
    if normalized_type == "date":
        normalized, warning = normalize_date(value)
        if warning:
            warnings.append(warning)
        return normalized, warnings
    if normalized_type in {"currency", "money"}:
        return normalize_currency(value), warnings
    if normalized_type == "currency_code":
        return normalize_currency_code(value), warnings
    if normalized_type in {"array", "table"}:
        return value, warnings
    return normalize_string(
        value,
        collapse_spaces=options.get("collapse_spaces", True),
        trim=options.get("trim", True),
    ), warnings
