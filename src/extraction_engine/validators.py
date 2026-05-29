from __future__ import annotations

import re
from typing import Any

from .models import BlueprintField, BlueprintTable
from .normalizers import normalize_number
from .warnings import ExtractionWarning


def validate_field(field: BlueprintField, value: Any) -> list[ExtractionWarning]:
    warnings: list[ExtractionWarning] = []
    key = field.output_key or field.name
    if value in (None, ""):
        if field.required:
            warnings.append(ExtractionWarning("required_missing", f"Required field {key!r} was not extracted", field=key))
        return warnings

    data_type = field.data_type.casefold()
    if data_type in {"number", "weight"} and not isinstance(value, int | float):
        warnings.append(ExtractionWarning("invalid_number", f"Field {key!r} is not a valid number", field=key))
    elif data_type == "date" and isinstance(value, str) and not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        warnings.append(ExtractionWarning("invalid_date", f"Field {key!r} was not normalized to YYYY-MM-DD", field=key))
    elif data_type in {"currency", "money"}:
        if not isinstance(value, dict) or value.get("amount") is None:
            warnings.append(ExtractionWarning("invalid_currency", f"Field {key!r} is not a valid currency amount", field=key))
    elif data_type == "currency_code" and not isinstance(value, str):
        warnings.append(ExtractionWarning("invalid_currency_code", f"Field {key!r} is not a valid currency code", field=key))

    pattern = field.validation.get("pattern") or field.validation.get("regex")
    if pattern and value is not None:
        pattern_value = str(value.get("amount")) if isinstance(value, dict) else str(value)
        if not re.match(pattern, pattern_value):
            warnings.append(ExtractionWarning("pattern_mismatch", f"Field {key!r} does not match pattern {pattern!r}", field=key))
    return warnings


def validate_numeric_consistency(extracted_data: dict[str, Any]) -> list[ExtractionWarning]:
    subtotal = normalize_number(extracted_data.get("subtotal"))
    total = normalize_number(extracted_data.get("total_amount"))
    if subtotal is None or total is None:
        return []
    additions = 0.0
    for key in ("tax_amount", "shipping_amount"):
        value = normalize_number(extracted_data.get(key))
        if value is not None:
            additions += float(value)
    discount = normalize_number(extracted_data.get("discount_amount")) or 0
    expected = float(subtotal) + additions - float(discount)
    if abs(expected - float(total)) > 0.05:
        return [
            ExtractionWarning(
                "numeric_inconsistency",
                f"subtotal/tax/discount/shipping do not approximately equal total_amount ({expected} != {total})",
            )
        ]
    return []


def validate_table(table: BlueprintTable, rows: list[dict[str, Any]]) -> list[ExtractionWarning]:
    warnings: list[ExtractionWarning] = []
    key = table.output_key or table.table_name
    if not rows:
        if table.required:
            warnings.append(ExtractionWarning("required_table_missing", f"Required table {key!r} was not extracted", table=key))
        return warnings

    for column in table.columns:
        output_key = column.get("output_key") or column.get("name")
        if column.get("required") and any(row.get(output_key) in (None, "") for row in rows):
            warnings.append(ExtractionWarning("required_column_missing", f"Required column {output_key!r} has missing values", table=key))
        if column.get("data_type") == "number":
            for row_index, row in enumerate(rows, start=1):
                value = row.get(output_key)
                if value is not None and not isinstance(value, int | float):
                    warnings.append(
                        ExtractionWarning(
                            "invalid_table_number",
                            f"Column {output_key!r} in row {row_index} is not numeric",
                            table=key,
                        )
                    )
    return warnings
