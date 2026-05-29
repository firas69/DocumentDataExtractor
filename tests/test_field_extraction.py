from extraction_engine.field_extractor import FieldExtractor
from extraction_engine.models import BlueprintField, NormalizedDocument


def document_from_lines(lines: list[str]) -> NormalizedDocument:
    return NormalizedDocument.from_dict(
        {
            "document_id": "test_doc",
            "pages": [
                {
                    "page_number": 1,
                    "lines": [
                        {"line_number": index + 1, "text": text, "page_number": 1}
                        for index, text in enumerate(lines)
                    ],
                }
            ],
            "full_text": "\n".join(lines),
        }
    )


def field(**overrides):
    data = {
        "name": "invoice_number",
        "data_type": "string",
        "possible_labels": ["Invoice Number"],
        "extraction_strategy": "label_neighbor",
        "output_key": "invoice_number",
    }
    data.update(overrides)
    return BlueprintField.from_dict(data)


def test_label_neighbor_extracts_same_line_after_colon():
    result = FieldExtractor().extract_field(
        document_from_lines(["Invoice Number: INV-001"]),
        field(),
    )

    assert result.value == "INV-001"
    assert result.label_found is True


def test_label_neighbor_extracts_next_line():
    result = FieldExtractor().extract_field(
        document_from_lines(["Invoice Number", "INV-002"]),
        field(),
    )

    assert result.value == "INV-002"


def test_regex_pattern_uses_extraction_pattern():
    result = FieldExtractor().extract_field(
        document_from_lines(["Reference abc", "Invoice INV-900 is due"]),
        field(
            extraction_strategy="regex_pattern",
            extraction={"pattern": "Invoice\\s+([A-Z]+\\-\\d+)"},
        ),
    )

    assert result.value == "INV-900"
    assert result.pattern_matched is True


def test_keyword_window_finds_nearby_value():
    result = FieldExtractor().extract_field(
        document_from_lines(["Header", "Amount Due", "Pay before Friday", "USD 42.00"]),
        field(
            name="total_amount",
            data_type="number",
            possible_labels=["Amount Due"],
            extraction_strategy="keyword_window",
            extraction={"pattern": "USD\\s+([0-9.]+)"},
            output_key="total_amount",
            window_lines=3,
        ),
    )

    assert result.value == "42.00"


def test_section_anchor_extracts_inside_section():
    result = FieldExtractor().extract_field(
        document_from_lines(["Header", "Totals", "Balance Due: 99.50", "Footer"]),
        field(
            name="total_amount",
            data_type="number",
            possible_labels=["Balance Due"],
            extraction_strategy="section_anchor",
            start_markers=["Totals"],
            end_markers=["Footer"],
            output_key="total_amount",
        ),
    )

    assert result.value == "99.50"
