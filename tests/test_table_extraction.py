from extraction_engine.models import BlueprintTable, NormalizedDocument
from extraction_engine.table_extractor import TableExtractor


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


def table(strategy: str = "header_based") -> BlueprintTable:
    return BlueprintTable.from_dict(
        {
            "table_name": "line_items",
            "detection_strategy": strategy,
            "header_keywords": ["Description", "Qty", "Price", "Amount"],
            "start_markers": ["Items"],
            "end_markers": ["Total"],
            "columns": [
                {"name": "description", "data_type": "string", "output_key": "description"},
                {"name": "quantity", "data_type": "number", "output_key": "quantity"},
                {"name": "unit_price", "data_type": "number", "output_key": "unit_price"},
                {"name": "line_total", "data_type": "number", "output_key": "line_total"},
            ],
            "output_key": "line_items",
        }
    )


def test_header_based_table_extraction():
    result = TableExtractor().extract_table(
        document_from_lines(
            [
                "Header",
                "Description Qty Price Amount",
                "Web service 1 100.00 100.00",
                "Total 100.00",
            ]
        ),
        table(),
    )

    assert result.found is True
    assert result.rows == [
        {"description": "Web service", "quantity": 1, "unit_price": 100, "line_total": 100}
    ]


def test_marker_based_table_extraction_skips_header_line():
    result = TableExtractor().extract_table(
        document_from_lines(
            [
                "Items",
                "Description Qty Price Amount",
                "Audit service 2 75.00 150.00",
                "Total 150.00",
            ]
        ),
        table("marker_based"),
    )

    assert len(result.rows) == 1
    assert result.rows[0]["description"] == "Audit service"
