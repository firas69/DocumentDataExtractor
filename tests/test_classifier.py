import json
from pathlib import Path

from classification import InvoiceClassifier, load_blueprints

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_classifier_matches_invoice_2_blueprint():
    blueprints = load_blueprints([ROOT / "test_files" / "blueprints" / "invoice_2_blueprint.json"])
    classifier = InvoiceClassifier(blueprints)
    document = load_json(ROOT / "test_files" / "normalized_documents" / "invoice_2_generated_variant_normalized.json")

    result = classifier.classify(document, "invoice_2_generated_variant.pdf")

    assert result.status == "known"
    assert result.blueprint_id == "invoice_novaflow_layout_v1"
    assert result.confidence >= 0.65


def test_classifier_matches_original_invoice_2_by_margin():
    blueprints = load_blueprints([ROOT / "test_files" / "blueprints", ROOT / "examples" / "blueprints"])
    classifier = InvoiceClassifier(blueprints)
    document = load_json(ROOT / "test_files" / "normalized_documents" / "invoice_2_normalized.json")

    result = classifier.classify(document, "invoice_2.pdf")

    assert result.status == "known"
    assert result.blueprint_id == "invoice_novaflow_layout_v1"
    assert "clearly ahead" in result.reason


def test_classifier_flags_unknown_document():
    blueprints = load_blueprints([ROOT / "test_files" / "blueprints" / "invoice_2_blueprint.json"])
    classifier = InvoiceClassifier(blueprints)
    document = {"document_id": "unknown", "full_text": "Random note with no invoice labels or totals."}

    result = classifier.classify(document, "unknown.pdf")

    assert result.status == "unknown"
    assert result.blueprint_id is None
