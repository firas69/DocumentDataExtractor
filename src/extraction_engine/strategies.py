from __future__ import annotations

import re
from collections.abc import Iterable

from .models import NormalizedDocument, NormalizedLine


def get_lines(document: NormalizedDocument) -> list[NormalizedLine]:
    lines: list[NormalizedLine] = []
    for page in sorted(document.pages, key=lambda page: page.page_number):
        page_lines = sorted(page.lines, key=lambda line: line.line_number)
        lines.extend(page_lines)
    if lines:
        return lines
    if document.full_text:
        return [
            NormalizedLine(line_number=index + 1, text=text)
            for index, text in enumerate(document.full_text.splitlines())
        ]
    return []


def get_full_text(document: NormalizedDocument) -> str:
    if document.full_text:
        return document.full_text
    lines = get_lines(document)
    if lines:
        return "\n".join(line.text for line in lines)
    return "\n".join(page.text for page in document.pages if page.text)


def normalize_for_search(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def label_in_text(text: str, labels: Iterable[str]) -> str | None:
    lowered = normalize_for_search(text)
    for label in labels:
        normalized_label = normalize_for_search(label)
        if not normalized_label:
            continue
        if len(normalized_label) <= 2:
            if lowered == normalized_label or lowered.startswith(f"{normalized_label} ") or lowered.startswith(f"{normalized_label}:"):
                return label
            continue
        if " " in normalized_label and normalized_label in lowered:
            return label
        if re.search(rf"(?<!\w){re.escape(normalized_label)}(?!\w)", lowered):
            return label
    return None


def find_line_index_by_label(lines: list[NormalizedLine], labels: Iterable[str]) -> tuple[int, str] | None:
    for index, line in enumerate(lines):
        label = label_in_text(line.text, labels)
        if label:
            return index, label
    return None


def get_nearby_lines(lines: list[NormalizedLine], index: int, before: int = 0, after: int = 2) -> list[NormalizedLine]:
    start = max(index - before, 0)
    end = min(index + after + 1, len(lines))
    return lines[start:end]


def text_after_label(line_text: str, label: str) -> str | None:
    pattern = re.compile(rf"{re.escape(label)}\s*:?\s*(.+)$", re.IGNORECASE)
    match = pattern.search(line_text)
    if match:
        value = match.group(1).strip()
        return value or None
    return None


def find_section(lines: list[NormalizedLine], start_markers: list[str], end_markers: list[str] | None = None) -> list[NormalizedLine]:
    start_index: int | None = None
    for index, line in enumerate(lines):
        if label_in_text(line.text, start_markers):
            start_index = index
            break
    if start_index is None:
        return []

    end_index = len(lines)
    for index in range(start_index + 1, len(lines)):
        if end_markers and label_in_text(lines[index].text, end_markers):
            end_index = index
            break
    return lines[start_index:end_index]


def regex_first_match(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    if not match:
        return None
    if match.groups():
        return next((group for group in match.groups() if group is not None), match.group(0)).strip()
    return match.group(0).strip()
