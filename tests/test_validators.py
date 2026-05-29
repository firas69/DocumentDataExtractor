from extraction_engine.models import BlueprintField, BlueprintTable
from extraction_engine.validators import validate_field, validate_numeric_consistency, validate_table


def test_required_field_warning():
    field = BlueprintField.from_dict(
        {"name": "invoice_number", "required": True, "output_key": "invoice_number"}
    )

    warnings = validate_field(field, None)

    assert warnings
    assert warnings[0].code == "required_missing"


def test_pattern_warning():
    field = BlueprintField.from_dict(
        {
            "name": "invoice_number",
            "validation": {"pattern": "^[A-Z]+$"},
            "output_key": "invoice_number",
        }
    )

    warnings = validate_field(field, "123")

    assert [warning.code for warning in warnings] == ["pattern_mismatch"]


def test_numeric_consistency_warning():
    warnings = validate_numeric_consistency({"subtotal": 100, "tax_amount": 20, "total_amount": 130})

    assert warnings
    assert warnings[0].code == "numeric_inconsistency"


def test_table_required_column_warning():
    table = BlueprintTable.from_dict(
        {
            "table_name": "line_items",
            "columns": [
                {"name": "description", "required": True, "output_key": "description"},
            ],
        }
    )

    warnings = validate_table(table, [{"description": ""}])

    assert warnings
    assert warnings[0].code == "required_column_missing"
