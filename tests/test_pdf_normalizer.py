from pathlib import Path

from normalizer import normalize_pdf_file

ROOT = Path(__file__).resolve().parents[1]


def test_pdf_normalizer_returns_expected_shape():
    normalized = normalize_pdf_file(ROOT / "test_files" / "pdfs" / "invoice_2_generated_variant.pdf")

    assert normalized["document_id"] == "invoice_2_generated_variant"
    assert normalized["pages"]
    assert normalized["pages"][0]["lines"]
    assert "INV-2026-1047" in normalized["full_text"]
