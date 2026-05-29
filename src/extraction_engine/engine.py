from __future__ import annotations

from typing import Any

from .confidence import score_field, score_table
from .field_extractor import FieldExtractor
from .models import Blueprint, NormalizedDocument
from .normalizers import normalize_value
from .table_extractor import TableExtractor
from .validators import validate_field, validate_numeric_consistency, validate_table

ENGINE_VERSION = "0.1.0"


class ExtractionEngine:
    def __init__(self) -> None:
        self.field_extractor = FieldExtractor()
        self.table_extractor = TableExtractor()

    def extract(self, normalized_document: dict[str, Any], blueprint: dict[str, Any]) -> dict[str, Any]:
        document = NormalizedDocument.from_dict(normalized_document)
        parsed_blueprint = Blueprint.from_dict(blueprint)

        extracted_data: dict[str, Any] = {}
        confidence: dict[str, float] = {}
        warnings = []
        fields_extracted = 0
        tables_extracted = 0

        for field in parsed_blueprint.fields:
            key = field.output_key or field.name
            extraction = self.field_extractor.extract_field(document, field)
            normalized, normalization_warnings = normalize_value(
                extraction.value,
                field.data_type,
                field.normalization,
            )
            extraction.value = normalized
            field_warnings = normalization_warnings + validate_field(field, normalized)
            for warning in field_warnings:
                warning.field = warning.field or key
            warnings.extend(field_warnings)
            if normalized is not None:
                self._set_output_value(extracted_data, key, normalized)
                fields_extracted += 1
            confidence[key] = score_field(extraction, field_warnings)

        for table in parsed_blueprint.tables:
            key = table.output_key or table.table_name
            extraction = self.table_extractor.extract_table(document, table)
            table_warnings = validate_table(table, extraction.rows)
            warnings.extend(table_warnings)
            self._set_output_value(extracted_data, key, extraction.rows)
            if extraction.rows:
                tables_extracted += 1
            confidence[key] = score_table(extraction, table_warnings)

        warnings.extend(validate_numeric_consistency(extracted_data))

        return {
            "document_id": document.document_id,
            "blueprint_id": parsed_blueprint.blueprint_id,
            "document_family": parsed_blueprint.document_family,
            "extracted_data": extracted_data,
            "confidence": confidence,
            "warnings": [warning.to_dict() for warning in warnings],
            "metadata": {
                "engine_version": ENGINE_VERSION,
                "fields_attempted": len(parsed_blueprint.fields),
                "fields_extracted": fields_extracted,
                "tables_attempted": len(parsed_blueprint.tables),
                "tables_extracted": tables_extracted,
            },
        }

    def _set_output_value(self, data: dict[str, Any], key: str, value: Any) -> None:
        if "." not in key:
            data[key] = value
            return
        current = data
        parts = key.split(".")
        for part in parts[:-1]:
            next_value = current.get(part)
            if not isinstance(next_value, dict):
                next_value = {}
                current[part] = next_value
            current = next_value
        current[parts[-1]] = value
