# InvoiceDataExtractor

Proof of Concept for a blueprint-driven PDF invoice data extraction system.

The implemented scope is only the Generic Extraction Engine:

```text
Normalized Document Representation + Blueprint JSON
-> ExtractionEngine.extract()
-> structured data, confidence scores, warnings, metadata
```

The engine does not parse PDFs, generate blueprints, call an LLM, or use hidden AI reasoning. It deterministically executes the blueprint supplied to it.

## Project Layout

```text
src/extraction_engine/
  engine.py
  models.py
  field_extractor.py
  table_extractor.py
  strategies.py
  normalizers.py
  validators.py
  confidence.py
  warnings.py

examples/
  normalized_documents/
  blueprints/
  run_extraction_demo.py

tests/
```

## Usage

```python
from extraction_engine import ExtractionEngine

result = ExtractionEngine().extract(
    normalized_document=normalized_document,
    blueprint=blueprint,
)
```

## Supported Field Strategies

- `label_neighbor`: extracts values on the same line after a label, after a colon, or on the next line.
- `regex_pattern`: extracts using `extraction.pattern`, `validation.pattern`, or fallback pattern keys.
- `keyword_window`: finds a label and searches nearby lines.
- `section_anchor`: searches within a marker-bounded section.
- `fallback_search`: tries label, regex, then keyword search.

## Supported Table Strategies

- `header_based`: finds a header line with enough keywords, then parses following lines until an end marker.
- `marker_based`: extracts rows between start and end markers.

The table parser uses simple whitespace splitting for this POC.

## Run Tests

```bash
python -m pytest
```

## Run Demo

```bash
PYTHONPATH=src python examples/run_extraction_demo.py
```

The demo processes three synthetic invoice documents with three different blueprints and saves outputs to `examples/outputs/`.

## Run The GUI

Install the project dependencies, then launch the Streamlit POC app:

```bash
python -m pip install -e .
PYTHONPATH=src python -m streamlit run src/gui/streamlit_app.py
```

The GUI supports:

- PDF upload by browsing or drag and drop
- automatic PDF normalization using `pypdf`
- deterministic blueprint classification
- unknown-document flagging
- per-invoice confirmation before extraction
- structured extracted-data views
- warnings and confidence display
- JSON export for full extraction results
- CSV export for extracted tables

The app loads known blueprints from:

```text
test_files/blueprints/
examples/blueprints/
```

Uploaded PDFs are normalized into `outputs/normalized/`, and confirmed extraction results are saved into `outputs/extracted/`.

The GUI is intentionally POC-focused. It does not add authentication, databases, billing, or production workflow management.

## Current Limitations

- No PDF parsing or OCR.
- PDF normalization currently uses text extraction via `pypdf`; scanned PDFs need OCR before this pipeline.
- No coordinate/layout reasoning yet.
- Table parsing is intentionally simple and whitespace-based.
- Date parsing supports common formats but does not resolve all ambiguous locale cases.
- Confidence scoring is heuristic and explainable, not statistical.
- Classification is deterministic blueprint matching, not a guarantee of production-grade document routing.
