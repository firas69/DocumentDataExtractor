from __future__ import annotations

from .models import FieldExtraction, TableExtraction
from .warnings import ExtractionWarning


def score_field(extraction: FieldExtraction, validation_warnings: list[ExtractionWarning]) -> float:
    if extraction.value is None:
        return 0.0
    if extraction.candidates > 1:
        return 0.4
    if extraction.fallback_used:
        return 0.6
    if extraction.label_found and extraction.pattern_matched and not validation_warnings:
        return 0.95
    if extraction.label_found:
        return 0.85 if not validation_warnings else 0.8
    if extraction.pattern_matched:
        return 0.7
    return 0.6


def score_table(extraction: TableExtraction, validation_warnings: list[ExtractionWarning]) -> float:
    if not extraction.found or not extraction.rows:
        return 0.0
    if validation_warnings:
        return 0.65
    return 0.8 if extraction.strategy == "header_based" else 0.7
