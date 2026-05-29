from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from pypdf import PdfReader


class PdfNormalizationError(ValueError):
    pass


def normalize_pdf_file(pdf_path: str | Path) -> dict[str, Any]:
    path = Path(pdf_path)
    return _normalize_reader(PdfReader(str(path)), document_id=path.stem, source_file=str(path))


def normalize_pdf_bytes(file_bytes: bytes, file_name: str) -> dict[str, Any]:
    if not file_name.lower().endswith(".pdf"):
        raise PdfNormalizationError("Only PDF files are supported.")
    return _normalize_reader(PdfReader(BytesIO(file_bytes)), document_id=Path(file_name).stem, source_file=file_name)


def _normalize_reader(reader: PdfReader, document_id: str, source_file: str) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    full_text_parts: list[str] = []

    for page_index, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        full_text_parts.append(page_text)
        lines = [
            {
                "line_number": line_index,
                "text": line.strip(),
                "page_number": page_index,
            }
            for line_index, line in enumerate(page_text.splitlines(), start=1)
            if line.strip()
        ]
        pages.append(
            {
                "page_number": page_index,
                "text": page_text,
                "lines": lines,
                "blocks": [
                    {
                        "block_id": f"p{page_index}_b1",
                        "type": "text",
                        "text": page_text,
                        "page_number": page_index,
                    }
                ]
                if page_text.strip()
                else [],
            }
        )

    full_text = "\n".join(part for part in full_text_parts if part)
    if not full_text.strip():
        raise PdfNormalizationError("No text could be extracted from this PDF.")

    return {
        "document_id": document_id,
        "source_file": source_file,
        "pages": pages,
        "full_text": full_text,
        "metadata": {
            "normalizer": "pypdf.extract_text",
            "page_count": len(reader.pages),
        },
    }
