from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd
import streamlit as st

from classification import InvoiceClassifier, load_blueprints
from extraction_engine import ExtractionEngine
from normalizer import PdfNormalizationError, normalize_pdf_bytes


ROOT = Path(__file__).resolve().parents[2]
BLUEPRINT_DIRS = [ROOT / "test_files" / "blueprints", ROOT / "examples" / "blueprints"]
OUTPUT_DIR = ROOT / "outputs" / "extracted"
NORMALIZED_DIR = ROOT / "outputs" / "normalized"
UPLOADED_BLUEPRINT_DIR = ROOT / "outputs" / "blueprints"


def main() -> None:
    st.set_page_config(page_title="Blueprint-Driven Invoice Extraction POC", layout="wide")
    _style()
    _init_state()

    st.title("Blueprint-Driven Invoice Extraction POC")
    st.caption(
        "Upload PDF invoices, classify them against known blueprint types, "
        "and extract structured data using a generic extraction engine."
    )

    with st.sidebar:
        _blueprint_upload_section()

    blueprints = load_blueprints([path for path in [*BLUEPRINT_DIRS, UPLOADED_BLUEPRINT_DIR] if path.exists()])
    classifier = InvoiceClassifier(blueprints)

    with st.sidebar:
        st.header("POC Settings")
        st.write(f"Known blueprints: **{len(blueprints)}**")
        if st.button("Clear session"):
            st.session_state.documents = {}
            st.rerun()
        with st.expander("Loaded blueprints"):
            for candidate in blueprints:
                st.write(f"- {candidate.blueprint_id}")

    _upload_section(classifier)
    _run_overview_section()
    _classification_section()
    _results_section()


def _init_state() -> None:
    st.session_state.setdefault("documents", {})


def _blueprint_upload_section() -> None:
    st.header("Blueprints")
    uploaded_blueprints = st.file_uploader(
        "Add blueprint JSON files",
        type=["json"],
        accept_multiple_files=True,
        help="Uploaded blueprints are saved locally and become available for classification.",
    )
    if not uploaded_blueprints:
        return

    UPLOADED_BLUEPRINT_DIR.mkdir(parents=True, exist_ok=True)
    saved = 0
    for uploaded_blueprint in uploaded_blueprints:
        try:
            blueprint = json.loads(uploaded_blueprint.getvalue().decode("utf-8"))
            blueprint_id = _blueprint_id(blueprint, Path(uploaded_blueprint.name).stem)
            output_path = UPLOADED_BLUEPRINT_DIR / f"{blueprint_id}.json"
            output_path.write_text(json.dumps(blueprint, indent=2, ensure_ascii=False), encoding="utf-8")
            saved += 1
        except Exception as exc:
            st.error(f"Could not add {uploaded_blueprint.name}: {exc}")
    if saved:
        st.success(f"Added {saved} blueprint file{'s' if saved != 1 else ''}.")
        st.rerun()


def _upload_section(classifier: InvoiceClassifier) -> None:
    st.subheader("1. Upload Invoices")
    uploaded_files = st.file_uploader(
        "Browse or drag PDF invoices here",
        type=["pdf"],
        accept_multiple_files=True,
    )
    if not uploaded_files:
        st.info("Upload one or more PDF files to start normalization and classification.")
        return

    for uploaded_file in uploaded_files:
        key = f"{uploaded_file.name}:{uploaded_file.size}"
        if key in st.session_state.documents:
            continue
        record = {
            "file_name": uploaded_file.name,
            "status": "Uploaded",
            "normalized_document": None,
            "classification": None,
            "extraction_result": None,
            "error": None,
        }
        try:
            record["status"] = "Normalizing"
            normalized = normalize_pdf_bytes(uploaded_file.getvalue(), uploaded_file.name)
            record["normalized_document"] = normalized
            record["status"] = "Normalized"
            record["classification"] = classifier.classify(normalized, uploaded_file.name)
            _save_normalized(uploaded_file.name, normalized)
        except PdfNormalizationError as exc:
            record["status"] = "Failed normalization"
            record["error"] = str(exc)
        except Exception as exc:  # Streamlit should keep processing the other uploads.
            record["status"] = "Failed normalization"
            record["error"] = f"Unexpected normalization error: {exc}"
        st.session_state.documents[key] = record


def _run_overview_section() -> None:
    records = list(st.session_state.documents.values())
    if not records:
        return

    known = sum(1 for record in records if _is_known(record))
    unknown = sum(1 for record in records if _is_unknown(record))
    extracted = sum(1 for record in records if record.get("extraction_result") is not None)
    warnings = sum(len(_extraction_result(record).get("warnings", [])) for record in records)

    st.subheader("Run Overview")
    cols = st.columns(5)
    cols[0].metric("Uploaded", len(records))
    cols[1].metric("Known", known)
    cols[2].metric("Unknown", unknown)
    cols[3].metric("Extracted", extracted)
    cols[4].markdown(_warning_badge_count(warnings), unsafe_allow_html=True)


def _classification_section() -> None:
    st.subheader("2. Classification Results")
    records = list(st.session_state.documents.items())
    if not records:
        return

    extractable = [
        key
        for key, record in records
        if record.get("classification") is not None
        and record["classification"].status == "known"
        and record.get("extraction_result") is None
        and record.get("error") is None
    ]
    if extractable:
        if st.button(f"Extract all known invoices ({len(extractable)})", type="primary"):
            for key in extractable:
                _extract_record(key)
            st.rerun()

    for key, record in records:
        classification = record.get("classification")
        with st.container(border=True):
            cols = st.columns([2.2, 1.4, 1, 2.2, 1.3])
            cols[0].markdown(f"**{record['file_name']}**")
            cols[1].markdown(_status_badge(record["status"]))
            if record.get("error"):
                cols[2].error("Failed")
                cols[3].write(record["error"])
                continue

            if classification is None:
                cols[2].warning("Pending")
                continue

            if classification.status == "known":
                cols[2].success("Known")
                cols[3].write(f"**{classification.detected_type}**")
                cols[3].caption(f"Blueprint: {classification.blueprint_id}")
                cols[3].progress(classification.confidence)
                with cols[4]:
                    if st.button("Confirm and Extract", key=f"extract_{key}"):
                        _extract_record(key)
            else:
                cols[2].warning("Unknown")
                cols[3].write("No matching blueprint found")
                cols[3].progress(classification.confidence)
                cols[4].button("No extraction", key=f"disabled_{key}", disabled=True)

            with st.expander(f"Classification reason for {record['file_name']}"):
                st.write(classification.reason)


def _extract_record(key: str) -> None:
    record = st.session_state.documents[key]
    classification = record.get("classification")
    if classification is None or classification.status != "known" or not classification.blueprint:
        record["error"] = "No confirmed matching blueprint is available."
        return
    try:
        record["status"] = "Extracting"
        result = ExtractionEngine().extract(
            normalized_document=record["normalized_document"],
            blueprint=classification.blueprint,
        )
        record["extraction_result"] = result
        record["status"] = "Extracted"
        _save_extraction(record["file_name"], result)
    except Exception as exc:
        record["status"] = "Extraction failed"
        record["error"] = f"Extraction failed: {exc}"


def _results_section() -> None:
    st.subheader("3. Extraction Results")
    extracted_records = [
        record for record in st.session_state.documents.values() if record.get("extraction_result") is not None
    ]
    if not extracted_records:
        st.info("Confirmed invoices will appear here after extraction.")
        return

    actions = st.columns([1.2, 1.2, 3])
    with actions[0]:
        st.download_button(
            "Download All JSON",
            data=_json_zip(extracted_records),
            file_name="extracted_invoices_json.zip",
            mime="application/zip",
            key="download_all_json",
        )
    with actions[1]:
        summary_frame = _run_summary_frame(extracted_records)
        st.download_button(
            "Download Summary CSV",
            data=summary_frame.to_csv(index=False),
            file_name="extraction_summary.csv",
            mime="text/csv",
            key="download_summary_csv",
        )

    for record in extracted_records:
        result = record["extraction_result"]
        classification = record["classification"]
        warnings = result.get("warnings", [])

        with st.container(border=True):
            cols = st.columns([2.4, 1.2, 1.2, 1.2])
            cols[0].markdown(f"**{record['file_name']}**")
            cols[0].caption(classification.detected_type if classification else "Unknown")
            cols[1].success(record["status"])
            cols[2].markdown(_warning_badge(warnings), unsafe_allow_html=True)
            with cols[3]:
                st.download_button(
                    "Download JSON",
                    data=json.dumps(result, indent=2, ensure_ascii=False),
                    file_name=f"{Path(record['file_name']).stem}_extracted.json",
                    mime="application/json",
                    key=f"download_{record['file_name']}",
                )

            with st.expander("View Extracted Data", expanded=False):
                _render_extracted_data(result)


def _render_extracted_data(result: dict[str, Any]) -> None:
    data = result.get("extracted_data", {})

    for section_name, section_value in data.items():
        if isinstance(section_value, list):
            st.markdown(f"**{_label(section_name)}**")
            if section_value:
                frame = pd.json_normalize(section_value)
                st.dataframe(frame, use_container_width=True, hide_index=True)
                st.download_button(
                    f"Download {_label(section_name)} CSV",
                    data=frame.to_csv(index=False),
                    file_name=f"{section_name}.csv",
                    mime="text/csv",
                    key=f"csv_{result.get('document_id')}_{section_name}",
                )
            else:
                st.warning("No rows extracted.")
        elif isinstance(section_value, dict):
            st.markdown(f"**{_label(section_name)}**")
            st.dataframe(_dict_to_frame(section_value), use_container_width=True, hide_index=True)
        else:
            st.write({section_name: section_value})

    warnings = result.get("warnings", [])
    if warnings:
        with st.expander("Warnings"):
            for warning in warnings:
                friendly = _friendly_warning(warning)
                st.markdown(
                    "<div class='friendly-warning'>"
                    f"<div class='friendly-warning-title'>{friendly['title']}</div>"
                    f"<div class='friendly-warning-body'>{friendly['message']}</div>"
                    "</div>",
                    unsafe_allow_html=True,
                )
            with st.expander("Technical details"):
                st.dataframe(pd.DataFrame(warnings), use_container_width=True, hide_index=True)


def _dict_to_frame(value: dict[str, Any], prefix: str = "") -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    def visit(data: dict[str, Any], path: str = "") -> None:
        for key, item in data.items():
            label = f"{path}.{key}" if path else key
            if isinstance(item, dict):
                visit(item, label)
            else:
                rows.append({"field": _label(label), "value": item})

    visit(value, prefix)
    return pd.DataFrame(rows)


def _save_normalized(file_name: str, normalized: dict[str, Any]) -> None:
    NORMALIZED_DIR.mkdir(parents=True, exist_ok=True)
    output_path = NORMALIZED_DIR / f"{Path(file_name).stem}_normalized.json"
    output_path.write_text(json.dumps(normalized, indent=2, ensure_ascii=False), encoding="utf-8")


def _save_extraction(file_name: str, result: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{Path(file_name).stem}_extracted.json"
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")


def _status_badge(status: str) -> str:
    return f"`{status}`"


def _warning_badge(warnings: list[dict[str, Any]]) -> str:
    return _warning_badge_count(len(warnings), has_errors=any(warning.get("severity") == "error" for warning in warnings))


def _warning_badge_count(count: int, has_errors: bool = False) -> str:
    if count == 0:
        color = "#064e3b"
        label = "0 warnings"
    elif count <= 2 and not has_errors:
        color = "#7c2d12"
        label = f"{count} warning{'s' if count != 1 else ''}"
    else:
        color = "#7f1d1d"
        label = f"{count} warnings"
    return (
        "<div class='warning-badge' style='"
        f"background:{color}; color:#f8fafc;'>"
        f"{label}</div>"
    )


def _friendly_warning(warning: dict[str, Any]) -> dict[str, str]:
    code = str(warning.get("code", "warning"))
    field = _label(str(warning.get("field") or warning.get("table") or "item"))
    severity = str(warning.get("severity", "warning")).title()

    messages = {
        "pattern_mismatch": (
            f"Please review {field}",
            f"The extracted value for {field} does not look like the expected format.",
        ),
        "required_missing": (
            f"Missing {field}",
            f"The document was processed, but {field} could not be found.",
        ),
        "required_table_missing": (
            f"Missing {field}",
            f"The expected table for {field} could not be found.",
        ),
        "required_column_missing": (
            f"Incomplete {field}",
            f"Some required values are missing from {field}.",
        ),
        "invalid_number": (
            f"Check {field}",
            f"The extracted value for {field} was not recognized as a number.",
        ),
        "invalid_table_number": (
            f"Check {field}",
            f"One or more table values in {field} were not recognized as numbers.",
        ),
        "invalid_date": (
            f"Check {field}",
            f"The extracted value for {field} was not recognized as a standard date.",
        ),
        "date_uncertain": (
            f"Check {field}",
            f"The date for {field} may need manual review.",
        ),
        "invalid_currency": (
            f"Check {field}",
            f"The extracted value for {field} was not recognized as a valid amount.",
        ),
        "invalid_currency_code": (
            f"Check {field}",
            f"The currency for {field} was not recognized.",
        ),
        "numeric_inconsistency": (
            "Totals may need review",
            "The extracted subtotal, tax, discount, shipping, or total amounts do not fully add up.",
        ),
    }
    title, message = messages.get(
        code,
        (f"{severity}: {field}", "This item may need manual review before the extracted data is approved."),
    )
    return {"title": title, "message": message}


def _json_zip(records: list[dict[str, Any]]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for record in records:
            file_name = f"{Path(record['file_name']).stem}_extracted.json"
            archive.writestr(
                file_name,
                json.dumps(record["extraction_result"], indent=2, ensure_ascii=False),
            )
    buffer.seek(0)
    return buffer.getvalue()


def _run_summary_frame(records: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for record in records:
        result = record["extraction_result"]
        classification = record.get("classification")
        metadata = result.get("metadata", {})
        rows.append(
            {
                "file_name": record["file_name"],
                "detected_type": classification.detected_type if classification else "",
                "blueprint_id": result.get("blueprint_id"),
                "status": record.get("status"),
                "warnings": len(result.get("warnings", [])),
                "fields_extracted": metadata.get("fields_extracted"),
                "fields_attempted": metadata.get("fields_attempted"),
                "tables_extracted": metadata.get("tables_extracted"),
                "tables_attempted": metadata.get("tables_attempted"),
            }
        )
    return pd.DataFrame(rows)


def _is_known(record: dict[str, Any]) -> bool:
    classification = record.get("classification")
    return classification is not None and classification.status == "known"


def _is_unknown(record: dict[str, Any]) -> bool:
    classification = record.get("classification")
    return classification is not None and classification.status == "unknown"


def _extraction_result(record: dict[str, Any]) -> dict[str, Any]:
    result = record.get("extraction_result")
    return result if isinstance(result, dict) else {}


def _label(value: str) -> str:
    return value.replace("_", " ").replace(".", " / ").title()


def _blueprint_id(blueprint: dict[str, Any], fallback: str) -> str:
    metadata = blueprint.get("blueprint_metadata", {}) if isinstance(blueprint.get("blueprint_metadata"), dict) else {}
    raw_id = str(blueprint.get("blueprint_id") or metadata.get("blueprint_id") or fallback)
    return "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in raw_id)


def _style() -> None:
    st.markdown(
        """
        <style>
        .block-container { padding-top: 2rem; }
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"],
        #MainMenu {
            visibility: hidden;
            height: 0;
        }
        .warning-badge {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 7.5rem;
            padding: 0.55rem 0.8rem;
            border-radius: 0.35rem;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
            font-size: 0.9rem;
            font-weight: 700;
            letter-spacing: 0;
        }
        .friendly-warning {
            border-left: 4px solid #92400e;
            background: #fffbeb;
            color: #1f2937;
            padding: 0.75rem 0.9rem;
            border-radius: 0.35rem;
            margin-bottom: 0.6rem;
        }
        .friendly-warning-title {
            font-weight: 700;
            margin-bottom: 0.2rem;
        }
        .friendly-warning-body {
            font-size: 0.95rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
