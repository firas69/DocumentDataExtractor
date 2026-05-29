# Blueprint PDF Data Extractor

Proof of Concept for a blueprint-driven PDF data extraction system.

This project demonstrates a reusable extraction workflow for structured and semi-structured business documents such as:

- invoices
- Bills of Lading
- bank statements
- receipts or similar document layouts

The goal is not to build a one-time extractor for one PDF template.

The goal is to separate document-specific rules from the extraction engine, so different document types can be processed using different blueprints while keeping the same generic extraction logic.

```text
PDF Document
-> Normalizer
-> Normalized Document Representation
-> Blueprint Classification
-> Matching Blueprint JSON
-> ExtractionEngine.extract()
-> Structured data, confidence scores, warnings, metadata
```

The extraction engine does not generate blueprints, call an LLM, or rely on hidden AI reasoning.  
It deterministically executes the supplied blueprint.

Blueprint generation is treated as a setup/configuration phase. In a real client project, representative samples are analyzed first, then reusable blueprints are created or refined for each known document layout.

---

## Why This Project Exists

Some of my professional data extraction work was done in private consulting/client contexts and cannot be shared publicly.

This repository was created as a public Proof of Concept to demonstrate my approach to document data extraction:

- document normalization
- reusable blueprint-based extraction
- document type classification
- unknown-document flagging
- warning handling for missing or invalid fields
- structured CSV/JSON output

The project is intentionally POC-focused, but it reflects the workflow I would use when building a custom extraction tool for a client.

---

## Implemented Scope

The implemented scope includes:

- PDF upload through a Streamlit GUI
- text extraction and normalization using `pypdf`
- deterministic document classification against known blueprints
- generic extraction engine
- field extraction strategies
- table extraction strategies
- normalization utilities
- validation and warnings
- confidence scores
- JSON export
- CSV export for extracted tables
- example blueprints and sample documents
- automated tests

The system currently supports known document layouts through blueprint files.  
Unknown documents are flagged instead of being blindly extracted.

---

## Core Engine Contract

```text
Normalized Document Representation + Blueprint JSON
-> ExtractionEngine.extract()
-> Structured data, confidence scores, warnings, metadata
```

Usage example:

```python
from extraction_engine import ExtractionEngine

result = ExtractionEngine().extract(
    normalized_document=normalized_document,
    blueprint=blueprint,
)
```

The same engine can process different document types as long as a matching blueprint exists.

Example:

```text
Bill of Lading + BOL Blueprint
-> Same Extraction Engine
-> Structured shipment data

Invoice + Invoice Blueprint
-> Same Extraction Engine
-> Structured invoice data

Bank Statement + Statement Blueprint
-> Same Extraction Engine
-> Structured transaction data
```

---

## Project Layout

```text
src/
  extraction_engine/
    engine.py
    models.py
    field_extractor.py
    table_extractor.py
    strategies.py
    normalizers.py
    validators.py
    confidence.py
    warnings.py

  classification/
    invoice_classifier.py

  gui/
    streamlit_app.py

examples/
  normalized_documents/
  blueprints/
  run_extraction_demo.py

test_files/
  blueprints/
  pdfs/

outputs/
  normalized/
  extracted/

tests/
```

---

## Supported Field Strategies

- `label_neighbor`: extracts values on the same line after a label, after a colon, or on the next line.
- `regex_pattern`: extracts using `extraction.pattern`, `validation.pattern`, or fallback pattern keys.
- `keyword_window`: finds a label and searches nearby lines.
- `section_anchor`: searches within a marker-bounded section.
- `fallback_search`: tries label extraction, regex extraction, then keyword search.

---

## Supported Table Strategies

- `header_based`: finds a header line with enough keywords, then parses following lines until an end marker.
- `marker_based`: extracts rows between start and end markers.

The table parser uses simple whitespace splitting for this POC.  
It is intentionally simple and can be upgraded later with coordinate-aware parsing, OCR, or table-specific extraction logic.

---

## Run Tests

```bash
python -m pytest
```

---

## Run Demo Script

```bash
PYTHONPATH=src python examples/run_extraction_demo.py
```

The demo script processes synthetic business documents using matching blueprints and saves outputs to:

```text
examples/outputs/
```

---

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
- user confirmation before extraction
- structured extracted-data views
- warnings and confidence display
- JSON export for full extraction results
- CSV export for extracted tables

The app loads known blueprints from:

```text
test_files/blueprints/
examples/blueprints/
```

Uploaded PDFs are normalized into:

```text
outputs/normalized/
```

Confirmed extraction results are saved into:

```text
outputs/extracted/
```

---

## Demo Workflow

The GUI demonstrates the following workflow:

```text
1. Upload PDF documents
2. Normalize document text
3. Classify each document against known blueprints
4. Flag unknown document types
5. Confirm extraction for known documents
6. Extract structured data with the generic engine
7. Display extracted results, confidence scores, and warnings
8. Export JSON or CSV outputs
```

The demo includes multiple document families, including Bills of Lading, invoices, and bank statements.

---

## Warning Handling

The system can raise warnings when required or important fields are missing, invalid, or unreadable.

Example warning cases:

- unreadable invoice number
- unreadable BOL number
- missing required date
- invalid amount format
- table extraction issues
- unknown document type

The goal is not to silently produce incorrect data.  
The system extracts what it can and clearly marks fields that need review.

---

## Current Limitations

This is a Proof of Concept, not a production SaaS product.

Current limitations:

- PDF normalization currently uses text extraction via `pypdf`.
- Scanned PDFs require OCR before this pipeline.
- No advanced coordinate/layout reasoning yet.
- Table parsing is simple and whitespace-based.
- Date parsing supports common formats but does not resolve all ambiguous locale cases.
- Confidence scoring is heuristic and explainable, not statistical.
- Classification is deterministic blueprint matching, not a guarantee of production-grade document routing.
- The GUI is intentionally lightweight and demo-focused.
- No authentication, database, billing, user management, or production workflow management.

---

## Future Improvements

Possible improvements include:

- OCR support for scanned PDFs
- coordinate-aware field extraction
- better table detection
- layout-aware classification
- editable blueprint review interface
- Excel export for full document results
- API endpoint for batch processing
- database-backed job history
- production deployment with authentication and monitoring

---

## Positioning

This project is designed to demonstrate the core workflow of a custom document extraction tool:

```text
Same engine.
Different blueprints.
Different document structures.
```

It can be adapted to client-specific document templates by creating or refining blueprints for the required document layouts.
