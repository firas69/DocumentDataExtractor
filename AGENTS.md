# AGENTS.md

## Project Purpose

This project is a Proof of Concept for a blueprint-driven PDF invoice extraction system.

The key idea is:

- Blueprints are generated separately.
- The extraction engine is generic.
- The engine receives a normalized document and a blueprint.
- The engine outputs structured extracted data.

## Hard Rules

- Do not build a one-time invoice extractor.
- Do not hardcode invoice-specific fields inside the engine.
- Do not call an LLM inside the extraction engine.
- Do not generate blueprints inside the extraction engine.
- Do not parse PDFs inside the extraction engine.
- The engine must work from normalized document JSON only.
- The same engine method must support multiple invoice types through different blueprints.
- Missing required fields should produce warnings, not crashes.
- Unknown blueprint keys should be ignored safely.
- Keep the code modular, typed, and testable.

## Main Engine Contract

The core interface is:

```python
result = ExtractionEngine().extract(
    normalized_document=normalized_document,
    blueprint=blueprint
)
```

## Required Output

The engine must return:

- extracted_data
- confidence
- warnings
- metadata

## POC Proof

The POC must demonstrate:

```text
Invoice Type A + Blueprint A -> Same Engine -> Extracted Data A
Invoice Type B + Blueprint B -> Same Engine -> Extracted Data B
Invoice Type C + Blueprint C -> Same Engine -> Extracted Data C
```

## Development Rules

- Implement incrementally.
- Add tests for each strategy.
- Add demo examples.
- Keep the README updated.
- Be honest about limitations.
