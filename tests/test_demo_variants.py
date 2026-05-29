import json
from pathlib import Path

from extraction_engine import ExtractionEngine

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_demo_variants_extract_with_expected_warning_cases():
    blueprint_by_prefix = {
        "bank_statement": load_json(ROOT / "test_files" / "blueprints" / "invoice_3_blueprint.json"),
        "bol": load_json(ROOT / "test_files" / "blueprints" / "invoice_1_blueprint.json"),
        "invoice": load_json(ROOT / "test_files" / "blueprints" / "invoice_2_blueprint.json"),
    }
    engine = ExtractionEngine()
    expected_warning_variants = {
        "bol_variant_03_normalized.json",
        "invoice_variant_02_normalized.json",
    }

    variant_paths = sorted((ROOT / "outputs" / "normalized").glob("*_variant_*_normalized.json"))
    assert variant_paths

    for path in variant_paths:
        stem = path.name
        prefix = "bank_statement" if stem.startswith("bank_statement") else "bol" if stem.startswith("bol") else "invoice"
        result = engine.extract(load_json(path), blueprint_by_prefix[prefix])

        if stem in expected_warning_variants:
            assert len(result["warnings"]) == 1
        else:
            assert result["warnings"] == []
        assert result["metadata"]["fields_extracted"] > 0
        assert result["metadata"]["tables_extracted"] == 1
