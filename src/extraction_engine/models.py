from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .warnings import ExtractionWarning


@dataclass(slots=True)
class NormalizedLine:
    line_number: int
    text: str
    page_number: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NormalizedLine":
        return cls(
            line_number=int(data.get("line_number", 0)),
            text=str(data.get("text", "")),
            page_number=data.get("page_number"),
        )


@dataclass(slots=True)
class NormalizedPage:
    page_number: int
    text: str = ""
    lines: list[NormalizedLine] = field(default_factory=list)
    blocks: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NormalizedPage":
        return cls(
            page_number=int(data.get("page_number", 0)),
            text=str(data.get("text", "")),
            lines=[NormalizedLine.from_dict(line) for line in data.get("lines", [])],
            blocks=list(data.get("blocks", [])),
        )


@dataclass(slots=True)
class NormalizedDocument:
    document_id: str | None
    source_file: str | None = None
    pages: list[NormalizedPage] = field(default_factory=list)
    full_text: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NormalizedDocument":
        if not isinstance(data, dict):
            raise ValueError("normalized_document must be a dictionary")
        pages = [NormalizedPage.from_dict(page) for page in data.get("pages", [])]
        return cls(
            document_id=data.get("document_id"),
            source_file=data.get("source_file"),
            pages=pages,
            full_text=str(data.get("full_text", "")),
            raw=data,
        )


@dataclass(slots=True)
class BlueprintField:
    name: str
    data_type: str = "string"
    required: bool = False
    possible_labels: list[str] = field(default_factory=list)
    extraction_strategy: str = "fallback_search"
    normalization: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)
    fallback_strategy: str | None = None
    output_key: str | None = None
    extraction: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BlueprintField":
        if not isinstance(data, dict) or not data.get("name"):
            raise ValueError("Each blueprint field must be a dictionary with a name")
        extraction_strategy = data.get("extraction_strategy", "fallback_search")
        extraction_config = dict(data.get("extraction", {}))
        if isinstance(extraction_strategy, dict):
            extraction_config = {**extraction_strategy, **extraction_config}
            extraction_strategy = extraction_strategy.get("strategy_type", "fallback_search")
        return cls(
            name=str(data["name"]),
            data_type=str(data.get("data_type", "string")),
            required=bool(data.get("required", False)),
            possible_labels=list(data.get("possible_labels", [])),
            extraction_strategy=str(extraction_strategy),
            normalization=dict(data.get("normalization", {})),
            validation=dict(data.get("validation", {})),
            fallback_strategy=data.get("fallback_strategy"),
            output_key=data.get("output_key") or data["name"],
            extraction=extraction_config,
            raw=data,
        )


@dataclass(slots=True)
class BlueprintTable:
    table_name: str
    required: bool = False
    detection_strategy: str = "header_based"
    header_keywords: list[str] = field(default_factory=list)
    start_markers: list[str] = field(default_factory=list)
    end_markers: list[str] = field(default_factory=list)
    columns: list[dict[str, Any]] = field(default_factory=list)
    output_key: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BlueprintTable":
        if not isinstance(data, dict) or not data.get("table_name"):
            raise ValueError("Each blueprint table must be a dictionary with a table_name")
        detection_strategy = data.get("detection_strategy", "header_based")
        if isinstance(detection_strategy, dict):
            detection_strategy = detection_strategy.get("strategy_type", "header_based")
        return cls(
            table_name=str(data["table_name"]),
            required=bool(data.get("required", False)),
            detection_strategy=str(detection_strategy),
            header_keywords=list(data.get("header_keywords", [])),
            start_markers=list(data.get("start_markers", [])),
            end_markers=list(data.get("end_markers", [])),
            columns=list(data.get("columns", [])),
            output_key=data.get("output_key") or data["table_name"],
            raw=data,
        )


@dataclass(slots=True)
class Blueprint:
    blueprint_id: str
    document_family: str | None = None
    version: str | None = None
    fields: list[BlueprintField] = field(default_factory=list)
    tables: list[BlueprintTable] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Blueprint":
        if not isinstance(data, dict):
            raise ValueError("blueprint must be a dictionary")
        metadata = data.get("blueprint_metadata", {}) if isinstance(data.get("blueprint_metadata"), dict) else {}
        blueprint_id = data.get("blueprint_id") or metadata.get("blueprint_id")
        if not blueprint_id:
            raise ValueError("blueprint must include blueprint_id")
        document_family = data.get("document_family")
        if isinstance(document_family, dict):
            document_family = document_family.get("document_type") or document_family.get("family")
        return cls(
            blueprint_id=str(blueprint_id),
            document_family=document_family,
            version=data.get("version") or metadata.get("blueprint_version"),
            fields=[BlueprintField.from_dict(field) for field in data.get("fields", [])],
            tables=[BlueprintTable.from_dict(table) for table in data.get("tables", [])],
            raw=data,
        )


@dataclass(slots=True)
class FieldExtraction:
    value: Any
    raw_value: str | None
    strategy: str
    evidence: str | None = None
    label_found: bool = False
    pattern_matched: bool = False
    fallback_used: bool = False
    candidates: int = 0
    warnings: list[ExtractionWarning] = field(default_factory=list)


@dataclass(slots=True)
class TableExtraction:
    rows: list[dict[str, Any]]
    strategy: str
    evidence: str | None = None
    found: bool = False
    warnings: list[ExtractionWarning] = field(default_factory=list)
