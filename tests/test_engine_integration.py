import json
from pathlib import Path

from extraction_engine import ExtractionEngine

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_engine_processes_available_blueprint_documents():
    engine = ExtractionEngine()

    cases = [
        (
            ROOT / "test_files" / "normalized_documents" / "invoice_1_normalized.json",
            ROOT / "test_files" / "blueprints" / "invoice_1_blueprint.json",
        ),
        (
            ROOT / "test_files" / "normalized_documents" / "invoice_2_normalized.json",
            ROOT / "test_files" / "blueprints" / "invoice_2_blueprint.json",
        ),
        (
            ROOT / "test_files" / "normalized_documents" / "invoice_3_normalized.json",
            ROOT / "test_files" / "blueprints" / "invoice_3_blueprint.json",
        ),
    ]

    for document_path, blueprint_path in cases:
        document = load_json(document_path)
        blueprint = load_json(blueprint_path)

        result = engine.extract(document, blueprint)

        assert result["document_id"]
        assert result["blueprint_id"]
        assert result["extracted_data"]
        assert result["confidence"]
        assert result["metadata"]["fields_extracted"] > 0
