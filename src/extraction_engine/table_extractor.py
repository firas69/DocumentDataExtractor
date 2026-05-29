from __future__ import annotations

import re
from typing import Any

from .models import BlueprintTable, NormalizedDocument, TableExtraction
from .normalizers import normalize_value
from .strategies import find_section, get_lines, label_in_text


class TableExtractor:
    def extract_table(self, document: NormalizedDocument, table: BlueprintTable) -> TableExtraction:
        strategy = self._canonical_strategy(table.detection_strategy)
        if strategy == "marker_based":
            return self._marker_based(document, table)
        return self._header_based(document, table)

    def _canonical_strategy(self, strategy: str) -> str:
        aliases = {
            "header_keyword_and_row_pattern": "header_based",
            "detected_tables_from_normalizer": "header_based",
            "line_grouping_between_markers": "marker_based",
        }
        return aliases.get(strategy.casefold(), strategy.casefold())

    def _header_based(self, document: NormalizedDocument, table: BlueprintTable) -> TableExtraction:
        lines = get_lines(document)
        header_index: int | None = None
        header_end_index: int | None = None
        for index, line in enumerate(lines):
            matches = sum(1 for keyword in table.header_keywords if keyword.casefold() in line.text.casefold())
            threshold = max(2, min(len(table.header_keywords), 3))
            if matches >= threshold:
                header_index = index
                header_end_index = index
                break
            stacked_end = self._stacked_header_end(lines, index, table) if self._line_matches_header(line.text, table) else None
            if stacked_end is not None:
                header_index = index
                header_end_index = stacked_end
                break
        if header_index is None:
            return TableExtraction(rows=[], strategy="header_based")

        row_lines: list[str] = []
        row_rules = table.raw.get("row_rules", {}) if isinstance(table.raw.get("row_rules"), dict) else {}
        has_split_row_pattern = bool(row_rules.get("special_row_pattern"))
        for line in lines[(header_end_index or header_index) + 1 :]:
            if label_in_text(line.text, table.end_markers):
                if has_split_row_pattern and label_in_text(line.text, ["subtotal", "discount", "tax", "total"]):
                    continue
                break
            if line.text.strip():
                row_lines.append(line.text)
        if has_split_row_pattern and row_lines and not any(self._line_matches_value_columns(line, table.columns[1:]) for line in row_lines):
            row_lines.extend(self._find_split_value_rows(lines[(header_end_index or header_index) + 1 :], table, len(row_lines)))
        return TableExtraction(
            rows=self._parse_rows(row_lines, table),
            strategy="header_based",
            evidence=lines[header_index].text,
            found=True,
        )

    def _marker_based(self, document: NormalizedDocument, table: BlueprintTable) -> TableExtraction:
        lines = find_section(get_lines(document), table.start_markers, table.end_markers)
        if not lines:
            return TableExtraction(rows=[], strategy="marker_based")
        row_lines = [line.text for line in lines[1:] if line.text.strip()]
        return TableExtraction(
            rows=self._parse_rows(row_lines, table),
            strategy="marker_based",
            evidence=lines[0].text,
            found=True,
        )

    def _parse_rows(self, row_lines: list[str], table: BlueprintTable) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        columns = table.columns
        row_rules = table.raw.get("row_rules", {}) if isinstance(table.raw.get("row_rules"), dict) else {}
        grouped_rows = self._parse_description_value_block_rows(row_lines, columns)
        if grouped_rows:
            return grouped_rows
        stacked_rows = self._parse_stacked_rows(row_lines, columns)
        if stacked_rows and (row_rules.get("special_row_pattern") or self._stacked_rows_are_complete(stacked_rows, columns)):
            return stacked_rows
        for row_line in row_lines:
            if self._looks_like_header(row_line, columns):
                continue
            parts = row_line.split()
            if not parts:
                continue
            row = self._parse_row_by_schema(parts, columns)
            numeric_keys = [
                column.get("output_key") or column.get("name")
                for column in columns
                if column.get("data_type") in {"number", "currency", "money", "weight"}
            ]
            if numeric_keys and all(row.get(key) is None for key in numeric_keys) and not any(char.isdigit() for char in row_line):
                continue
            if any(value is not None and value != "" for value in row.values()):
                rows.append(row)
        return rows

    def _parse_description_value_block_rows(self, row_lines: list[str], columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
        description_index = self._description_column_index(columns)
        if description_index != 0 or len(columns) < 3:
            return []
        ignored = self._ignored_row_markers(row_lines, columns)
        usable_lines = [
            line.strip()
            for line in row_lines
            if line.strip()
            and not self._looks_like_header(line, columns)
            and not label_in_text(line, ignored)
        ]
        description_lines: list[str] = []
        value_lines: list[str] = []
        for line in usable_lines:
            parts = line.split()
            if self._parts_match_columns(parts, columns[1:]):
                value_lines.append(line)
            elif not value_lines and not self._looks_like_money_or_number(line):
                description_lines.append(line)
            elif value_lines:
                break
        if not description_lines or len(description_lines) != len(value_lines):
            return []
        rows: list[dict[str, Any]] = []
        for description, value_line in zip(description_lines, value_lines, strict=False):
            parts = value_line.split()
            row = {columns[0].get("output_key") or columns[0].get("name"): description}
            for column, raw_value in zip(columns[1:], parts, strict=False):
                key = column.get("output_key") or column.get("name")
                normalized, _ = normalize_value(raw_value, column.get("data_type", "string"))
                row[key] = normalized
            rows.append(row)
        return rows

    def _stacked_header_end(self, lines, start_index: int, table: BlueprintTable) -> int | None:
        matched_columns = 0
        end_index = start_index
        max_header_lines = min(len(table.columns) + 2, 8)
        for index in range(start_index, min(start_index + max_header_lines, len(lines))):
            text = lines[index].text.casefold()
            if any(keyword.casefold() == text.strip() or keyword.casefold() in text for keyword in table.header_keywords):
                matched_columns += 1
                end_index = index
        threshold = max(2, min(len(table.columns), 3))
        return end_index if matched_columns >= threshold else None

    def _line_matches_header(self, text: str, table: BlueprintTable) -> bool:
        lowered = text.casefold().strip()
        return any(keyword.casefold() == lowered or keyword.casefold() in lowered for keyword in table.header_keywords)

    def _find_split_value_rows(self, lines, table: BlueprintTable, expected_rows: int) -> list[str]:
        value_rows: list[str] = []
        value_columns = table.columns[1:]
        for line in lines:
            text = line.text.strip()
            if self._line_matches_value_columns(text, value_columns):
                value_rows.append(text)
                if len(value_rows) >= expected_rows:
                    break
        return value_rows if len(value_rows) == expected_rows else []

    def _line_matches_value_columns(self, text: str, columns: list[dict[str, Any]]) -> bool:
        return self._parts_match_columns(text.split(), columns)

    def _parse_stacked_rows(self, row_lines: list[str], columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(columns) < 2 or len(row_lines) < len(columns):
            return []
        usable_lines = [line.strip() for line in row_lines if line.strip() and not self._looks_like_header(line, columns)]
        rows: list[dict[str, Any]] = []
        index = 0
        while index + len(columns) <= len(usable_lines):
            chunk = usable_lines[index : index + len(columns)]
            if not self._chunk_matches_columns(chunk, columns):
                if rows:
                    break
                return []
            row: dict[str, Any] = {}
            for column, raw_value in zip(columns, chunk, strict=False):
                key = column.get("output_key") or column.get("name")
                normalized, _ = normalize_value(raw_value, column.get("data_type", "string"))
                row[key] = normalized
            rows.append(row)
            index += len(columns)
        return rows

    def _stacked_rows_are_complete(self, rows: list[dict[str, Any]], columns: list[dict[str, Any]]) -> bool:
        required_keys = [
            column.get("output_key") or column.get("name")
            for column in columns
            if column.get("required")
        ]
        return bool(rows) and all(all(row.get(key) not in (None, "") for key in required_keys) for row in rows)

    def _looks_like_money_or_number(self, value: str) -> bool:
        return bool(re.match(r"^\s*[$€£]?\s*\d[\d\s,.]*\s*$", value))

    def _chunk_matches_columns(self, chunk: list[str], columns: list[dict[str, Any]]) -> bool:
        matches = 0
        for raw_value, column in zip(chunk, columns, strict=False):
            data_type = column.get("data_type", "string")
            if data_type == "string" and raw_value:
                matches += 1
            elif data_type == "number" and normalize_value(raw_value, "number")[0] is not None:
                matches += 1
            elif data_type in {"money", "currency"} and re.search(r"[$€£]\s*\d|\d[\d\s,.]*\s*(USD|EUR|GBP|TND)", raw_value, flags=re.IGNORECASE):
                matches += 1
            elif data_type == "weight" and normalize_value(raw_value, "weight")[0] is not None:
                matches += 1
        return matches >= len(columns) - 1

    def _parts_match_columns(self, parts: list[str], columns: list[dict[str, Any]]) -> bool:
        if len(parts) != len(columns):
            return False
        return self._chunk_matches_columns(parts, columns)

    def _parse_row_by_schema(self, parts: list[str], columns: list[dict[str, Any]]) -> dict[str, Any]:
        description_index = self._description_column_index(columns)
        if description_index is None:
            description_index = 0

        leading_columns = columns[:description_index]
        description_column = columns[description_index]
        trailing_columns = columns[description_index + 1 :]

        cursor = 0
        raw_values: dict[str, str | None] = {}

        for column in leading_columns:
            key = column.get("output_key") or column.get("name")
            raw_values[key] = parts[cursor] if cursor < len(parts) else None
            cursor += 1

        right_cursor = len(parts)
        for column in reversed(trailing_columns):
            key = column.get("output_key") or column.get("name")
            if right_cursor <= cursor:
                raw_values[key] = None
            else:
                right_cursor -= 1
                raw_values[key] = parts[right_cursor]

        description_key = description_column.get("output_key") or description_column.get("name")
        raw_values[description_key] = " ".join(parts[cursor:right_cursor]).strip() or None

        row: dict[str, Any] = {}
        for column in columns:
            key = column.get("output_key") or column.get("name")
            data_type = column.get("data_type", "string")
            normalized, _ = normalize_value(raw_values.get(key), data_type)
            row[key] = normalized
        return row

    def _description_column_index(self, columns: list[dict[str, Any]]) -> int | None:
        for index, column in enumerate(columns):
            name = str(column.get("name", "")).casefold()
            output_key = str(column.get("output_key", "")).casefold()
            if "description" in name or "description" in output_key:
                return index
        for index, column in enumerate(columns):
            if column.get("data_type", "string") == "string":
                return index
        return None

    def _looks_like_header(self, row_line: str, columns: list[dict[str, Any]]) -> bool:
        lowered = row_line.casefold()
        matches = 0
        for column in columns:
            headers = column.get("possible_headers") or [column.get("name", "")]
            if any(header and str(header).casefold() in lowered for header in headers):
                matches += 1
        return matches >= 2

    def _ignored_row_markers(self, row_lines: list[str], columns: list[dict[str, Any]]) -> list[str]:
        return ["subtotal", "discount", "tax", "total", "remarks", "terms"]
