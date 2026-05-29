from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from .models import BlueprintField, FieldExtraction, NormalizedDocument, NormalizedLine
from .normalizers import detect_currency, normalize_date
from .strategies import (
    find_section,
    get_full_text,
    get_lines,
    get_nearby_lines,
    label_in_text,
    regex_first_match,
    text_after_label,
)


class FieldExtractor:
    def extract_field(self, document: NormalizedDocument, field: BlueprintField) -> FieldExtraction:
        strategy = self._canonical_strategy(field.extraction_strategy)
        if strategy == "label_neighbor":
            return self._label_neighbor(document, field)
        if strategy == "regex_pattern":
            return self._regex_pattern(document, field)
        if strategy == "keyword_window":
            return self._keyword_window(document, field)
        if strategy == "section_anchor":
            return self._section_anchor(document, field)
        if strategy == "currency_detection":
            return self._currency_detection(document, field)
        if strategy == "terms_based":
            return self._terms_based(document, field)
        if strategy == "fallback_search":
            return self._fallback_search(document, field)
        return self._fallback_search(document, field)

    def _canonical_strategy(self, strategy: str) -> str:
        aliases = {
            "label_value": "label_neighbor",
            "label_value_with_split_label_support": "label_neighbor",
            "label_value_with_reversed_totals_support": "label_neighbor",
            "label_value_or_summary_column": "label_neighbor",
            "section_based": "section_anchor",
            "regex": "regex_pattern",
            "symbol_or_code_detection": "currency_detection",
            "terms_based_inference": "terms_based",
        }
        return aliases.get(strategy.casefold(), strategy.casefold())

    def _label_neighbor(self, document: NormalizedDocument, field: BlueprintField) -> FieldExtraction:
        lines = get_lines(document)
        for index, line in enumerate(lines):
            label = label_in_text(line.text, field.possible_labels)
            if not label:
                continue
            if self._is_ambiguous_label_hit(line.text, label, field):
                continue
            same_line_value = text_after_label(line.text, label)
            if (
                same_line_value
                and not self._is_separator_or_label(same_line_value, field)
                and self._candidate_matches_field_type(same_line_value, field)
            ):
                return FieldExtraction(
                    value=same_line_value,
                    raw_value=same_line_value,
                    strategy="label_neighbor",
                    evidence=line.text,
                    label_found=True,
                )
            max_distance = int(field.extraction.get("max_search_distance_lines", 1))
            prefer_previous = self._prefer_previous_value(field)
            if prefer_previous:
                previous_value = self._previous_value_for_label(lines, index, field, max_distance)
                if previous_value:
                    return FieldExtraction(
                        value=previous_value,
                        raw_value=previous_value,
                        strategy="label_neighbor",
                        evidence=line.text,
                        label_found=True,
                    )
            for nearby_line in get_nearby_lines(lines, index, after=max_distance)[1:]:
                candidate = nearby_line.text.strip()
                if not candidate or self._is_separator_or_label(candidate, field):
                    continue
                if not self._candidate_matches_field_type(candidate, field):
                    previous_value = self._previous_value_for_label(lines, index, field, max_distance)
                    if previous_value:
                        return FieldExtraction(
                            value=previous_value,
                            raw_value=previous_value,
                            strategy="label_neighbor",
                            evidence=line.text,
                            label_found=True,
                        )
                    break
                if candidate:
                    return FieldExtraction(
                        value=candidate,
                        raw_value=candidate,
                        strategy="label_neighbor",
                        evidence=f"{line.text}\n{nearby_line.text}",
                        label_found=True,
                    )
            if not prefer_previous:
                previous_value = self._previous_value_for_label(lines, index, field, max_distance)
                if previous_value:
                    return FieldExtraction(
                        value=previous_value,
                        raw_value=previous_value,
                        strategy="label_neighbor",
                        evidence=line.text,
                        label_found=True,
                    )
            grouped_value = self._mapped_following_value(lines, index, field)
            if grouped_value:
                return FieldExtraction(
                    value=grouped_value,
                    raw_value=grouped_value,
                    strategy="label_neighbor",
                    evidence=line.text,
                    label_found=True,
                )
        regex_value = self._regex_fallback_value(document, field)
        if regex_value:
            return FieldExtraction(
                value=regex_value,
                raw_value=regex_value,
                strategy="label_neighbor",
                evidence="full_text",
                pattern_matched=True,
                fallback_used=True,
            )
        return FieldExtraction(value=None, raw_value=None, strategy="label_neighbor")

    def _regex_pattern(self, document: NormalizedDocument, field: BlueprintField) -> FieldExtraction:
        pattern = self._pattern_for(field)
        if not pattern:
            return FieldExtraction(value=None, raw_value=None, strategy="regex_pattern")
        value = regex_first_match(get_full_text(document), pattern)
        return FieldExtraction(
            value=value,
            raw_value=value,
            strategy="regex_pattern",
            pattern_matched=value is not None,
        )

    def _keyword_window(self, document: NormalizedDocument, field: BlueprintField) -> FieldExtraction:
        lines = get_lines(document)
        pattern = self._pattern_for(field)
        for index, line in enumerate(lines):
            if not label_in_text(line.text, field.possible_labels):
                continue
            window_lines = get_nearby_lines(lines, index, before=0, after=int(field.raw.get("window_lines", 3)))
            window_text = "\n".join(item.text for item in window_lines)
            if pattern:
                value = regex_first_match(window_text, pattern)
                if value:
                    return FieldExtraction(
                        value=value,
                        raw_value=value,
                        strategy="keyword_window",
                        evidence=window_text,
                        label_found=True,
                        pattern_matched=True,
                    )
            value = self._first_value_after_label(window_lines, field.possible_labels)
            if value:
                return FieldExtraction(
                    value=value,
                    raw_value=value,
                    strategy="keyword_window",
                    evidence=window_text,
                    label_found=True,
                )
        return FieldExtraction(value=None, raw_value=None, strategy="keyword_window")

    def _section_anchor(self, document: NormalizedDocument, field: BlueprintField) -> FieldExtraction:
        lines = get_lines(document)
        start_markers = list(field.raw.get("start_markers", []) or field.extraction.get("section_markers", []))
        end_markers = list(field.raw.get("end_markers", []) or field.extraction.get("section_end_markers", []))
        section_lines = find_section(lines, start_markers or field.possible_labels, end_markers)
        if not section_lines:
            return FieldExtraction(value=None, raw_value=None, strategy="section_anchor")
        candidate_selection = str(field.extraction.get("candidate_selection", ""))
        extended_lines = self._extend_section_if_empty(section_lines, lines, field)
        if len(extended_lines) > len(section_lines):
            section_lines = extended_lines
        if candidate_selection == "all_lines_until_next_section_marker":
            max_lines = int(field.extraction.get("max_lines_in_section", len(section_lines)))
            body_lines = [line.text.strip() for line in section_lines[1:max_lines] if line.text.strip()]
            if body_lines:
                value = " ".join(body_lines)
                return FieldExtraction(
                    value=value,
                    raw_value=value,
                    strategy="section_anchor",
                    evidence="\n".join(item.text for item in section_lines[:max_lines]),
                    label_found=True,
                )
        if candidate_selection.startswith("first_") and len(section_lines) > 1:
            max_lines = int(field.extraction.get("max_lines_in_section", len(section_lines)))
            for line in section_lines[1:max_lines]:
                text = line.text.strip()
                if (
                    text
                    and not self._is_separator_or_label(text, field)
                    and not label_in_text(text, end_markers)
                    and not text.startswith("#")
                ):
                    return FieldExtraction(
                        value=text,
                        raw_value=text,
                        strategy="section_anchor",
                        evidence="\n".join(item.text for item in section_lines[:max_lines]),
                        label_found=True,
                    )
        section_doc = self._document_from_lines(document, section_lines)
        result = self._label_neighbor(section_doc, field)
        if result.value is not None:
            result.strategy = "section_anchor"
            result.evidence = "\n".join(line.text for line in section_lines)
            return result
        pattern = self._pattern_for(field)
        if pattern:
            value = regex_first_match("\n".join(line.text for line in section_lines), pattern)
            if value:
                return FieldExtraction(
                    value=value,
                    raw_value=value,
                    strategy="section_anchor",
                    evidence="\n".join(line.text for line in section_lines),
                    label_found=True,
                    pattern_matched=True,
                )
        return FieldExtraction(value=None, raw_value=None, strategy="section_anchor")

    def _extend_section_if_empty(
        self,
        section_lines: list[NormalizedLine],
        all_lines: list[NormalizedLine],
        field: BlueprintField,
    ) -> list[NormalizedLine]:
        max_lines = int(field.extraction.get("max_lines_in_section", len(section_lines)))
        body = [
            line.text.strip()
            for line in section_lines[1:max_lines]
            if line.text.strip() and not self._is_separator_or_label(line.text.strip(), field)
        ]
        if body:
            return section_lines
        last_line = section_lines[-1]
        try:
            last_index = all_lines.index(last_line)
        except ValueError:
            return section_lines
        return all_lines[max(0, last_index - len(section_lines) + 1) : min(len(all_lines), last_index + max_lines)]

    def _fallback_search(self, document: NormalizedDocument, field: BlueprintField) -> FieldExtraction:
        for extractor in (self._label_neighbor, self._regex_pattern, self._keyword_window):
            result = extractor(document, field)
            if result.value is not None:
                if extractor is not self._label_neighbor:
                    result.fallback_used = True
                result.strategy = "fallback_search"
                return result
        return FieldExtraction(value=None, raw_value=None, strategy="fallback_search")

    def _currency_detection(self, document: NormalizedDocument, field: BlueprintField) -> FieldExtraction:
        currency = detect_currency(get_full_text(document))
        return FieldExtraction(
            value=currency,
            raw_value=currency,
            strategy="currency_detection",
            pattern_matched=currency is not None,
        )

    def _terms_based(self, document: NormalizedDocument, field: BlueprintField) -> FieldExtraction:
        lines = get_lines(document)
        for index, line in enumerate(lines):
            if not label_in_text(line.text, field.possible_labels):
                continue
            window = "\n".join(
                item.text
                for item in get_nearby_lines(
                    lines,
                    index,
                    after=int(field.extraction.get("max_search_distance_lines", 5)),
                )
            )
            net_match = re.search(r"\bnet\s+(\d+)\b", window, flags=re.IGNORECASE)
            if net_match:
                inferred = self._infer_due_date_from_first_date(get_full_text(document), int(net_match.group(1)))
                return FieldExtraction(
                    value=inferred or net_match.group(0),
                    raw_value=net_match.group(0),
                    strategy="terms_based",
                    label_found=True,
                )
            date_value = regex_first_match(window, self._date_regex())
            if date_value:
                return FieldExtraction(value=date_value, raw_value=date_value, strategy="terms_based", label_found=True)
        return FieldExtraction(value=None, raw_value=None, strategy="terms_based")

    def _first_value_after_label(self, lines: list[NormalizedLine], labels: list[str]) -> str | None:
        for index, line in enumerate(lines):
            label = label_in_text(line.text, labels)
            if label:
                same_line = text_after_label(line.text, label)
                if same_line:
                    return same_line
                if index + 1 < len(lines) and lines[index + 1].text.strip():
                    return lines[index + 1].text.strip()
        return None

    def _previous_value_for_label(
        self,
        lines: list[NormalizedLine],
        index: int,
        field: BlueprintField,
        max_distance: int,
    ) -> str | None:
        mapped = self._mapped_reversed_value(lines, index, field)
        if mapped:
            return mapped

        pattern = self._value_pattern_regex(field)
        start = max(0, index - max_distance)
        if field.extraction.get("support_label_value_inverted_order"):
            for previous in reversed(lines[start:index]):
                numeric_identifier = re.search(r"\b\d{4,20}\b", previous.text)
                if numeric_identifier:
                    return numeric_identifier.group(0)
        for previous in reversed(lines[start:index]):
            text = previous.text.strip()
            if not text or self._is_separator_or_label(text, field):
                continue
            if pattern and re.search(pattern, text, flags=re.IGNORECASE):
                return text
            if self._looks_like_type_value(text, field.data_type):
                return text
            if field.data_type == "string" and "previous_value_block" in field.extraction.get("label_position", []):
                return text
        return None

    def _prefer_previous_value(self, field: BlueprintField) -> bool:
        label_positions = field.extraction.get("label_position", [])
        if "previous_value_block" not in label_positions:
            return False
        return "next_line" not in label_positions and "right_of_label" not in label_positions

    def _mapped_reversed_value(self, lines: list[NormalizedLine], index: int, field: BlueprintField) -> str | None:
        if "previous_value_block" not in field.extraction.get("label_position", []):
            return None

        known_total_labels = ["subtotal", "discount", "tax", "total", "solde à payer"]

        block_start = index
        cursor = index - 1
        while cursor >= 0:
            text = lines[cursor].text.strip()
            if text == ":" or label_in_text(text, known_total_labels) or label_in_text(text, field.possible_labels):
                block_start = cursor
                cursor -= 1
                continue
            break

        label_lines: list[int] = []
        cursor = block_start
        while cursor < len(lines):
            text = lines[cursor].text.strip()
            if text == ":":
                cursor += 1
                continue
            if not (label_in_text(text, field.possible_labels) or label_in_text(text, known_total_labels)):
                break
            label_lines.append(cursor)
            cursor += 1
        if index not in label_lines:
            label_lines.insert(0, index)

        value_lines: list[str] = []
        cursor = block_start - 1
        while cursor >= 0:
            text = lines[cursor].text.strip()
            if not text or text == ":":
                cursor -= 1
                continue
            if self._looks_like_type_value(text, field.data_type):
                value_lines.insert(0, text)
                cursor -= 1
                continue
            break

        offset = label_lines.index(index) if index in label_lines else 0
        if len(value_lines) > len(label_lines):
            value_lines = value_lines[-len(label_lines) :]
        if offset < len(value_lines):
            return value_lines[offset]
        return None

    def _mapped_following_value(self, lines: list[NormalizedLine], index: int, field: BlueprintField) -> str | None:
        label_lines = self._nearby_label_block(lines, index, field)
        if index not in label_lines:
            return None
        if field.name == "invoice_number":
            return self._first_identifier_value(lines, start=index)

        offset = label_lines.index(index)
        cursor = label_lines[-1] + 1
        current_run: list[str] = []
        max_scan = min(len(lines), cursor + 32)
        while cursor < max_scan:
            text = lines[cursor].text.strip()
            if not text or text == ":":
                cursor += 1
                continue
            if self._is_grouped_value_candidate(text, field):
                current_run.append(text)
                if len(current_run) >= len(label_lines) and offset < len(current_run):
                    return current_run[offset]
            elif current_run:
                current_run = []
            cursor += 1
        return None

    def _is_grouped_value_candidate(self, text: str, field: BlueprintField) -> bool:
        if field.data_type in {"money", "currency"}:
            return self._looks_like_single_money_value(text)
        return self._looks_like_type_value(text, field.data_type)

    def _looks_like_single_money_value(self, text: str) -> bool:
        return bool(re.match(r"^\s*(?:[$€£][ \t]*\d[\d \t,\.]*|\d[\d \t,\.]*[ \t]*(?:USD|EUR|GBP|TND))\s*$", text, flags=re.IGNORECASE))

    def _nearby_label_block(self, lines: list[NormalizedLine], index: int, field: BlueprintField) -> list[int]:
        block_labels = self._block_labels_for(field)
        start = index
        cursor = index - 1
        while cursor >= 0:
            text = lines[cursor].text.strip()
            if text == ":" or label_in_text(text, block_labels):
                start = cursor
                cursor -= 1
                continue
            break

        label_lines: list[int] = []
        cursor = start
        while cursor < len(lines):
            text = lines[cursor].text.strip()
            if text == ":":
                cursor += 1
                continue
            if not label_in_text(text, block_labels):
                break
            label_lines.append(cursor)
            cursor += 1
        return label_lines

    def _block_labels_for(self, field: BlueprintField) -> list[str]:
        labels = list(field.possible_labels)
        if field.data_type in {"money", "currency"}:
            labels.extend(["subtotal", "discount", "tax", "total", "solde à payer", "opening balance", "total credit", "total debit", "net balance"])
        if field.data_type == "date" or field.name in {"invoice_number", "po_reference_number", "purchase_order"}:
            labels.extend(["invoice", "#", "date", "payment methods", "purchase order", "solde à payer"])
        return labels

    def _first_identifier_value(self, lines: list[NormalizedLine], start: int = 0) -> str | None:
        pattern = re.compile(r"\b(?:INV|STG|PO|BOL)[A-Z0-9\-\/]*\d[A-Z0-9\-\/]*\b", flags=re.IGNORECASE)
        for line in lines[start:]:
            match = pattern.search(line.text)
            if match:
                return match.group(0).lstrip("#").strip()
        return None

    def _regex_fallback_value(self, document: NormalizedDocument, field: BlueprintField) -> str | None:
        if field.name == "invoice_number":
            return self._first_identifier_value(get_lines(document))
        pattern = self._value_pattern_regex(field)
        if not pattern or pattern in {"date", "money", "number", "date_or_payment_terms"}:
            return None
        return regex_first_match(get_full_text(document), pattern)

    def _value_pattern_regex(self, field: BlueprintField) -> str | None:
        pattern = self._pattern_for(field)
        aliases = {
            "date": self._date_regex(),
            "money": r"(?:[$€£][ \t]*\d[\d \t,\.]*|\d[\d \t,\.]*[ \t]*(?:USD|EUR|GBP|TND))",
            "number": r"\d[\d\s,\.]*",
            "date_or_payment_terms": rf"({self._date_regex()}|\bnet\s+\d+\b)",
        }
        return aliases.get(pattern, pattern)

    def _looks_like_type_value(self, text: str, data_type: str) -> bool:
        data_type = data_type.casefold()
        if data_type == "date":
            return bool(re.search(self._date_regex(), text, flags=re.IGNORECASE))
        if data_type in {"money", "currency"}:
            return bool(re.search(r"[$€£][ \t]*\d|\d[\d \t,\.]*[ \t]*(USD|EUR|GBP|TND)", text, flags=re.IGNORECASE))
        if data_type in {"number", "weight"}:
            return bool(re.search(r"\d", text))
        return bool(text)

    def _candidate_matches_field_type(self, text: str, field: BlueprintField) -> bool:
        regex = field.validation.get("regex") or field.validation.get("pattern")
        if regex and field.data_type == "string":
            return re.match(regex, text) is not None
        if field.data_type == "string":
            return True
        return self._looks_like_type_value(text, field.data_type)

    def _is_separator_or_label(self, text: str, field: BlueprintField) -> bool:
        if text.strip() in {":", "-", "–"}:
            return True
        label = label_in_text(text, field.possible_labels)
        if not label:
            return False
        normalized_text = text.strip().casefold().rstrip(":")
        normalized_label = label.strip().casefold()
        return normalized_text == normalized_label

    def _is_ambiguous_label_hit(self, text: str, label: str, field: BlueprintField) -> bool:
        if field.name == "net_balance" and label.casefold() == "balance":
            lowered = text.casefold()
            return any(prefix in lowered for prefix in ("opening balance", "total debit", "total credit"))
        return False

    def _date_regex(self) -> str:
        return r"(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{4}|[A-Z][a-z]{2,8}\s+\d{1,2},\s+\d{4})"

    def _infer_due_date_from_first_date(self, text: str, days: int) -> str | None:
        date_match = re.search(self._date_regex(), text)
        if not date_match:
            return None
        normalized, warning = normalize_date(date_match.group(0))
        if warning or not normalized:
            return None
        year, month, day = (int(part) for part in normalized.split("-"))
        return (date(year, month, day) + timedelta(days=days)).isoformat()

    def _pattern_for(self, field: BlueprintField) -> str | None:
        extraction_config: dict[str, Any] = field.extraction or {}
        return (
            extraction_config.get("pattern")
            or extraction_config.get("value_pattern")
            or field.validation.get("pattern")
            or field.validation.get("regex")
            or field.raw.get("fallback_regex")
            or field.raw.get("fallback_pattern")
        )

    def _document_from_lines(self, document: NormalizedDocument, lines: list[NormalizedLine]) -> NormalizedDocument:
        raw = {
            "document_id": document.document_id,
            "source_file": document.source_file,
            "pages": [
                {
                    "page_number": 1,
                    "lines": [
                        {
                            "line_number": line.line_number,
                            "text": line.text,
                            "page_number": line.page_number,
                        }
                        for line in lines
                    ],
                }
            ],
            "full_text": "\n".join(line.text for line in lines),
        }
        return NormalizedDocument.from_dict(raw)
